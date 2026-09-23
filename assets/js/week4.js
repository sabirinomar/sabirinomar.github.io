(() => {
  "use strict";

  const DATA_URL = "../../assets/week4_summary.json";
  const SVG_NS = "http://www.w3.org/2000/svg";
  const COLORS = ["#e85a98", "#8d63ff", "#e0a62d", "#3f2d52", "#38a89d", "#ee8f55", "#7c6bb2", "#c44f85"];
  const $ = (selector) => document.querySelector(selector);
  const escapeHtml = (value) => String(value).replace(/[&<>\"']/g, (character) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"}[character]));

  fetch(DATA_URL)
    .then((response) => {
      if (!response.ok) throw new Error(`Could not load ${DATA_URL}`);
      return response.json();
    })
    .then(init)
    .catch((error) => {
      console.error("Week 4 data load failed.", error);
      $("#week4-app")?.insertAdjacentHTML("afterbegin", `<p class="week4-error">The Week 4 data could not be loaded. ${escapeHtml(error.message)}</p>`);
    });

  function init(data) {
    const positions = data.positions;
    const nodes = Object.fromEntries(data.community_comparison.louvain_nodes.map((node) => [node.id, node]));
    const edges = data.edges;
    const comparisonState = { method: "louvain", selected: null };
    const weightState = { method: "unweighted", selected: null };

    const communityRows = (method) => method === "louvain" ? data.community_comparison.louvain_nodes : data.community_comparison.infomap_nodes;
    const weightRows = (method) => method === "weighted" ? data.weighted_comparison.weighted_nodes : data.weighted_comparison.unweighted_nodes;
    const point = (nodeId, width, height) => ({
      x: 20 + ((positions[nodeId]?.x ?? 0.5) + 1) / 2 * (width - 40),
      y: 20 + ((positions[nodeId]?.y ?? 0.5) + 1) / 2 * (height - 40),
    });

    function svgElement(name, attributes = {}) {
      const element = document.createElementNS(SVG_NS, name);
      Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
      return element;
    }

    function network(container, rows, options = {}) {
      if (!container) return;
      const width = 900;
      const height = options.height || 520;
      const rowById = Object.fromEntries(rows.map((row) => [row.id, row]));
      const svg = svgElement("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": options.label || "Interactive community network" });
      const selected = options.selected;
      const neighbourIds = new Set(selected ? edges.filter((edge) => edge[0] === selected || edge[1] === selected).flatMap((edge) => [edge[0], edge[1]]) : []);
      const edgeGroup = svgElement("g", { class: "week4-edges" });
      edges.forEach(([source, target, weight, alpha]) => {
        if (options.alpha != null && alpha < options.alpha) return;
        const sourcePoint = point(source, width, height);
        const targetPoint = point(target, width, height);
        edgeGroup.appendChild(svgElement("line", {
          x1: sourcePoint.x, y1: sourcePoint.y, x2: targetPoint.x, y2: targetPoint.y,
          class: `week4-edge${selected && (source === selected || target === selected) ? " is-selected" : ""}`,
          "stroke-width": options.alpha != null ? Math.min(3, 0.6 + weight * 0.7) : 0.55,
        }));
      });
      svg.appendChild(edgeGroup);
      const nodeGroup = svgElement("g", { class: "week4-nodes" });
      rows.forEach((row) => {
        const nodePoint = point(row.id, width, height);
        const circle = svgElement("circle", {
          cx: nodePoint.x, cy: nodePoint.y,
          r: row.id === selected ? 8 : (row.changed ? 4.8 : 3.2),
          class: `week4-node${row.changed ? " is-changed" : ""}${row.id === selected ? " is-selected" : ""}${neighbourIds.has(row.id) ? " is-neighbour" : ""}`,
          fill: COLORS[row.community % COLORS.length],
          tabindex: "0",
          "data-node-id": row.id,
          "aria-label": `${row.name}, community ${row.community + 1}${row.changed ? ", assignment differs" : ""}`,
        });
        circle.addEventListener("mouseenter", () => showTooltip(container, row, nodePoint, options.otherLabel));
        circle.addEventListener("focus", () => showTooltip(container, row, nodePoint, options.otherLabel));
        circle.addEventListener("mouseleave", () => hideTooltip(container));
        circle.addEventListener("blur", () => hideTooltip(container));
        circle.addEventListener("click", () => {
          if (options.onSelect) options.onSelect(row.id);
        });
        nodeGroup.appendChild(circle);
      });
      svg.appendChild(nodeGroup);
      const tooltip = container.querySelector(".week4-tooltip");
      container.replaceChildren(svg);
      if (tooltip) container.appendChild(tooltip);
      if (selected && rowById[selected]) showTooltip(container, rowById[selected], point(selected, width, height), options.otherLabel);
    }

    function showTooltip(container, row, nodePoint, otherLabel) {
      const tooltip = container.querySelector(".week4-tooltip");
      if (!tooltip) return;
      tooltip.innerHTML = `<strong>${escapeHtml(row.name)}</strong><br>Community ${row.community + 1}${row.changed ? `<br><span class="tooltip-accent">Assignment differs</span>` : ""}${otherLabel ? `<br>${otherLabel}: ${row.other_community + 1}` : ""}`;
      tooltip.hidden = false;
      tooltip.style.left = `${Math.min(Math.max(nodePoint.x / 900 * 100, 8), 78)}%`;
      tooltip.style.top = `${Math.max(4, nodePoint.y / 520 * 100 - 13)}%`;
    }

    function hideTooltip(container) {
      const tooltip = container.querySelector(".week4-tooltip");
      if (tooltip) tooltip.hidden = true;
    }

    function networkShell(id, hint) {
      const container = $(id);
      if (!container) return null;
      container.innerHTML = `<div class="week4-network-wrap"><div class="week4-tooltip" role="tooltip" hidden></div></div><p class="week4-hint">${hint}</p>`;
      return container.querySelector(".week4-network-wrap");
    }

    const communityNetwork = networkShell("#community-network", "Hover or focus a node. Outlined nodes have different Louvain and Infomap assignments.");
    const weightedNetwork = networkShell("#weighted-network", "Toggle the view, then hover a node. Outlined nodes move when reciprocal-link weight is included.");

    function renderCommunity() {
      const rows = communityRows(comparisonState.method);
      network(communityNetwork, rows, { selected: comparisonState.selected, otherLabel: comparisonState.method === "louvain" ? "Infomap" : "Louvain", onSelect: (id) => { comparisonState.selected = id; renderCommunity(); } });
      document.querySelectorAll("[data-community-method]").forEach((button) => button.classList.toggle("is-active", button.dataset.communityMethod === comparisonState.method));
      const selectedRow = rows.find((row) => row.id === comparisonState.selected);
      $("#community-readout").innerHTML = selectedRow ? `<strong>${escapeHtml(selectedRow.name)}</strong><span>Community ${selectedRow.community + 1}${selectedRow.changed ? " · assignment differs" : " · same assignment"}</span>` : "Select a node to read its assignment.";
    }

    function renderWeighted() {
      const rows = weightRows(weightState.method);
      network(weightedNetwork, rows, { selected: weightState.selected, otherLabel: weightState.method === "weighted" ? "Unweighted" : "Weighted", onSelect: (id) => { weightState.selected = id; renderWeighted(); } });
      document.querySelectorAll("[data-weight-method]").forEach((button) => button.classList.toggle("is-active", button.dataset.weightMethod === weightState.method));
      const selectedRow = rows.find((row) => row.id === weightState.selected);
      $("#weighted-readout").innerHTML = selectedRow ? `<strong>${escapeHtml(selectedRow.name)}</strong><span>Community ${selectedRow.community + 1}${selectedRow.changed ? " · moved" : " · unchanged"}</span>` : "Select a node to read its assignment.";
    }

    document.querySelectorAll("[data-community-method]").forEach((button) => button.addEventListener("click", () => { comparisonState.method = button.dataset.communityMethod; renderCommunity(); }));
    document.querySelectorAll("[data-weight-method]").forEach((button) => button.addEventListener("click", () => { weightState.method = button.dataset.weightMethod; renderWeighted(); }));

    const backboneNetwork = networkShell("#backbone-network", "Choose an analyzed alpha threshold to see which links survive the backbone filter.");
    const alphaSelect = $("#alpha-select");
    const alphaReadout = $("#alpha-readout");
    data.backbone.selected.forEach((measurement, index) => {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = `α = ${measurement.alpha.toFixed(4)}`;
      alphaSelect.appendChild(option);
    });

    function renderBackbone() {
      const measurement = data.backbone.selected[Number(alphaSelect.value) || 0];
      network(backboneNetwork, communityRows("louvain"), { alpha: measurement.alpha, height: 500, label: "Backbone network at selected alpha" });
      alphaReadout.innerHTML = `<div><strong>${measurement.nodes}</strong><span>nodes</span></div><div><strong>${measurement.edges}</strong><span>edges</span></div><div><strong>${measurement.giant_component}</strong><span>giant component</span></div><div><strong>${(measurement.fragmentation * 100).toFixed(1)}%</strong><span>fragmentation</span></div>`;
      $("#alpha-note").textContent = measurement.alpha === data.backbone.break_alpha ? "This is the largest observed giant-component drop among the tested thresholds." : "This is one of three thresholds selected around the measured structural break.";
    }
    alphaSelect.addEventListener("change", renderBackbone);

    $("#community-nmi").textContent = data.community_comparison.nmi.toFixed(3);
    $("#community-counts").textContent = `${data.community_comparison.louvain_communities} / ${data.community_comparison.infomap_communities}`;
    $("#community-nmi-panel").textContent = `NMI is ${data.community_comparison.nmi.toFixed(3)}`;
    $("#weighted-nmi-inline").textContent = data.weighted_comparison.nmi.toFixed(3);
    $("#moved-count").textContent = data.weighted_comparison.moved_count;
    $("#moved-count-text").textContent = data.weighted_comparison.moved_count;
    $("#break-alpha").textContent = data.backbone.break_alpha.toFixed(4);
    $("#break-node").textContent = data.backbone.associated_node.name;
    $("#break-alpha-text").textContent = `alpha ${data.backbone.break_alpha.toFixed(4)}`;
    const aristotleMessage = data.aristotle.present ? `<strong>${escapeHtml(data.aristotle.name)}</strong><span>Community ${data.aristotle.community + 1} · ${data.aristotle.neighbors.length} direct neighbours</span>` : `<strong>Aristotle is absent</strong><span>No Aristotle node exists in the supplied Marvel dataset.</span>`;
    $("#aristotle-readout").innerHTML = aristotleMessage;

    renderCommunity();
    renderWeighted();
    renderBackbone();
  }
})();
