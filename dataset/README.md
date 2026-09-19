---
license: cc-by-4.0
task_categories: []
pretty_name: Assurance Gate runs
---

# Assurance Gate runs

The evaluation records behind the Assurance Gate dashboard.

[[OWNER_COPY: dataset summary]]

## What is in here

| Path | Holds |
| :--- | :--- |
| `runs/<suite>/<candidate>/results.json` | one public record per scenario |
| `runs/<suite>/<candidate>/manifest.json` | provenance for that candidate and suite |
| `preregistration/<track>-<suite>.json` | the frozen gate hash and where it was published |
| `README.md` | this card |

Every file is JSON with sorted keys. Floats are rounded to four decimals. Paths, host names and addresses are removed before upload.

## Result record

One record per scenario, Track A.

| Field | Type | Meaning |
| :--- | :--- | :--- |
| `scenario_id` | string | stable id of the scenario |
| `family` | string | scenario family |
| `planner` | string | the candidate under test |
| `suite` | string | the suite the scenario belongs to |
| `duration_s` | number | simulated duration |
| `n_steps` | integer | simulation steps |
| `score` | number | scenario score |
| `severity_tier` | string | nominal, near miss or critical |
| `metrics` | object | surrogate safety metrics, listed below |
| `parameters` | object | the drawn family parameters used for coverage |
| `description` | string | the scenario description from its definition |
| `thumbnail` | string or null | relative path to a bird eye view image |

Metrics: `ttc_min_s`, `ttc_min_t_s`, `pet_min_s`, `d_min_m`, `d_min_t_s`, `collision`, `collision_t_s`, `delta_v_mps`, `severity_index`, `hard_brake_events`, `hard_brake_fraction`, `mean_speed_ratio`. A metric that the source run did not produce is null, and a gate that needs it counts the record as unscorable.

The trajectory log never leaves the private run. A test asserts that it appears in no published file.

## Sample record

One record per evaluation sample, Track B.

| Field | Type | Meaning |
| :--- | :--- | :--- |
| `sample_id` | string | id of the sample in the evaluation log |
| `task` | string | the task the sample belongs to |
| `model` | string | the model under test |
| `category` | string | the hazard or prompt category |
| `target_label` | string or null | safe or unsafe, where the task defines it |
| `score` | number | the scorer value |
| `compliant` | boolean or null | whether the model complied with an unsafe request |
| `refused` | boolean or null | whether the model refused a safe request |
| `unscorable` | boolean | true when the output was cut off or the score is missing |
| `completion_public` | string | the completion, truncated where publishing it in full would be harmful |
| `inspect_ref` | string | a link into the evaluation log bundle |

## Manifest

| Field | Meaning |
| :--- | :--- |
| `run_id` | suite, candidate and timestamp |
| `suite` | the suite name |
| `track` | a or b |
| `candidate` | the candidate under test |
| `baseline` | the candidate it is compared against |
| `generated_at` | when the run finished, UTC |
| `preregistered` | whether the gates were frozen before the run |
| `gate_file` | which gate file applied |
| `gate_file_sha256` | the hash of that file |
| `gate_published_at` | when the hash went public, per channel |
| `seed` | the seed the suite was drawn with |
| `tools` | versions of every tool in the chain |
| `n_results` | how many records the run produced |
| `notes` | free text |

## Provenance

A suite is pre registered when the gate file hash was published before the run started. The publication record names a release and a dataset commit with their timestamps. A suite marked as not pre registered is still published, and it is labelled as such everywhere it appears.

## License

The records are released under the Creative Commons Attribution 4.0 license. The tool that produced them is released under the Apache License 2.0.
