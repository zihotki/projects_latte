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
    <a href="report.html">Review report</a>
    <a href="parts.csv">Draft cut list</a>
  </nav>
  <div id="draft-badge" data-state="unknown">DRAFT · NOT FOR MANUFACTURING</div>
  <nav id="view-toolbar" aria-label="Viewer controls">
    <button type="button" data-view="iso" title="Isometric view">Iso</button>
    <button type="button" data-view="front" title="Front view">Front</button>
    <button type="button" data-view="side" title="Side view">Side</button>
    <button type="button" data-view="top" title="Top view">Top</button>
    <label id="panel-opacity-control" for="panel-opacity">
      Panel opacity
      <input type="range" id="panel-opacity" min="0" max="100"
             value="100" step="5">
      <output id="panel-opacity-value" for="panel-opacity">100%</output>
    </label>
    <button type="button" id="grain-toggle" aria-pressed="true">Grain marks on</button>
    <button type="button" id="drawer-pose-toggle" aria-pressed="false" hidden>
      Drawers closed
    </button>
    <button type="button" id="door-pose-toggle" aria-pressed="false" hidden>
      Upper doors closed
    </button>
  </nav>
</header>
<section id="parts-dock" aria-label="Cutting parts">
  <div id="table-heading">
    <h1>Cutting parts</h1>
    <span id="table-hint">Equal blanks are grouped. Grain direction is assumed.</span>
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
        <th scope="col">Max blank length mm</th><th scope="col">Max blank width mm</th>
        <th scope="col">Blank thickness mm</th>
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
