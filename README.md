# Skráningartafla – pyRevit export

Fills in the HMS skráningartafla (útgáfa 5.03) straight from the Revit model.
It writes a copy of the official template, so the macros still work: open the
file in Excel, run the villutékk on Einingar and press **Reikna** on Forsíða.

## Install

From GitHub (recommended), in a command prompt:

```
pyrevit extend ui Skraningartafla https://github.com/<user>/<repo>.git
```

then reload pyRevit. Update later with `pyrevit extensions update Skraningartafla`.

Or from a local copy: pyRevit tab → Settings → Custom Extension Directories → Add
the folder that **contains** `Skraningartafla.extension` → Save & Reload.

A **Skráningartafla** tab appears with five buttons:

| Button | What it does |
|---|---|
| **Flytja út skráningartöflu** | Runs the checks, then fills the HMS template (`.xlsm`) |
| **Yfirlit rýma** | Raw overview in a plain `.xlsx` (values, no formulas) for filling the table by hand and double-checking the automatic export |
| **Búa til færibreytur** | Adds the `SKR_` shared parameters (run once per project) |
| **Yfirfara skráningu** | Runs the checks and shows the summary. Writes nothing |
| **Stillingar** | Opens the settings JSON: parameter names, Area Scheme, template, room keywords |

## How the model maps to the table

**Each rýmislína is one Area** in the Area Scheme `Skráning` (you can change the
scheme name in Stillingar, or choose a scheme when you export). You can also
choose Rooms instead, where each Room is one line.

| Column | Comes from |
|---|---|
| D0 Lokun | `SKR_Lokun` (A/B/C, empty = A) |
| D1 Rými | Area **Number** (0101, 0102…) |
| D2 Notkun | Area **Name** |
| D3 Höfuðflokkun | `SKR_Hofudflokkun` (N U T B F V S) |
| D4 Eignarhald | `SKR_Eignarhald` (0101 / X / Y / Y1…) |
| D5 Botnflötur | Area area, or `SKR_Botnflotur`. Goes in **D5M** when `SKR_Milliflotur` is ticked |
| D6 / D7 / D9 | `SKR_Stigar`, `SKR_Op`, `SKR_Undir180` |
| D10a / D10b | `SKR_SalarhaedMin/Max`. If these are empty: `SKR_SalarhaedHaedar` on the Level, otherwise the height from this level to the next |
| D11 Brúttórúmmál | `=ROUND(D5 × mean salarhæð, 1)` (A and B lines, not svalir) |
| D12 Nettóflötur | Sum of the **Rooms** whose location point is inside the Area, written as `=10.9+3.6+…` the way you do it by hand. `SKR_Nettoflotur` overrides it |
| D8, D13, D14, D15 | Formulas, as in the Skólahvarf table (you can turn this off with `fylla_reiknada_dalka`) |
| D16 Upphitað | `SKR_Upphitad` (mælir 1, 2…) |
| T–AC room counts | The Rooms inside each Area, sorted by name (stofa, svefnherbergi, bað…; you can edit the keywords) |
| E-lines | **Parking** elements standing inside a B line with Y/X ownership. The number comes from **Mark** (B01…) |

The other sheets:

- **Forsíða**: comes from Project Information: Project Name (or `SKR_Heiti`), `SKR_Landeignanumer`,
  `SKR_Stadgreinir`, `SKR_Matshlutanumer`, `SKR_FjoldiMatshluta`, `SKR_Skrasetjari`,
  `SKR_Kennitala`. The date is today's date.
- **Hæðir**: one row per floor. The number and name come from `SKR_Haednumer` / `SKR_Haedarheiti` on
  the Level, or else from the first two digits of the rýmisnúmer. Botnflötur and rúmmál are summed over the A lines.
- **Matshluti**: lóð comes from `SKR_Lod`. Botnplata is the lowest floor's A botnflötur, with m³ = m² × 0.2.
  Útveggir, op, þak and þakop are **estimated** from exterior walls, windows, doors and roofs, so always check them.
  Efsti kóti and ummál come from `SKR_EfstiKoti` and `SKR_Ummal`.
- **Sameign_sumra**: put `SKR_SameignSumra` on the **eignarlína** (the line where rými = eignarhald),
  e.g. `Y1` or `Y; Y1`. The rule is S by default, J for bílastæði / B lines, or you can write it
  explicitly as `Y1:P`. Bílastæði get the Y of the garage they stand in.
- **Athugasemdir**: comes from `SKR_Athugasemdir` on Project Information, one line per comment.

## Yfirlit rýma (raw overview)

A normal `.xlsx` with filters and frozen headers. Sheets:

- **Rýmislínur**: the lines exactly as *Flytja út* calculates them (D0–D16), as numbers, plus the room areas that make up each nettóflötur
- **Eignir**: sums per eignarhald (flötur A/B/C, nettó, rúmmál, birt)
- **Herbergi**: every Room: level, number, name, area, perimeter, height, volume, department, which Area it falls in, the SKR_ values and status (not placed / not enclosed)
- **Svæði**: every Area in every Area Scheme, with the rooms inside it and their sum
- **Hæðir**: every Level: elevation, height to the next level, Building Story, room and area totals
- **Stigar og op**: stairs (footprint of runs and landings, or a rough bounding box), shafts and floor openings with their area, to help fill D6/D7 by hand
- **Bílastæði**: every Parking element with its Mark and the Area it stands in

## Checks (Yfirfara)

- duplicate or badly formatted rýmisnúmer
- lokun or höfuðflokkun that isn't allowed
- eignarhald that points to a line that doesn't exist, and Y0
- a bílgeymsla whose eignarhald isn't its own number
- svalir/verönd that aren't S
- salarhæð or nettóflötur missing
- Rooms that aren't inside any Area
- Y codes with no owner
- bílastæði without a number

Every message links to the element in Revit.

## Tests

`python tests/test_core.py` runs in plain Python (no Revit). The table logic was
also checked against the Skólahvarf 2-4 table. All 132 lines and all 46
Sameign_sumra lines come out the same. The only differences are where the
original has hand-entered values (the top-floor stigahús) or a salarhæð with 3 decimals (2.845).
