# Cut-service exports

Each build includes provider downloads at `report.html#cutlists`. The report
lists one CSV per material, panel type and thickness group (with separate files
when a provider limit requires a split). It shows panel counts and export issues,
including omitted source records. The CSV files and their `index.json` source
traces are captured under `build/REVISION/cutlists/PROVIDER/` and remain with
that build. `parts.csv` is secondary internal parts data.

Report downloads use the default export configuration. To set custom material,
grain or finish options, use the CLI below with `--config`. These settings do
not change existing report downloads. Select and check the actual material
product on the provider website.

Export the latest validated build. The command reads its captured result and
does not run CAD or change the build:

```bash
./buratino/bin/buratino export-cutlist projects/machined-drawer \
  --provider opmaatzagen
./buratino/bin/buratino export-cutlist projects/machined-drawer \
  --provider zagenzagen --config projects/machined-drawer/cut-service.json \
  --json
```

The default output is `projects/NAME/exports/REVISION/PROVIDER/`. It contains
one CSV per material, panel type, and thickness group, plus `index.json`. The
index records the revision, source IDs and safe labels, group context, issues,
and links to the captured report and its Assembly section. It is an export trace,
not another machining list. Re-export replaces only a directory with a valid
Buratino export marker. The command refuses an unowned non-empty directory.

If the source changed after build, or a captured build file changed, run
`build` first. A successful export still does not mean the design is ready to
manufacture. Review the linked reports and resolve the listed issues.

## Configuration

Configuration is optional. It can choose provider import context and state
explicit grain or finish intent. It does not replace the furniture model or
select a band by its display color.

```json
{
  "materials": {
    "birch-plywood": {
      "panel_type": "plywood",
      "provider_material": "Birch plywood",
      "purchase_type": "cut-to-size",
      "grain_required": true
    }
  },
  "parts": {
    "drawer.front": {
      "grain_axis": "x",
      "show_face": "z+",
      "edge_finishes": {
        "x+": {"kind": "band"},
        "y-": {"kind": "chamfer", "face": "a", "size_mm": 2}
      }
    }
  }
}
```

Part IDs must match exactly. Supported finish kinds are `band`, `chamfer`,
`roundover`, and `mitre`. The config schema checks unknown fields and invalid
types. Provider options do not change the panel dimensions.

## Dimensions and edges

Providers accept whole millimetres. For each positive fractional blank
dimension, the export rounds up to the next millimetre. It never rounds to the
nearest millimetre. This makes the ordered blank a safe oversize of the exact
source geometry. The source geometry does not change. The export index records
the exact source dimensions, ordered dimensions, and the round-up allowance;
the captured report retains the exact source geometry.

Services trim stock before banding. CSV dimensions are the ordered blank
dimensions. Do not subtract or add band thickness. Band trimming does not
change the nominal ordered dimensions. Display band thickness zero is not an
order thickness. Dimensions and quantities must be positive; quantity and
thickness are not rounded.

Length follows the authored grain axis when known. Width follows the signed
panel basis. Do not swap dimensions to make Length larger. Grain stays
independent from stock-sheet grain. Unknown grain blocks export only when the
configured material requires directional grain.

| Provider field | Signed basis edge | Position in the supplied diagram |
| --- | --- | --- |
| ZAGENZAGEN `LV` | `v = 0` | Bottom/front |
| ZAGENZAGEN `LA` | `v = Width` | Top/back |
| ZAGENZAGEN `BL` | `u = 0` | Left |
| ZAGENZAGEN `BR` | `u = Length` | Right |
| OPMAATZAGEN `Long side 1` | `v = Width` | Top |
| OPMAATZAGEN `Long side 2` | `v = 0` | Bottom |
| OPMAATZAGEN `Short side 1` | `u = 0` | Left |
| OPMAATZAGEN `Short side 2` | `u = Length` | Right |

The provider edge diagrams do not settle the meaning of Long and Short when
Length is less than Width. The export keeps the ordered dimensions and marks
the multi-edge encoding as unverified where it applies. Upper/lower finish
faces map to panel faces A/B, not world up.

ZAGENZAGEN uses the semicolon header
`Naam;Aantal;Lengte;Breedte;LV;LA;BL;BR`. Its numeric edge codes are 1 through
9. Matching band intent uses code 7. An opposing pair, or one edge as its
   subset, can be represented. Other band layouts export the blank with no
   guessed band code and a review issue for manual provider selection.
   Single-edge eligibility remains open. Unsupported finishes do not remove a
   valid blank row; only unsafe dimensions or missing required grain omit it.

OPMAATZAGEN uses the comma header
`Aantal,Lengte (mm),Breedte (mm),Eigen kenmerk,Afwerking zijdes,Afwerking type`.
Matching band intent uses the template option `Edge band matching - 1mm`.
This is a provider option; it does not change display geometry. The current
best-effort multi-edge encoding puts comma-separated side labels in one quoted
cell and uses one shared finish type. This grammar is open and unverified.
Mixed finish types and finishes that the template cannot express export a
blank with a review issue. The row remains in the report cut lists.

Existing declared EdgeBand metadata is matching band intent for export.
Color does not select a product. Services trim before banding, so dimensions
stay unchanged. Other machining remains in the report part drawings.

No supplier import or order has been tested. Check the CSV in the provider
import UI before use. ZAGENZAGEN panel limit is 500 physical panels per CSV;
larger quantities split across files. Provider product eligibility and
OPMAATZAGEN multi-edge parsing remain unverified.
