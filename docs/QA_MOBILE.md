# Mobile QA checklist, 390 px (AC-19)

Manual acceptance for the demo path when Playwright is not available in CI. One human fills this in before a release and records the date, the build tag and the result. Automation replaces this file as soon as Playwright runs in CI.

## Setup

1. Build the data: `gate build --out site/`.
2. Serve the folder: `python -m http.server 8000 --directory site`.
3. Open `http://localhost:8000/#/` in a browser with device emulation at **390 x 844** and a device pixel ratio of 3.
4. Reload once with the cache disabled so the first load is measured cold.

## Demo path, three taps (AC-19)

| # | Step | Expected | Pass |
| :--- | :--- | :--- | :--- |
| 0 | Land on `#/` | The headline verdict is the largest text above the fold | [ ] |
| 1 | Tap the decision button | Lands on `#/gates` with the first failing gate expanded | [ ] |
| 2 | Tap the first failing gate row | Lands on `#/evidence` filtered to that gate's failing ids | [ ] |
| 3 | Tap the first scenario card | The failing scenario card is open with metrics and thumbnail | [ ] |

Three taps from the decision to a failing scenario card. A fourth tap anywhere on this path is a failure of the criterion.

## Layout at 390 px

| Check | Expected | Pass |
| :--- | :--- | :--- |
| Horizontal scroll | None on any route | [ ] |
| Gutter | 16 px on both sides, consistent across routes | [ ] |
| Tables | Gate, coverage and regression tables stay readable, wrapping or scrolling inside their own container only | [ ] |
| Ribbon | The demo ribbon is visible above the fold when a loaded suite is not pre registered | [ ] |
| Banner | The permanent banner is readable and not clipped | [ ] |
| Headline | The verdict headline fits without a mid word break | [ ] |
| Buttons | Every tap target is at least 44 x 44 px | [ ] |
| Coverage matrix | Bin cells keep their number legible, colour status still distinguishable | [ ] |
| Case tree | Collapsible nodes open and close, indentation does not push text off screen | [ ] |
| Evidence cards | Thumbnails scale to the column, filters stack rather than overflow | [ ] |
| Limitations | The owner paragraph sits above the fold | [ ] |
| Font | Inter Tight loads from the local subset, no layout shift on load | [ ] |

## Routes

Every route opens directly from a cold load and from a reload:

`#/`, `#/gates`, `#/coverage`, `#/case`, `#/evidence`, `#/limits`, `#/gates?gate=a.hard.ped_collision`, `#/evidence?scenario=<id>`, `#/evidence?track=b`, `#/case?node=g0`.

| Check | Expected | Pass |
| :--- | :--- | :--- |
| Deep link | A pasted deep link opens the same view as navigating there | [ ] |
| Back button | Browser back returns to the previous route | [ ] |
| Missing data | Without `data_b.json` the Track B tab shows the empty state string, no error | [ ] |

## Record

| Field | Value |
| :--- | :--- |
| Date | |
| Build tag | |
| Browser and version | |
| Demo path result | |
| Layout result | |
| Routes result | |
| Notes | |
