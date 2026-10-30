# Cut-service CSV exports

**Draft requirements.** This guide describes the planned exports for
ZAGENZAGEN and OPMAATZAGEN. The export commands and files are not implemented
yet. Provider selection happens outside the CSV where the provider requires
it.

## Shared export rules

- Export rectangular stock blanks. The CSV does not claim that provider
  software will perform the cabinet's remaining machining.
- Keep the full blank envelope separate from the finished cabinet geometry.
  An operation that a provider CSV cannot express does not remove the blank
  row. Its full machining record remains in the existing assembly report.
  This export adds no remaining-work CSV or sidecar.
- Keep each part's grain direction separate from the grain direction of the
  stock sheet. Never infer part grain from the larger blank dimension.
- Keep dimension order from the part's resolved local axes. `Length` can be
  less than `Width` when the part grain follows the shorter axis. Do not rotate
  or mirror a part to make `Length` the larger number.
- Group output by local material ID, panel type, and thickness. A provider
  material selection, when configured, is outer import context; the service
  selection fields are not in these CSVs. A supplier SKU mapping is optional.
- Preserve source part IDs and assembly links in the internal export model.
  Write one row per resolved part record, with its actual stock quantity.
  `Naam` and `Eigen kenmerk` are label fields. Use a safe stable part code as
  the label and keep the full source ID internally. Keep stock quantities
  separate from any optional assembly split code.
- Keep unknown material or grain visible as unresolved data. Local material
  IDs are enough to form groups; a provider SKU is not required. For a
  provider material known to require a direction, do not guess a missing
  grain axis. Continue with other valid rows when one row needs review.
- Do not infer a 2 mm bevel, 45-degree mitre, edge-band product, or edge-band
  thickness from geometry or edge color. Current Space edge color is display
  data; it is not a provider finish order.
- Keep provider product selection lightweight. A declared material-to-provider
  selection mapping is optional; the export does not require a full supplier
  catalog integration or a network lookup.

## ZAGENZAGEN

The supplied example is UTF-8 without BOM, LF line endings, semicolon
separators, and no quoting. Its exact header is:

```text
Naam;Aantal;Lengte;Breedte;LV;LA;BL;BR
```

The sample rows are:

```text
Voorbeeld paneel 1;1;2530;760;7;7;7;7
Voorbeeld paneel 2;3;230;750;7;7;;
```

Live CSV help confirms numeric edge codes from 1 to 9. These codes mean:

| Code | Confirmed live meaning |
| --- | --- |
| `1` | Upper 2 mm chamfer |
| `2` | Lower 2 mm chamfer |
| `3` | Upper and lower 2 mm chamfer |
| `4` | Upper R3 rounding |
| `5` | Lower R3 rounding |
| `6` | Upper and lower R3 rounding |
| `7` | Edge gluing |
| `8` | Upper 45-degree mitre |
| `9` | Lower 45-degree mitre |

The example CSV uses numeric `7`. The `svg7` text in the supplied rich text is
not the CSV spelling.

The live panel-entry guidance says that `Lengte` follows grain for directional
material. It also states that the service uses 10 mm perimeter stock cleanup
and 6 mm saw kerf. These are provider nesting settings, not per-part
allowances to add to exported dimensions.

One selected material applies to a cutting list. A live limit is 500 panels;
the source does not say if this means rows or physical quantity. The export
must use the conservative limit `sum(Aantal) <= 500` and split a larger group
across lists. Live guidance says edge gluing is limited to opposing sides.
It gives 70 × 200 mm as a minimum example, not a universal product rule.

**Draft edge mapping:** the supplied diagram expands `LV` as Lengte Voor,
`LA` as Lengte Achter, `BL` as Breedte Links, and `BR` as Breedte Rechts.
Using the signed panel basis below, map `LV` to `v = 0`, `LA` to `v = Width`,
`BL` to `u = 0`, and `BR` to `u = Length`. Confirm the signed orientation with
an asymmetric panel fixture before implementation. Do not assume that `LV`
means the same edge as OPMAATZAGEN's `Long side 1`.

**Open format questions:** the sample does not define required fields, numeric
precision, valid ranges, and blank-row rules. It sets code `7` on all four
edges, while live guidance limits edge gluing to opposing sides. Treat the
sample as a syntax example; do not use it to infer finish eligibility.
One-edge gluing is also not confirmed. Do not export an explicitly requested
finish until its eligibility is clear. A blank with no requested provider
finish remains exportable.

## OPMAATZAGEN

The workbook instructions say to select the material and thickness outside
the CSV, use millimetres, and import rectangles only. Live CSV guidance says
to use a comma-separated CSV and skip the first row as a header. Material,
thickness, and purchase type are selected in the import UI. The exact ordered
Import headers are:

```text
Aantal,Lengte (mm),Breedte (mm),Eigen kenmerk,Afwerking zijdes,Afwerking type
```

The workbook's edge-side choices are:

- `Long side 1`
- `Long side 2`
- `Short side 1`
- `Short side 2`

Its full finish-type list is:

| Finish type | Workbook value |
| --- | --- |
| Rounding off top, 2 mm | `Rounding off top - 2mm` |
| Rounding off top, 4 mm | `Rounding off top - 4mm` |
| Rounding off top, 6 mm | `Rounding off top - 6mm` |
| Rounding off bottom, 2 mm | `Rounding off bottom - 2mm` |
| Rounding off bottom, 4 mm | `Rounding off bottom - 4mm` |
| Rounding off bottom, 6 mm | `Rounding off bottom - 6mm` |
| Rounding off top and bottom, 2 mm | `Rounding off top and bottom - 2mm` |
| Rounding off top and bottom, 4 mm | `Rounding off top and bottom - 4mm` |
| Rounding off top and bottom, 6 mm | `Rounding off top and bottom - 6mm` |
| Bevelling top, 2 mm | `Bevelling top - 2mm` |
| Bevelling top, 3 mm | `Bevelling top - 3mm` |
| Bevelling top, 4 mm | `Bevelling top - 4mm` |
| Bevelling bottom, 2 mm | `Bevelling bottom - 2mm` |
| Bevelling bottom, 3 mm | `Bevelling bottom - 3mm` |
| Bevelling bottom, 4 mm | `Bevelling bottom - 4mm` |
| Bevelling top and bottom, 2 mm | `Bevelling top and bottom - 2mm` |
| Bevelling top and bottom, 3 mm | `Bevelling top and bottom - 3mm` |
| Bevelling top and bottom, 4 mm | `Bevelling top and bottom - 4mm` |
| Matching edge band, 1 mm | `Edge band matching - 1mm` |

The available finishes depend on material and thickness. The workbook does not
show all supplier products. The `3D example and translations` sheet labels
the horizontal edges `Long side 1` and `Long side 2`, and the vertical edges
`Short side 1` and `Short side 2`.

Live manual entry permits multiple selected side chips. This does not define
the CSV syntax for multiple sides or mixed finishes. Until the provider
confirms that syntax, do not guess a separator and do not duplicate a panel
row or quantity to represent extra edges. A plain blank remains exportable.
If the design explicitly requests an OPMAATZAGEN finish that the CSV cannot
represent with confirmed syntax, keep that finish in the existing assembly
report and mark only that export row unresolved.

## Orientation and part grain

`PartGrain` is separate from stock-sheet grain. It is keyed by canonical
resolved part ID and stores an axis in the canonical resolved part-local XYZ
frame: `x`, `y`, `z`, or `none`.
Omitted grain resolves to `unknown`, not to the largest panel dimension.
`none` means the material has no directional grain. Persist this metadata with
the project and show the saved value after reload. Keep the axis tied to the
part's local frame through placement and mirroring.

The TOSIZE diagram supplies edge names but does not label panel faces A and B.
The first release accepts whole-mm blank dimensions and positive integer
quantities. It rejects fractional blank dimensions; it does not round them.

The draft shared model uses a right-handed signed basis: `L × W = A`. By
default, A is the positive stock-thickness face; an explicit show-face choice
can select the opposite face when upper/lower finishes need it. L follows the
positive authored grain axis for directional material. Grain is an unoriented
line, so its sign is canonicalized. For a non-directional material, choose the
first canonical local XYZ axis perpendicular to A as positive L; do not sort
by dimension. W is `A × L` and can point along a negative source axis. When it
does, shift the local origin to the source-axis maximum so coordinates remain
non-negative; do not reflect the panel. With face A viewed from outside toward
B, positive L is right and positive W is up.

The diagram-derived edge mappings are:

| Provider field | Basis edge | Diagram position |
| --- | --- | --- |
| ZAGENZAGEN `LV` | `v = 0` | Bottom/front |
| ZAGENZAGEN `LA` | `v = Width` | Top/back |
| ZAGENZAGEN `BL` | `u = 0` | Left |
| ZAGENZAGEN `BR` | `u = Length` | Right |
| OPMAATZAGEN `Long side 1` | `v = Width` | Top |
| OPMAATZAGEN `Long side 2` | `v = 0` | Bottom |
| OPMAATZAGEN `Short side 1` | `u = 0` | Left |
| OPMAATZAGEN `Short side 2` | `u = Length` | Right |

The ZAGENZAGEN diagram expands its labels as `LV` = Lengte Voor, `LA` = Lengte
Achter, `BL` = Breedte Links, and `BR` = Breedte Rechts. These mappings follow
the provided orientation diagrams. Confirm the signed orientation with an
asymmetric edge and A/B fixture before implementation. In particular,
`OPMAATZAGEN Long side 1` is not `ZAGENZAGEN LV`. Map upper/top finishes to
face A and lower/bottom finishes to face B, not to world up. Confirm the A/B
choice with the same fixture. Provider `Long` and `Short` meaning when `Length`
is numerically less than `Width` still needs confirmation.

The example stock sheet of 2600 × 2100 mm is one example. Do not hardcode it
as a universal provider sheet size.

## Evidence and status

Template column names, edge labels, finish values, and delimiter observations
come from the supplied `Import OPMAATZAGEN _ TOSIZE.xlsx` and
`zaaglijst-voorbeeld.csv`. Provider UI rules were checked on 2026-10-30.

- [ZAGENZAGEN cutting service](https://www.zagenzagen.nl/app): open
  **Importeer zaaglijst**, then **CSV richtlijnen bekijken** for codes and limits.
- [ZAGENZAGEN panel orientation](https://www.zagenzagen.nl/images/paneel.webp):
  the A/B faces and four named edges shown in the supplied diagram.
- [OPMAATZAGEN import](https://www.opmaatzagen.nl/hout-plaatmateriaal): open
  **Importeer je zaaglijst**, then **CSV importeren** for format rules and
  material, thickness, and purchase-type context.
- [OPMAATZAGEN template](https://docs.google.com/spreadsheets/d/1Tq_GntnnNIFxz44lfTrSXIRa44-r-Autp64m-48cIV8):
  the template linked by the import UI and supplied as an Excel workbook.

The unverified CSV syntax and finish dimension rules above remain open. No
supplier import test or order was submitted during this requirements review.
