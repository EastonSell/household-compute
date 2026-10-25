"""Single-request serial pipeline model; all device/link values are assumptions."""
import math


def _number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be a number')
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f'{name} must be finite and {"positive" if positive else "nonnegative"}')
    return value


def _index(records, label):
    indexed = {}
    for record in records:
        identifier = record.get('id')
        if not isinstance(identifier, str) or not identifier:
            raise ValueError(f'{label} id must be a nonempty string')
        if identifier in indexed:
            raise ValueError(f'duplicate {label} id: {identifier}')
        indexed[identifier] = record
    return indexed


def simulate(scenario, placement):
    """Estimate latency for explicit placements. Raises ValueError if infeasible.

    All assigned stage weights stay resident. A conservative per-device transient
    reserve is max(workspace + incoming activation + output activation), over its
    stages. Initial input is modeled as zero bytes; weights are already loaded.
    """
    stages = scenario['stages']
    devices = _index(scenario['devices'], 'device')
    _index(stages, 'stage')
    if not stages or len(placement) != len(stages):
        raise ValueError('placement must assign one device to each nonempty stage')
    links = {}
    for link in scenario.get('links', []):
        key = (link['source'], link['target'])
        if key in links:
            raise ValueError('duplicate directed link')
        if any(endpoint not in devices for endpoint in key):
            raise ValueError('link endpoint must name a device')
        _number(link['bytes_per_second'], 'bytes_per_second', positive=True)
        _number(link['latency_ms'], 'latency_ms')
        links[key] = link
    weights, transient, compute = {}, {}, 0.0
    for index, (stage, device_id) in enumerate(zip(stages, placement)):
        if device_id not in devices:
            raise ValueError(f'unknown placement device: {device_id}')
        device = devices[device_id]
        if device.get('consent') is not True:
            raise ValueError(f'explicit consent required for {device_id}')
        capacity = _number(device['memory_bytes'], 'memory_bytes', positive=True)
        rate = _number(device['ops_per_second'], 'ops_per_second', positive=True)
        for field in ('operations', 'weights_bytes', 'workspace_bytes', 'output_bytes'):
            _number(stage[field], field)
        weights[device_id] = weights.get(device_id, 0) + stage['weights_bytes']
        incoming = stages[index - 1]['output_bytes'] if index else 0
        reserve = stage['workspace_bytes'] + incoming + stage['output_bytes']
        transient[device_id] = max(transient.get(device_id, 0), reserve)
        if weights[device_id] + transient[device_id] > capacity:
            raise ValueError(f'memory capacity exceeded on {device_id}')
        compute += stage['operations'] / rate
    transfer = 0.0
    transferred_bytes = 0
    for index in range(1, len(stages)):
        source, target = placement[index - 1:index + 1]
        if source == target:
            continue
        link = links.get((source, target))
        if link is None:
            raise ValueError(f'missing directed link: {source} -> {target}')
        payload = stages[index - 1]['output_bytes']
        transferred_bytes += payload
        transfer += payload / link['bytes_per_second'] + link['latency_ms'] / 1000
    return {
        'kind': 'analytical_estimate',
        'placement': list(placement),
        'compute_seconds': compute,
        'transfer_seconds': transfer,
        'total_seconds': compute + transfer,
        'transferred_bytes': transferred_bytes,
        'required_memory_bytes': {key: weights[key] + transient[key] for key in weights},
    }
