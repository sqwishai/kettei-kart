# Recorded runs

Recorded on 18 October 2026 using the implementation in this repository. The tables retain every completed trial in the fresh comparison batch. Demonstration clips are selected excerpts; these results are the comparison sample.

**Evaluation in progress: 9 of 15 trials complete.** Pending trials below have no reported outcome yet.

## Full-lap time trials

| Track | Model | Outcome | Game seconds | Rescue presses |
|---|---|---|---:|---:|
| Hacienda | Jev 1.14 | API failure (HTTP 529) | 277.2 | 13 |
| Lighthouse | Kettei Fat | Finished | 74.0 | 4 |
| Lighthouse | Jev 1.14 | Finished | 131.6 | 23 |
| Hacienda | D1 Ultra | Pending | — | — |
| Hacienda | Kettei Fat | Pending | — | — |
| Lighthouse | D1 Ultra | Pending | — | — |
| Oliver's Math Class | D1 Ultra | Pending | — | — |
| Oliver's Math Class | Kettei Fat | Pending | — | — |
| Oliver's Math Class | Jev 1.14 | Pending | — | — |

One trial per model per track is a small descriptive sample. The harness was selected for Fat and applied unchanged to the other providers; it is not a provider-specific optimization contest.

## Shared-world head-to-head races

Across 6 completed races: **Kettei Fat 3 wins; Jev 1.14 0 wins; 3 without a sole winner.**

| Track | Fat starting slot | Winner | Game seconds | Fat / Jev rescue presses |
|---|---:|---|---:|---:|
| Hacienda | 1 | Kettei Fat | 132.8 | 3 / 5 |
| Hacienda | 2 | No finisher | 300.0 | 910 / 285 |
| Lighthouse | 1 | Kettei Fat | 91.2 | 8 / 46 |
| Lighthouse | 2 | No finisher | 300.0 | 1128 / 77 |
| Oliver's Math Class | 1 | Kettei Fat | 77.0 | 10 / 10 |
| Oliver's Math Class | 2 | No finisher | 300.0 | 1333 / 30 |

Both starting slots are tested on each track. These six races describe this batch; they do not establish a universal win rate. A model still driving when its opponent finishes is a race loss, not a failed solo lap.

## Randomized-start checks

| Track | Finished / starts | Mean seconds after takeover | Mean rescue presses |
|---|---:|---:|---:|
| Lighthouse | 4 / 4 | 73.2 | 5.5 |
| Oliver's Math Class | 3 / 3 | 119.5 | 18.7 |
| Hacienda | 3 / 3 | 204.2 | 6.3 |
| Zen Garden | 2 / 2 | 84.0 | 10.5 |
| Snow Peak | 2 / 2 | 155.3 | 24.5 |

Randomized setup applies 54–84 straight ticks, 3–6 gentle steering ticks and 6–15 straight ticks, selected deterministically from each recorded seed before model takeover. Zen Garden and Snow Peak were held out from prompt development. These completion-to-finish times start after setup and cannot be compared directly with standing-grid lap times.

## Reproduce a comparison

Use the commands in the [main README](../README.md), the provider credentials, track IDs and seeds in [results.json](results.json). Each run writes the full decision trace, exact camera images, probabilities and source hashes. API nondeterminism and later provider builds can change the drive even when the simulator seed is unchanged.

Every model sees only ordinary player-camera images, public driving instructions and its own action history. Engine coordinates, speed and route geometry are evaluation data only. The simulation pauses during API calls, and videos play at game speed. Display names above karts are added in verified replay; they were not added to the recorded model inputs.

Game times count the controlled simulation ticks after the fixed countdown. Rescue counts are presses of the normal rescue key, including repeated requests. A 300-second cap is distinct from an API error. The source hashes and decision-trace hashes are retained in the machine-readable result file.
