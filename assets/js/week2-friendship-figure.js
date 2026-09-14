(() => {
  const dataUrl = "../../assets/week2_summary.json";
  const colors = {
    pink: "#f0579f",
    lilac: "#b9abff",
    gold: "#f9d778",
    navy: "#1d264b",
    muted: "#625473",
    border: "rgba(96, 74, 120, 0.18)",
  };

  const escapeHtml = (value) =>
    String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  const format = (value) => Number(value).toFixed(1);
  const byId = (id) => document.querySelector(`#${id}`);

  function fallback(id, src, alt) {
    const element = byId(id);
    if (element) {
      element.innerHTML = `<img src="${src}" alt="${alt}" loading="lazy">`;
    }
  }

  function chartShell(id, svg, label) {
    const element = byId(id);
    if (!element) {
      return null;
    }
    element.innerHTML = `
      <div class="module-chart-wrap">
        ${svg}
        <div class="module-chart-tooltip" role="tooltip" hidden></div>
      </div>
      <p class="module-chart-hint">${label}</p>
    `;
    return element;
  }

  function attachTooltip(container, selector, getContent) {
    const tooltip = container.querySelector(".module-chart-tooltip");
    const items = container.querySelectorAll(selector);
    let active;

    const hide = () => {
      tooltip.hidden = true;
      active?.classList.remove("is-active");
      active = null;
    };
    const show = (item) => {
      const content = getContent(item);
      if (!content) {
        return;
      }
      active?.classList.remove("is-active");
      active = item;
      active.classList.add("is-active");
      tooltip.innerHTML = content;
      tooltip.hidden = false;
      const wrap = container.querySelector(".module-chart-wrap");
      const itemRect = item.getBoundingClientRect();
      const wrapRect = wrap.getBoundingClientRect();
      const maxLeft = Math.max(8, wrapRect.width - tooltip.offsetWidth - 8);
      const left = Math.min(Math.max(itemRect.left - wrapRect.left + itemRect.width / 2, 8), maxLeft);
      const top = itemRect.top - wrapRect.top - tooltip.offsetHeight - 10;
      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${Math.max(8, top)}px`;
    };

    items.forEach((item) => {
      item.addEventListener("mouseenter", () => show(item));
      item.addEventListener("focus", () => show(item));
      item.addEventListener("click", () => show(item));
      item.addEventListener("mouseleave", hide);
      item.addEventListener("blur", hide);
    });
  }

  function renderFriendship(data) {
    const element = byId("friendship-figure");
    if (!element) {
      return;
    }
    const points = data.points.filter((point) => point.degree > 0);
    const maxima = new Set(data.local_maxima.map((point) => point.node));
    const width = 860;
    const height = 570;
    const margin = { top: 58, right: 28, bottom: 78, left: 82 };
    const limit = Math.max(...points.flatMap((point) => [point.degree, point.average_neighbor_degree])) + 2;
    const x = (value) => margin.left + (value / limit) * (width - margin.left - margin.right);
    const y = (value) => height - margin.bottom - (value / limit) * (height - margin.top - margin.bottom);
    const ticks = Array.from({ length: Math.floor(limit / 20) + 1 }, (_, index) => index * 20);
    const svg = `
      <svg class="module-chart friendship-chart" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="friendship-title friendship-description">
        <title id="friendship-title">The friendship paradox in the Marvel network</title>
        <desc id="friendship-description">Character degree compared with average neighbour degree.</desc>
        <text class="chart-title" x="${width / 2}" y="25" text-anchor="middle">The friendship paradox in the Marvel network</text>
        ${ticks.map((tick) => `
          <line class="chart-grid" x1="${x(tick)}" y1="${y(0)}" x2="${x(tick)}" y2="${y(limit)}"></line>
          <line class="chart-grid" x1="${x(0)}" y1="${y(tick)}" x2="${x(limit)}" y2="${y(tick)}"></line>
          <text class="chart-tick" x="${x(tick)}" y="${y(0) + 22}" text-anchor="middle">${tick}</text>
          <text class="chart-tick" x="${x(0) - 10}" y="${y(tick) + 4}" text-anchor="end">${tick}</text>
        `).join("")}
        <line class="chart-axis" x1="${x(0)}" y1="${y(0)}" x2="${x(limit)}" y2="${y(0)}"></line>
        <line class="chart-axis" x1="${x(0)}" y1="${y(0)}" x2="${x(0)}" y2="${y(limit)}"></line>
        <line class="chart-reference" x1="${x(0)}" y1="${y(0)}" x2="${x(limit)}" y2="${y(limit)}"></line>
        ${points.map((point) => `
          <g class="friendship-point ${maxima.has(point.node) ? "local-maximum" : ""}" data-node="${escapeHtml(point.node)}" tabindex="0" role="button"
            aria-label="${escapeHtml(point.name)}, degree ${point.degree}, average neighbour degree ${format(point.average_neighbor_degree)}">
            <circle cx="${x(point.degree)}" cy="${y(point.average_neighbor_degree)}" r="4"></circle>
          </g>
        `).join("")}
        <text class="chart-axis-label" x="${(x(0) + x(limit)) / 2}" y="${height - 18}" text-anchor="middle">Character degree</text>
        <text class="chart-axis-label" transform="translate(19 ${(y(0) + y(limit)) / 2}) rotate(-90)" text-anchor="middle">Average neighbour degree</text>
      </svg>
    `;
    const chart = chartShell("friendship-figure", svg, "Hover, focus, or tap a point to inspect a character.");
    const pointsByNode = new Map(points.map((point) => [point.node, point]));
    attachTooltip(chart, ".friendship-point", (item) => {
      const point = pointsByNode.get(item.dataset.node);
      const gap = point.average_neighbor_degree - point.degree;
      return `<strong>${escapeHtml(point.name)}</strong><br>
        Character degree: ${point.degree}<br>
        Average neighbour degree: ${format(point.average_neighbor_degree)}<br>
        Difference: ${gap >= 0 ? "+" : "−"}${format(Math.abs(gap))}<br>
        Experiences the paradox: ${gap > 0 ? "Yes" : "No"}`;
    });
  }

  function renderCcdf(data) {
    const width = 860;
    const height = 540;
    const margin = { top: 54, right: 34, bottom: 70, left: 76 };
    const series = Object.entries(data);
    const maxX = Math.max(...series.flatMap(([, values]) => values.degree));
    const x = (value) => margin.left + (Math.log10(Math.max(value, 1)) / Math.log10(maxX)) * (width - margin.left - margin.right);
    const y = (value) => height - margin.bottom - ((-Math.log10(Math.max(value, 0.0033))) / 2.5) * (height - margin.top - margin.bottom);
    const colorsByName = { "Marvel network": colors.pink, "Random graph": "#8d63ff", "Barabasi-Albert": colors.gold };
    const svg = `
      <svg class="module-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Log-log CCDF comparison">
        <text class="chart-title" x="${width / 2}" y="25" text-anchor="middle">Marvel degree CCDF versus model networks</text>
        ${[1, 10, 100].map((tick) => `<line class="chart-grid" x1="${x(tick)}" y1="${y(1)}" x2="${x(tick)}" y2="${y(0.0033)}"></line><text class="chart-tick" x="${x(tick)}" y="${y(1) + 22}" text-anchor="middle">${tick}</text>`).join("")}
        ${[1, 0.1, 0.01].map((tick) => `<line class="chart-grid" x1="${x(1)}" y1="${y(tick)}" x2="${x(maxX)}" y2="${y(tick)}"></line><text class="chart-tick" x="${x(1) - 10}" y="${y(tick) + 4}" text-anchor="end">${tick}</text>`).join("")}
        ${series.map(([name, values]) => {
          const points = values.degree.map((degree, index) => `${x(degree)},${y(values.ccdf[index])}`).join(" ");
          return `<polyline class="ccdf-line" data-series="${escapeHtml(name)}" points="${points}" style="stroke:${colorsByName[name]}"></polyline>
            ${values.degree.map((degree, index) => `<circle class="ccdf-point" data-series="${escapeHtml(name)}" data-degree="${degree}" data-probability="${values.ccdf[index]}" cx="${x(degree)}" cy="${y(values.ccdf[index])}" r="4" tabindex="0" role="button"></circle>`).join("")}`;
        }).join("")}
        <text class="chart-axis-label" x="${width / 2}" y="${height - 18}" text-anchor="middle">Undirected degree k</text>
        <text class="chart-axis-label" transform="translate(19 ${height / 2}) rotate(-90)" text-anchor="middle">P(K ≥ k)</text>
      </svg>
    `;
    const chart = chartShell("ccdf-figure", svg, "Hover, focus, or tap a point to compare a degree threshold.");
    attachTooltip(chart, ".ccdf-point", (item) => `<strong>${escapeHtml(item.dataset.series)}</strong><br>Degree k: ${item.dataset.degree}<br>P(K ≥ k): ${format(Number(item.dataset.probability))}`);
  }

  function renderPreferential(data) {
    const width = 860;
    const height = 520;
    const series = Object.entries(data.degree_ranks);
    const panels = series.map(([name, degrees], index) => {
      const left = 55 + index * 405;
      const max = Math.max(...degrees);
      const barWidth = 330 / degrees.length;
      return `<g><text class="chart-panel-title" x="${left + 165}" y="45" text-anchor="middle">${escapeHtml(name)}</text>
        ${degrees.map((degree, rank) => `<rect class="degree-bar" data-series="${escapeHtml(name)}" data-rank="${rank + 1}" data-degree="${degree}" x="${left + rank * barWidth}" y="${440 - (degree / max) * 350}" width="${Math.max(1, barWidth)}" height="${(degree / max) * 350}" tabindex="0" role="button"></rect>`).join("")}
        <text class="chart-axis-label" x="${left + 165}" y="485" text-anchor="middle">Ranked node</text>
        <text class="chart-axis-label" transform="translate(${left - 30} 270) rotate(-90)" text-anchor="middle">Degree</text></g>`;
    }).join("");
    const svg = `<svg class="module-chart preferential-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Ranked degree bars for the real Marvel and preferential-attachment networks">
      <text class="chart-title" x="${width / 2}" y="22" text-anchor="middle">The model gets the hub shape, not the whole story</text>${panels}</svg>`;
    const chart = chartShell("preferential-figure", svg, "Hover, focus, or tap a ranked bar to inspect its degree.");
    attachTooltip(chart, ".degree-bar", (item) => `<strong>${escapeHtml(item.dataset.series)}</strong><br>Ranked node: ${item.dataset.rank}<br>Degree: ${item.dataset.degree}`);
  }

  function renderLookCloser(points) {
    const container = byId("look-closer-visualization");
    if (!container) {
      return;
    }
    const sorted = [...points].sort((a, b) => a.name.localeCompare(b.name));
    container.innerHTML = `
      <div class="look-closer-controls">
        <label for="character-search">Choose a character</label>
        <input id="character-search" type="search" autocomplete="off" role="combobox" aria-expanded="false" aria-controls="character-options" placeholder="Search characters">
        <div id="character-options" class="character-options" role="listbox" hidden></div>
        <p id="character-empty" class="look-closer-empty" hidden>No matching characters.</p>
      </div>
      <div id="character-comparison" aria-live="polite"></div>
    `;
    const search = container.querySelector("#character-search");
    const options = container.querySelector("#character-options");
    const comparison = container.querySelector("#character-comparison");
    const empty = container.querySelector("#character-empty");
    const byName = new Map(sorted.map((point) => [point.name.toLowerCase(), point]));
    let selected = sorted.find((point) => point.degree > 0) || sorted[0];

    const renderOptions = () => {
      const query = search.value.trim().toLowerCase();
      const matches = sorted.filter((point) => point.name.toLowerCase().includes(query));
      options.innerHTML = matches.slice(0, 30).map((point) => `<button type="button" role="option" class="character-option" data-name="${escapeHtml(point.name)}">${escapeHtml(point.name)}</button>`).join("");
      options.hidden = !query || !matches.length;
      search.setAttribute("aria-expanded", String(!options.hidden));
      empty.hidden = Boolean(matches.length || !query);
      options.querySelectorAll(".character-option").forEach((button) => {
        button.addEventListener("click", () => select(byName.get(button.dataset.name.toLowerCase())));
      });
    };
    const select = (point) => {
      if (!point) {
        return;
      }
      selected = point;
      search.value = point.name;
      options.hidden = true;
      search.setAttribute("aria-expanded", "false");
      renderComparison();
    };
    const renderComparison = () => {
      const gap = selected.average_neighbor_degree - selected.degree;
      const difference = format(Math.abs(gap));
      const maximum = Math.max(selected.degree, selected.average_neighbor_degree, 1);
      comparison.innerHTML = `
        <div class="look-closer-summary">
          <h3>${escapeHtml(selected.name)}</h3>
          <p class="look-closer-conclusion">${gap > 0 ? "Yes — this character’s connected characters are more popular on average." : "No — this character is at least as popular as their connected characters on average."}</p>
          <p class="look-closer-difference">${gap > 0 ? `Neighbors are ${difference} more popular on average.` : `This character is ${difference} more popular on average.`}</p>
          <div class="comparison-bars">
            ${bar("This character", selected.degree, "Character popularity by degree", maximum)}
            ${bar("Their connected characters on average", selected.average_neighbor_degree, "Average degree of connected characters", maximum)}
          </div>
          <p class="look-closer-meta">Difference: ${gap >= 0 ? "+" : "−"}${difference} · ${selected.neighbors.length} relevant neighbors</p>
          <div class="connected-neighbors">
            <strong>Most popular relevant neighbors</strong>
            ${selected.neighbors.length ? selected.neighbors.map((neighbor) => `
              <button type="button" class="connected-neighbor" data-name="${escapeHtml(neighbor.name)}">
                <span>${escapeHtml(neighbor.name)}</span><span class="neighbor-bar"><i style="width:${(neighbor.degree / maximum) * 100}%"></i></span><strong>${neighbor.degree}</strong>
              </button>`).join("") : "<p class=\"look-closer-empty\">This character has no relevant neighbors.</p>"}
          </div>
        </div>
      `;
      comparison.querySelectorAll(".connected-neighbor").forEach((button) => {
        button.addEventListener("click", () => select(byName.get(button.dataset.name.toLowerCase())));
      });
    };
    const bar = (label, value, explanation, maximum) => `
      <div class="comparison-bar-wrap">
        <div class="comparison-bar-label"><span>${label}</span><strong>${format(value)}</strong></div>
        <div class="comparison-bar" tabindex="0" role="img" aria-label="${label}: ${format(value)}">
          <span style="width:${(value / maximum) * 100}%"></span>
          <span class="comparison-tooltip" role="tooltip">${label}<br><strong>${format(value)}</strong><br><small>${explanation}</small></span>
        </div>
      </div>
    `;
    search.addEventListener("input", renderOptions);
    search.addEventListener("focus", renderOptions);
    search.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        options.hidden = true;
        search.setAttribute("aria-expanded", "false");
      }
      if (event.key === "Enter") {
        const first = options.querySelector(".character-option");
        if (first) {
          event.preventDefault();
          select(byName.get(first.dataset.name.toLowerCase()));
        }
      }
    });
    select(selected);
  }

  fetch(dataUrl)
    .then((response) => {
      if (!response.ok) {
        throw new Error("Week 2 data unavailable");
      }
      return response.json();
    })
    .then((data) => {
      renderCcdf(data.ccdf);
      renderFriendship(data.friendship_paradox);
      renderPreferential(data.preferential_attachment);
      renderLookCloser(data.friendship_paradox.points);
    })
    .catch(() => {
      fallback("ccdf-figure", "../../assets/figures/week2/degree_ccdf_models.png", "Log-log CCDF comparison");
      fallback("friendship-figure", "../../assets/figures/week2/friendship_paradox.png", "Friendship paradox scatter plot");
      fallback("preferential-figure", "../../assets/figures/week2/preferential_attachment.png", "Ranked degree profiles");
    });
})();
