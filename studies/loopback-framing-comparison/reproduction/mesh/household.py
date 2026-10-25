"""Transparent household-memory scenarios, not distributed-inference forecasts."""
import math

GIB = 1024**3


def _number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f'{name} must be finite and {"positive" if positive else "nonnegative"}')
    return value


def _integer(value, name, positive=True):
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError(f'{name} must be a {"positive" if positive else "nonnegative"} integer')
    return value


def memory_estimate(*, parameters, weight_bits, household_available_gib,
                    weight_overhead_fraction=0, kv_bytes=0, runtime_reserve_bytes=0):
    """Ceiling of model bytes / assumed allocatable memory per household.

    Perfect sharding/pooling is assumed. The adjusted envelope is still only a
    capacity calculation, not proof that kernels, topology or throughput work.
    """
    _integer(parameters, 'parameters')
    for name, value in [('weight_bits', weight_bits), ('household_available_gib', household_available_gib)]:
        _number(value, name, positive=True)
    for name, value in [('weight_overhead_fraction', weight_overhead_fraction), ('kv_bytes', kv_bytes), ('runtime_reserve_bytes', runtime_reserve_bytes)]:
        _number(value, name)
    weights = parameters * weight_bits / 8
    memory = household_available_gib * GIB
    adjusted = weights * (1 + weight_overhead_fraction) + kv_bytes + runtime_reserve_bytes
    for name, value in [('weights', weights), ('household memory', memory), ('adjusted memory', adjusted)]:
        _number(value, name, positive=True)
    return {'weight_bytes': weights, 'household_available_bytes_assumption': memory,
            'weight_only_households': math.ceil(weights / memory),
            'adjusted_model_bytes': adjusted, 'adjusted_households': math.ceil(adjusted / memory),
            'weight_overhead_fraction_assumption': weight_overhead_fraction,
            'kv_bytes': kv_bytes, 'runtime_reserve_bytes_assumption': runtime_reserve_bytes,
            'consent_premise': 'all_participating_devices_fully_informed_and_consented',
            'establishes_inference_feasibility': False}


def kv_cache_bytes(*, layers, kv_heads, head_dim, context_tokens, element_bits, batch=1):
    """Dense, uncompressed resident K and V cache; excludes allocator overhead."""
    for name, value in [('layers', layers), ('kv_heads', kv_heads), ('head_dim', head_dim), ('context_tokens', context_tokens), ('batch', batch)]:
        _integer(value, name)
    _number(element_bits, 'element_bits', positive=True)
    return 2 * layers * kv_heads * head_dim * context_tokens * batch * element_bits / 8


def communication_floor(*, households, hidden_size, activation_bits, payload_mbps,
                        one_way_ms, context_tokens=1):
    """Ideal serial layer pipeline, one contiguous stage per household.

    Each boundary transmits one activation per generated token. Ignores compute,
    serialization, output-return traffic, jitter, contention and retransmission.
    This is NOT a tensor-parallel/all-reduce or streaming-prefill model.
    """
    for name, value in [('households', households), ('hidden_size', hidden_size), ('context_tokens', context_tokens)]:
        _integer(value, name)
    _number(activation_bits, 'activation_bits', positive=True)
    _number(payload_mbps, 'payload_mbps', positive=True)
    _number(one_way_ms, 'one_way_ms')
    boundaries = households - 1
    payload_bytes = hidden_size * activation_bits / 8
    link_bytes_per_second = payload_mbps * 1_000_000 / 8
    per_boundary = one_way_ms / 1000 + payload_bytes / link_bytes_per_second
    decode = boundaries * per_boundary
    prefill = boundaries * (one_way_ms / 1000 + payload_bytes * context_tokens / link_bytes_per_second)
    _number(decode, 'derived decode time')
    _number(prefill, 'derived prefill time')
    return {'interhousehold_boundaries': boundaries, 'activation_bytes_per_decode_boundary': payload_bytes,
            'decode_communication_seconds': decode, 'prefill_communication_seconds': prefill,
            'decode_tokens_per_second_ceiling_from_communication_only': 1 / decode if decode > 0 else None,
            'compute_time_included': False, 'measured_network': False,
            'topology_assumption': 'serial_contiguous_layer_pipeline_one_stage_per_household'}
