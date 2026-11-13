---
name: buratino
description: Use when authoring or editing a Buratino furniture project, checking a preview or report, or preparing a supplier cut list.
---

# Buratino

- Start from a runnable Space example for rectangular work or a profile example
  for slopes. Set furniture inputs in `project.py`. For shared geometry behavior,
  use the editable Cabineteer source at `buratino/vendor/cabineteer`.
  [Authoring guide](../../../buratino/docs/designing.md#choose-a-model)
- Use `resolved_space_assembly()` to check Space dimensions before a CAD build.
  For runner fit, measure from the datums in the selected slide's instructions.
  A runner can reference a machined face below the drawer bottom.
- In the preview catalog, a URL with `/revisions/` stays on that build. Open
  `/designs/<project>/preview.html` or `/designs/<project>/report.html` for the
  live project. Check watcher status and `buratino/projects/<project>/build/latest.json`.
  A failed edit leaves the last good build visible. If no watcher is active,
  run `./buratino/bin/buratino build <project>` after editing.
- In `report.html`, use `#part-drawings` for machined dimensions, `#assembly`
  for exploded views, and `#cutlists` for supplier CSVs. Check supplier quantities
  in the CSV and its `index.json` trace. One row can supply several drawing codes
  when the ordered blanks match. [Cut-service guide](../../../buratino/docs/cut-services.md)
