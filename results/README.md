# Recorded runs

Recorded on 18 October 2026 using the implementation in this repository. The tables retain every completed trial in the fresh comparison batch. Demonstration clips are selected excerpts; these results are the comparison sample.

**Evaluation in progress: 13 of 15 trials complete.** Pending trials below have no reported outcome yet.

## Full-lap time trials

| Track | Model | Outcome | Game seconds | Rescue presses |
|---|---|---|---:|---:|
| Hacienda | Kettei Fat | 300-second cap | 300.0 | 4 |
| Hacienda | Jev 1.14 | API failure (HTTP 529) | 277.2 | 13 |
| Lighthouse | D1 Ultra | Finished | 161.8 | 57 |
| Lighthouse | Kettei Fat | Finished | 74.0 | 4 |
| Lighthouse | Jev 1.14 | Finished | 131.6 | 23 |
| Oliver's Math Class | D1 Ultra | 300-second cap | 300.0 | 194 |
| Oliver's Math Class | Kettei Fat | Finished | 80.4 | 9 |
| Hacienda | D1 Ultra | Pending | — | — |
| Oliver's Math Class | Jev 1.14 | Pending | — | — |

One trial per model per track is a small descriptive sample. The harness was selected for Fat and applied unchanged to the other providers; it is not a provider-specific optimization contest.

## Shared-world head-to-head races

**The six initial 1v1 comparisons and their win claims are withdrawn.** A native-camera audit found that explicit camera slots followed race position and could switch karts after an overtake. It also found a 2.67:1 camera projection rendered into 1.33:1 frames. These runs cannot establish a fair model comparison. Corrected camera capture must pass ownership and aspect-ratio checks before new races are reported.

| Track | Fat starting slot | Winner | Game seconds | Fat / Jev rescue presses |
|---|---:|---|---:|---:|
| Hacienda | 1 | Excluded: camera capture | 132.8 | 3 / 5 |
| Hacienda | 2 | Excluded: camera capture | 300.0 | 910 / 285 |
| Lighthouse | 1 | Excluded: camera capture | 91.2 | 8 / 46 |
| Lighthouse | 2 | Excluded: camera capture | 300.0 | 1128 / 77 |
| Oliver's Math Class | 1 | Excluded: camera capture | 77.0 | 10 / 10 |
| Oliver's Math Class | 2 | Excluded: camera capture | 300.0 | 1333 / 30 |

The machine-readable file retains the original observed outcomes for audit, explicitly marks all six runs ineligible, and reports no comparison winners. The single-player time trials and randomized-start checks use one player camera and are separate from this two-player capture defect.

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
