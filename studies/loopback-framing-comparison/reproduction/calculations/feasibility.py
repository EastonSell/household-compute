"""Deterministic analytical scenarios; no hardware/model execution or networking.

All memory/compute/link/availability scenario outputs are hypothetical calculations,
not observations. Source dimensions are documented in the companion paper.
Uses only the Python standard library (Python 3.10+).
"""
from fractions import Fraction
from pathlib import Path
import csv
import html
import io
import json
import math

GIB = 1024 ** 3


def _int(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(name + ' must be a positive integer')
    return value


def _num(value, name, zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float, Fraction)):
        raise ValueError(name + ' must be finite and positive')
    if not math.isfinite(value) or value < 0 or (not zero and value == 0):
        raise ValueError(name + ' must be finite and ' + ('nonnegative' if zero else 'positive'))
    return Fraction(str(value))


def weight_bytes(parameters, bits):
    return _int(parameters, 'parameters') * _num(bits, 'bits') / 8


def households(required_bytes, budget_bytes):
    ratio = _num(required_bytes, 'required bytes') / _num(budget_bytes, 'budget bytes')
    return math.ceil(ratio)


def kv_bytes(layers, kv_heads, head_dim, context, batch, element_bytes):
    values = [layers, kv_heads, head_dim, context, batch, element_bytes]
    for v in values:
        _int(v, 'KV dimension')
    return 2 * math.prod(values)


def comm_seconds(stages, width, element_bytes, mbps, one_way_ms):
    _int(stages, 'stages')
    _int(width, 'width')
    _int(element_bytes, 'element bytes')
    rate = _num(mbps, 'Mbps') * 1_000_000 / 8
    latency = _num(one_way_ms, 'one-way ms', zero=True) / 1000
    return float((stages - 1) * (latency + width * element_bytes / rate))


def serial_seconds(stage_compute_ms):
    if not stage_compute_ms:
        raise ValueError('at least one stage is required')
    return float(sum(_num(v, 'stage ms') for v in stage_compute_ms) / 1000)


def pipeline_rate_ceiling(stage_service_ms):
    if not stage_service_ms:
        raise ValueError('at least one stage is required')
    return float(1000 / max(_num(v, 'stage ms') for v in stage_service_ms))


def chain_availability(probability, stages, replicas=1):
    p = _num(probability, 'availability', zero=True)
    if p > 1:
        raise ValueError('availability must lie in [0, 1]')
    _int(stages, 'stages')
    _int(replicas, 'replicas')
    return float((1 - (1 - p) ** replicas) ** stages)


def tables():
    floors = []
    for p in [1, 8, 70, 400]:
        for bits in [4, 8, 16]:
            w = weight_bytes(p * 10 ** 9, bits)
            floors.append(dict(parameters_billion=p, weight_bits=bits,
                               ideal_weight_gib=float(w / GIB),
                               conditional_homes_at_12gib=households(w, 12 * GIB)))
    memory = []
    for p, layers in [(8, 32), (70, 80), (405, 126)]:
        kv = kv_bytes(layers, 8, 128, 8192, 1, 2)
        for bits in [4, 8, 16]:
            w = weight_bytes(p * 10 ** 9, bits)
            envelope = Fraction(6, 5) * w + kv + 2 * GIB
            for budget in [4, 12, 24]:
                memory.append(dict(parameters_billion=p, weight_bits=bits,
                                   household_gib=budget, ideal_weight_gib=float(w / GIB),
                                   kv_gib=float(Fraction(kv, GIB)),
                                   illustrative_envelope_gib=float(envelope / GIB),
                                   weight_only_households=households(w, budget * GIB),
                                   illustrative_envelope_households=households(envelope, budget * GIB)))
    comm = []
    for stages in [2, 4, 16, 64]:
        for name, mbps, ms in [('assumed_local', 1000, 1), ('assumed_impaired', 20, 20), ('assumed_stress', 5, 100)]:
            seconds = comm_seconds(stages, 8192, 2, mbps, ms)
            comm.append(dict(stages=stages, setting=name, payload_mbps=mbps,
                             one_way_ms=ms, activation_bytes=16384,
                             communication_seconds_per_token=seconds,
                             communication_only_tps_ceiling=1 / seconds))
    availability = [dict(per_node_probability=p, stages=k,
                         independent_no_replication=chain_availability(p, k),
                         independent_two_replicas_per_stage=chain_availability(p, k, 2),
                         perfectly_common_mode_probability=p)
                    for p in [.90, .99] for k in [4, 16, 64]]
    compute = [dict(parameters_billion=p, assumed_active_dense_matmul_gflop_per_token=2 * p,
                    target_tokens_per_second=tps,
                    assumed_active_dense_matmul_tflop_per_second=2 * p * tps / 1000)
               for p in [1, 8, 70, 400] for tps in [1, 5, 10]]
    kv_sensitivity = [dict(context_tokens=context, batch=batch,
                           fp16_kv_gib=kv_bytes(80, 8, 128, context, batch, 2) / GIB)
                      for context in [2048, 8192, 32768, 131072] for batch in [1, 4]]
    pipeline = []
    for name, times in [('balanced', [20, 20, 20, 20]), ('one_5x_straggler', [20, 20, 20, 100])]:
        c = comm_seconds(4, 8192, 2, 20, 20)
        serial = serial_seconds(times)
        pipeline.append(dict(setting=name, stage_compute_ms=times,
                             serial_compute_seconds=serial, serial_communication_seconds=c,
                             ideal_single_request_tps=1 / (serial + c),
                             compute_stage_only_aggregate_tps_ceiling=pipeline_rate_ceiling(times)))
    return dict(weight_floors=floors, memory_sensitivity=memory, communication=comm,
                availability=availability, dense_matmul_budget=compute,
                kv_sensitivity=kv_sensitivity, synthetic_stage_sensitivity=pipeline)


def _csv(rows):
    target = io.StringIO(newline='')
    writer = csv.DictWriter(target, fieldnames=list(rows[0]))
    writer.writeheader()
    for r in rows:
        writer.writerow({k: json.dumps(v) if isinstance(v, list) else v for k, v in r.items()})
    return target.getvalue()


def _svg_bars(title, subtitle, labels, values, unit, color):
    """Small reproducible SVG; no plotting packages or model/hardware calls."""
    width, height, left, right, top, bottom = 920, 420, 105, 38, 90, 72
    graph_w, graph_h = width - left - right, height - top - bottom
    maxval = max(values) * 1.1
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">',
           '<rect width="100%" height="100%" fill="#f8fafc"/>',
           '<style>text{font-family:Arial,sans-serif;fill:#172238}.small{font-size:13px}.label{font-size:15px}</style>',
           f'<text x="24" y="30" font-size="21" font-weight="bold">{html.escape(title)}</text>',
           f'<text x="24" y="54" class="small">{html.escape(subtitle)}</text>']
    for frac in [0, .25, .5, .75, 1]:
        y = top + graph_h * (1 - frac)
        out += [f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" y2="{y:.2f}" stroke="#dbe3ed"/>',
                f'<text x="{left-8}" y="{y+5:.2f}" text-anchor="end" class="small">{maxval*frac:.1f}</text>']
    for i, (label, value) in enumerate(zip(labels, values)):
        slot = graph_w / len(values)
        x = left + slot * i + slot * .2
        h = graph_h * value / maxval
        out += [f'<rect x="{x:.2f}" y="{top+graph_h-h:.2f}" width="{slot*.6:.2f}" height="{h:.2f}" rx="4" fill="{color}"/>',
                f'<text x="{x+slot*.3:.2f}" y="{top+graph_h-h-8:.2f}" text-anchor="middle" class="label">{value:.2f}</text>',
                f'<text x="{x+slot*.3:.2f}" y="{height-bottom+25}" text-anchor="middle" class="label">{html.escape(label)}</text>']
    out += [f'<text x="{left}" y="{height-18}" class="small">{html.escape(unit)}. Calculations only; not observed device or network performance.</text>', '</svg>']
    return '\n'.join(out) + '\n'


def write_outputs(root):
    root = Path(root)
    results = root / 'results'
    figures = root / 'figures'
    results.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    rows = tables()
    package = dict(evidence_kind='analytical_not_measurement', assumptions_version=1,
                   units=dict(memory='GiB = 2^30 bytes', parameters='B = 10^9 parameters',
                              links='Mbps = 10^6 bits/s, one-way latency'),
                   tables=rows)
    (results / 'feasibility_tables.json').write_text(json.dumps(package, indent=2, sort_keys=True) + '\n')
    for name, entries in rows.items():
        (results / ('feasibility_' + name + '.csv')).write_text(_csv(entries))
    summary = ['# Calculated tables', '', 'All values are scenario arithmetic, not measurements. See the paper for assumptions.', '',
               '| Parameter budget | 4-bit GiB | 8-bit GiB | 16-bit GiB |', '|---|---:|---:|---:|']
    for p in [1, 8, 70, 400]:
        values = [r['ideal_weight_gib'] for r in rows['weight_floors'] if r['parameters_billion'] == p]
        summary.append(f'| {p}B | ' + ' | '.join(f'{v:.3f}' for v in values) + ' |')
    summary += ['', '| Stages | 1Gbps / 1ms t/s | 20Mbps / 20ms t/s | 5Mbps / 100ms t/s |', '|---:|---:|---:|---:|']
    for k in [2, 4, 16, 64]:
        values = [r['communication_only_tps_ceiling'] for r in rows['communication'] if r['stages'] == k]
        summary.append(f'| {k} | ' + ' | '.join(f'{v:.3f}' for v in values) + ' |')
    (results / 'feasibility_tables.md').write_text('\n'.join(summary) + '\n')
    (figures / 'feasibility_memory.svg').write_text(_svg_bars(
        'Weight storage grows with parameter budget', 'Nominal 4-bit weights only; no metadata, KV cache, workspace or replicas',
        ['1B', '8B', '70B', '400B'], [float(weight_bytes(p * 10**9, 4) / GIB) for p in [1, 8, 70, 400]], 'GiB', '#4f6aaf'))
    (figures / 'feasibility_communication.svg').write_text(_svg_bars(
        'More serial boundaries reduce the communication ceiling', '70B architecture width; FP16 activations; assumed 20Mbps and 20ms one-way',
        ['2 stages', '4 stages', '16 stages', '64 stages'], [1 / comm_seconds(k, 8192, 2, 20, 20) for k in [2, 4, 16, 64]],
        'Communication-only tokens/s ceiling', '#22816e'))
    return rows


if __name__ == '__main__':
    write_outputs(Path(__file__).resolve().parents[1])
    print('Reproduced analytical tables and SVG figures; no model/device execution.')
