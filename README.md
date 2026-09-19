# assurance-gate

Evaluation results in, release decision out.

[[OWNER_COPY: repo summary]]

## What it does

The tool reads evaluation results and returns one verdict per candidate: GO, NO GO or CONDITIONAL. Gates are written down before the run and frozen by a hash of the gate file. A threshold cannot move after a result is known, and any later change is recorded as a deviation next to the frozen value.

Every verdict ships with the evidence behind it. The dashboard shows each gate with its count, its rate, its confidence bound and its margin. It also shows the coverage matrix, the paired regression against a baseline, an assurance case tree and the residual risk that no gate covers.

## Two tracks

Track A reads driving scenario results from a simulation suite. Gates cover collisions, time to collision, minimum distance, severity tiers, availability, coverage and regression.

Track B reads language model safety evaluations produced with Inspect. Gates cover harmful compliance on unsafe prompts, over refusal on safe prompts and category coverage.

## Install

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

The Track B extra pulls the evaluation runtime:

```bash
.venv/bin/pip install -e ".[trackb,dev]"
```

## Commands

```bash
gate preregister --track a --suite holdout   # freeze and publish the gate hash
gate ingest --track a --suite holdout --from <results> --candidate <name>
gate run --track b --config configs/track_b.yaml --dry-run
gate build --out site/                       # write data.json and the dashboard
gate publish --tag v1.0 --dry-run            # show every upload without doing it
```

`gate build` is deterministic. Two runs over the same inputs write the same bytes.

## Repository layout

| Path | Holds |
| :--- | :--- |
| `gates/` | gate files per track, frozen and hashed |
| `configs/` | coverage bin edges and the Track B run configuration |
| `runs/` | ingested suites with results, manifests and thumbnails |
| `site/` | the static dashboard and the built data files |
| `space/` | the card for the hosted dashboard |
| `dataset/` | the card for the published run dataset |
| `scripts/` | the copy linter and the fixture generator |

## Provenance

Each suite carries a manifest with a run id, a timestamp, the gate file path, the gate file hash, the seed, the tool versions and the number of results. A suite whose gates were written after the run is marked as not pre registered, and the dashboard says so on every page.

## Copy linter

```bash
python scripts/lint_copy.py --mode push
python scripts/lint_copy.py --mode release
```

Push mode allows owner copy placeholders. Release mode treats them as errors. Both modes run a stealth grep over everything that ships, so no employer name, product name or personal detail reaches a published file.

## Limitations

[[OWNER_COPY: limitations]]

## License

Apache License 2.0. See `LICENSE`.
