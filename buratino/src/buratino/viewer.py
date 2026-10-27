"""HTML extension for the bare-cabinet preview workspace."""


def viewer_extension() -> str:
    """Return the preview UI markup added to Cabineteer's standalone page."""
    return """<link rel="stylesheet" href="assets/preview.css">
<header id="workspace-header">
  <div id="project-block">
  <div id="project-title">Cabinet preview</div>
    <div id="project-dimensions">Loading dimensions…</div>
  </div>
  <nav id="project-links" aria-label="Project documents">
    <a href="report.html">Report</a>
    <a href="parts.csv">Cut list</a>
  </nav>
  <div id="draft-badge" data-state="unknown">DRAFT · NOT FOR MANUFACTURING</div>
  <nav id="view-toolbar" aria-label="Viewer controls">
    <button type="button" data-view="iso" title="Isometric view">Iso</button>
    <button type="button" data-view="front" title="Front view">Front</button>
    <button type="button" data-view="side" title="Side view">Side</button>
    <button type="button" data-view="top" title="Top view">Top</button>
    <label id="panel-opacity-control" for="panel-opacity">
      <input type="range" id="panel-opacity" aria-label="Panel opacity"
             min="0" max="100" value="100" step="5">
      <output id="panel-opacity-value" for="panel-opacity">100%</output>
    </label>
    <button type="button" id="grain-toggle" aria-pressed="true">Grain on</button>
    <button type="button" id="drawer-pose-toggle" aria-pressed="false" hidden>
      Drawers
    </button>
    <button type="button" id="door-pose-toggle" aria-pressed="false" hidden>
      Doors
    </button>
  </nav>
</header>
<section id="parts-dock" aria-label="Cutting parts">
  <div id="table-heading">
    <h1>Cutting parts</h1>
    <span id="table-hint">Equal blanks are grouped.</span>
    <span id="group-count">Loading groups…</span>
  </div>
  <fieldset id="visibility-controls" aria-label="Model visibility">
    <legend>Visible parts</legend>
    <div id="visibility-options"></div>
  </fieldset>
  <div id="table-scroll">
    <table aria-label="Grouped cutting parts">
      <thead><tr>
        <th scope="col">Part</th><th scope="col">Qty</th>
        <th scope="col"><span class="wide-label">Length mm</span>
          <abbr class="compact-label" title="Length in millimetres">L mm</abbr></th>
        <th scope="col"><span class="wide-label">Width mm</span>
          <abbr class="compact-label" title="Width in millimetres">W mm</abbr></th>
        <th scope="col"><span class="wide-label">Thickness mm</span>
          <abbr class="compact-label" title="Thickness in millimetres">T mm</abbr></th>
        <th scope="col">Grain</th><th scope="col">Model</th>
      </tr></thead>
      <tbody id="parts-body"></tbody>
    </table>
  </div>
  <div id="selection-caption">
    Select a part name or a panel to inspect its cutting blank.
  </div>
</section>
<div id="viewer-message" role="status" hidden></div>
<script type="module" src="assets/preview.js"></script>"""
