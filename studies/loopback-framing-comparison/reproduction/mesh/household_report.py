"""Reproduce household scenario JSON/CSV from cited assumptions, without devices."""
import csv
import json
from pathlib import Path

from .household import GIB, memory_estimate, kv_cache_bytes, communication_floor

ROOT = Path(__file__).resolve().parents[1]


def build_rows(assumptions):
    rows = []
    model_source = next(source for source in assumptions['sources'] if source['id'] == 'llama_paper')
    for model in assumptions['models']:
        kv = kv_cache_bytes(layers=model['layers'], kv_heads=model['kv_heads'], head_dim=model['head_dim'],
                            context_tokens=assumptions['context_tokens'], element_bits=assumptions['kv_bytes_per_element'] * 8,
                            batch=assumptions['concurrent_sequences'])
        for budget in assumptions['household_memory_budgets_gib']:
            for bits in assumptions['weight_bits']:
                estimate = memory_estimate(parameters=int(model['parameters_billion_rounded'] * 1_000_000_000),
                    weight_bits=bits, household_available_gib=budget,
                    weight_overhead_fraction=assumptions['illustrative_weight_overhead_fraction'], kv_bytes=kv,
                    runtime_reserve_bytes=assumptions['illustrative_aggregate_extra_workspace_gib'] * GIB)
                rows.append({'model': model['label'], 'parameters_billion_rounded': model['parameters_billion_rounded'],
                    'household_available_gib_assumed': budget, 'nominal_weight_bits': bits,
                    'weight_only_gib': estimate['weight_bytes']/GIB, 'kv_gib': kv/GIB,
                    'illustrative_envelope_gib': estimate['adjusted_model_bytes']/GIB,
                    'weight_only_household_lower_bound': estimate['weight_only_households'],
                    'illustrative_envelope_households': estimate['adjusted_households'],
                    'precision': f'{bits}-bit nominal weights; FP16 KV cache',
                    'sourceURL': model_source['url'], 'sourceDate': model_source['observed'],
                    'measured': False, 'advertised': False, 'assumed': True, 'unknown': False,
                    'inference_feasibility': 'not established', 'consent': 'all participating devices fully informed and consenting'})
    return rows


def communication_rows():
    rows = []
    # Sensitivity cases, NOT measured US household links or source-paper settings.
    links = [('100 Mbps / 5 ms',100,5), ('20 Mbps / 20 ms',20,20), ('5 Mbps / 50 ms',5,50)]
    for label, rate, latency in links:
        for homes in range(2,65):
            result = communication_floor(households=homes, hidden_size=8192, activation_bits=16,
                                         payload_mbps=rate, one_way_ms=latency, context_tokens=8192)
            rows.append({'households': homes, 'link_scenario': label, 'payload_mbps_assumed': rate,
                'one_way_ms_assumed': latency, **result,
                'sourceURL':'https://arxiv.org/html/2407.21783v3#S3.T3', 'sourceDate':'2024',
                'precision':'FP16 intermediate activation, no compression',
                'measured':False, 'advertised':False, 'assumed':True, 'unknown':False,
                'source_scope':'Model hidden size only; network settings are hypothetical sensitivity assumptions'})
    return rows


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    assumptions=json.loads((ROOT/'data/household/scaling_assumptions.json').read_text())
    atlas=json.loads((ROOT/'data/household/device_evidence.json').read_text())
    output=ROOT/'results/household'
    output.mkdir(parents=True,exist_ok=True)
    rows=build_rows(assumptions)
    communications=communication_rows()
    (output/'memory_scenarios.json').write_text(json.dumps(rows,indent=2)+'\n')
    write_csv(output/'memory_scenarios.csv', rows)
    (output/'communication_scenarios.json').write_text(json.dumps(communications,indent=2)+'\n')
    write_csv(output/'communication_scenarios.csv', communications)
    flat=[]
    for device in atlas['devices']:
        row=dict(device)
        row['urls']='; '.join(row['urls'])
        flat.append(row)
    write_csv(output/'device_atlas.csv',flat)
    print(f'Regenerated {len(rows)} capacity scenarios, {len(communications)} communication scenarios and {len(flat)} device evidence rows. No device access.')


if __name__=='__main__':
    main()
