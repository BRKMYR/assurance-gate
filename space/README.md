---
title: Assurance Gate
emoji: 🚧
sdk: static
app_file: index.html
pinned: false
license: apache-2.0
---

# Assurance Gate

Evaluation results in, release decision out.

[[OWNER_COPY: space summary]]

## What this Space shows

The page is a static dashboard over one build of the gate. It opens on the decision: one verdict per candidate, the count of gates that failed, and the names of those gates. Every other page exists to let a reader check that verdict.

| Page | Answers |
| :--- | :--- |
| Decision | what the verdict is and which gates drove it |
| Gates | how each gate was measured, with its bound, its threshold and its margin |
| Coverage | which parameter ranges were tested and which cells are empty |
| Assurance case | how the claims hang together, down to the evidence |
| Evidence | the individual scenarios and samples behind every number |
| Limitations | what the suite cannot see and what risk is left |

## How to read it

A rate gate passes on a confidence bound rather than on the point estimate. A run of sixteen scenarios with fourteen passes gives a point estimate of 0.875 and a lower bound near 0.62. A threshold of 0.60 clears on the bound. A threshold of 0.70 does not, even though the point estimate sits above it.

Gates are frozen before a run. The gate file hash is published, and the dashboard shows the publication time against the first run time. A grey ribbon marks any suite whose gates were written after the run, because such a result carries less weight.

## Data

The runs behind this page are published as a dataset. Results, manifests and the pre registration records travel together, so anyone can recompute the verdict from the raw records.

## Limitations

[[OWNER_COPY: space limitations]]
