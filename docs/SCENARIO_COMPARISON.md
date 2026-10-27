# Compare your own explicit placements safely

The standard-library wrapper below validates an entire scenario before producing
any result. It does not discover devices, measure rates, open sockets, run a model,
or change files. All capacities and rates are assumptions supplied by you.

From the repository root (Python 3.10+):

```sh
python -B tools/compare_scenario.py examples/illustrative.json
python -B -m unittest discover -s tests -p 'test_compare_scenario.py' -v
```

You can copy `examples/illustrative.json` to a new path and edit its explicit
budgets, rates, stages and named placements. The script also works from another
working directory when given its absolute path and the scenario's absolute path.
It prints JSON to stdout; redirect only to a **new** output path, never a retained
result. No historical results or frozen study sources are changed by this tool.

## Input contract

- The root is a JSON object. `devices`, `stages` and `placements` are nonempty
  arrays of objects. `links` is an optional array (empty means no transfers are
  available between different devices).
- Devices have unique nonempty string `id`, positive finite `memory_bytes` and
  `ops_per_second`, and optional boolean `consent`. Missing or false consent
  denies selection; it does not prove anything about real-world consent.
- Stages have unique nonempty string `id` and finite nonnegative `operations`,
  `weights_bytes`, `workspace_bytes`, `output_bytes`.
- Placements have unique nonempty string `name` and a `devices` array naming
  exactly one known device for each stage in order.
- Links have known string `source` and `target`, positive finite
  `bytes_per_second` and nonnegative finite `latency_ms`. Directed endpoint pairs
  must be unique; no reverse link is inferred.
- Numeric booleans, duplicate JSON keys and nonstandard `NaN`/`Infinity` are
  rejected. Every record is validated, including unselected devices. Extremely
  large numbers that cannot enter the finite floating-point model are rejected.
  Extra metadata fields are permitted but ignored by the model.

Malformed inputs exit **2**, print a field-oriented error to stderr, and emit
nothing to stdout. Structural mistakes (including unknown device IDs) are input
errors, not resource infeasibility. A valid scenario exits **0**, even if no
placement is feasible: inspect both `feasible` and `rejected`. Insufficient memory,
missing consent and missing directed links are per-placement rejections. Finite
inputs that overflow the analytical result cause an error, not partial output.

## What the output means

The existing `kind`, `feasible` and `rejected` fields retain the original model's
semantics. Feasible placements are sorted by analytical total latency, with stable
input order for ties. `scenario_sha256` hashes the exact UTF-8 input bytes (including
whitespace), allowing you to distinguish inputs; retain the input and repository
commit alongside output for reproduction. The digest is provenance, not a
signature, authentication or a proof the assumptions describe your devices.

`evidence_kind` is always `assumption_conditional_not_measurement`. Even a feasible
placement is only feasible under the current serial model: resident stage weights
plus a per-device maximum transient reserve, declared operations/rates, and
specified direct transfers. It does not validate actual kernels, available RAM,
thermal limits, model quality, service security or real-network performance.

This is an additive entry point: `python -m mesh simulate` and all historical study
freezes remain unchanged. Prefer this validated wrapper for newly edited inputs.
