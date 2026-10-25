# Reproducible local-process studies

These additive, self-contained snapshots extend the household-capability analysis without replacing the main project's source, results or documentation. Run commands from the selected study directory. These are one-host CPU experiments over local pipes, not household-device or network measurements.

## Transport codecs

[Results](transport-codecs/TRANSPORT_RESULTS.md) · [Protocol](transport-codecs/TRANSPORT_EXPERIMENT.md) · [Figure](transport-codecs/figures/transport_codec_summary.svg)

216 retained paired measurements cover three codecs, two injected-delay conditions, twelve fixed diagnostic prefixes and three timing repetitions. FP16 used roughly half the activation bytes and preserved next-token argmax on all 12 prefixes. This particular whole-tensor/global-scale INT8 codec used roughly one quarter and preserved none. Independent post-hoc frames and arrays associate the loss with an extreme activation outlier setting the scale. This is not a general finding about INT8 or language quality. Injected delays are not real links; repeated timings are not independent quality examples.

## Cached decode

[Results](cached-decode/CACHED_RESULTS.md) · [Protocol](cached-decode/CACHED_EXPERIMENT.md) · [Limitations](cached-decode/CACHED_LIMITATIONS.md) · [Source/failure history](cached-decode/CACHED_STAGE_HISTORY.md)

Both retained 36-row runs exactly reproduce monolithic FP32 logits, greedy tokens, reset/replay and one another, with stage-local KV caches. The split is slower on median decode. A roughly 2.4 KB logical boundary frame is not whole-application traffic: full-vocabulary audit-logit return raises summed application frames to roughly 202 KB per decode. Neither figure is network-wire traffic. No speedup or total-memory saving is established.

## Validate without inference

From either study directory:

```sh
python -m unittest discover -s tests -v
```

From `studies/cached-decode`:

```sh
python -m mesh.cached_verify cached_runs/retained-v4-001 cached_runs/retained-v4-002
```

Default Python may skip NumPy and real-model optional tests. A skip is not a pass. The original cached archive omitted an atlas required by an inherited test; this integration supplies that byte-identical document from the transport snapshot.

## Optional model reproduction

Use Python 3.10+ and an existing compatible local environment: PyTorch 2.5.1 CPU, Transformers 4.46.3, NumPy 2.3.5 and safetensors 0.4.5. Pins are in each `requirements-pretrained.txt`; model preparation is documented in `PRETRAINED_EXPERIMENT.md`. No weights are bundled. The pinned model is HuggingFaceTB/SmolLM2-135M-Instruct revision `12fd25f77366fa6b3b4b768ec3050bf629380bac`; its config and safetensors hashes are verified by the loader. Substitute your local directory for `PINNED_LOCAL_MODEL`; recorded absolute paths are historical provenance, not required locations.

```sh
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
```

From `studies/transport-codecs`, choose a fresh output file:

```sh
( set -C; python -m mesh.transport_experiment --model-dir PINNED_LOCAL_MODEL --opt-in > NEW_TRANSPORT_RESULT.json )
```

Never overwrite the bundled results. Abrupt interruption can lose the transport runner's in-memory samples. From `studies/cached-decode`, use new output directories:

```sh
python -m mesh.cached_experiment --output NEW_CACHED_RUN_1 --model-dir PINNED_LOCAL_MODEL --source-hashes cached_checkpoints/v4/source_hashes.json --opt-in
python -m mesh.cached_experiment --output NEW_CACHED_RUN_2 --model-dir PINNED_LOCAL_MODEL --source-hashes cached_checkpoints/v4/source_hashes.json --opt-in
python -m mesh.cached_verify NEW_CACHED_RUN_1 NEW_CACHED_RUN_2
```

Both require explicit opt-in and at least 3 GiB available memory at their resource gate. Sampling/cooperative checks are not an OS memory cap. Artifact verification requires no inference, download, installation or network/device setup.

## Integrity and historical material

`PUBLICATION_SHA256.json` is the authoritative integrated-tree inventory, excluding itself. Run `python verify_publication.py` from this directory. Original manifests remain unchanged as archive provenance, not current publication inventories. `PACKAGE_ADAPTATIONS.json` records editorial-only package-document cleanup, omission of a non-scientific handoff, and added inherited documentation. Scientific source, tests, frozen protocols, arrays, results and failure checkpoints remain unchanged. Prospective status wording inside protocols describes that historical checkpoint, not the completed result.

The transport snapshot includes historical household/pretrained results. Cached inherited reports are background/dependencies, not cached-decode outcomes. Current main-project material remains at repository root; study-local READMEs describe historical snapshots.

## Integration validation (2026-10-22)

The prepared standalone directories were tested again without model inference. Transport: 67 tests discovered, 64 passed and 3 optional model tests skipped in the pinned environment; default runtime: 61 passed, 6 skipped. Cached: 81 discovered, 78 passed and 3 skipped in the pinned environment; default runtime: 75 passed, 6 skipped. Historical prose saying “81 tests passed” should be read as 81 discovered, not 81 executed passes. All suites completed without errors after supplying the missing inherited atlas. The independent artifact checker verified both retained 36-row runs, 72 logit files per run, exact greedy/reset/cross-run bytes. All 44 cached v4 frozen source entries were verified. The integration reran no model inference.
