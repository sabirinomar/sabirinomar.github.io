(() => {
  "use strict";

  const DATA_URL = "../../assets/week3/network_game.json";
  const SVG_NS = "http://www.w3.org/2000/svg";
  const $ = (selector) => document.querySelector(selector);
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const shortName = (name) => name.replace(/\s*\([^)]*\)/g, "");

  fetch(DATA_URL)
    .then((response) => {
      if (!response.ok) throw new Error(`Could not load ${DATA_URL}`);
      return response.json();
    })
    .then((data) => {
      try {
        init(data);
      } catch (error) {
        console.error("Week 3 playground initialization failed.", error);
        showError(`The playground could not be initialized. ${error.message}`);
      }
    })
    .catch((error) => {
      console.error("Week 3 playground data load failed.", error);
      showError(`The playground data could not be loaded. ${error.message}`);
    });

  function showError(message) {
    document.querySelector(".week3-playground")?.insertAdjacentHTML(
      "afterbegin",
      `<p class="playground-error">${message}</p>`,
    );
  }

  function init(data) {
    const nodeById = Object.fromEntries(data.nodes.map((node) => [node.id, node]));
    const adjacency = Object.fromEntries(data.nodes.map((node) => [node.id, []]));
    data.edges.forEach(([source, target]) => {
      adjacency[source].push(target);
      adjacency[target].push(source);
    });

    const state = { removed: new Set(), removalHistory: [], selected: null, clue: "none" };
    const characterClass = (node) => {
      if (!node) return "unknown";
      const name = node.name.toLowerCase();
      if (node.id === "Spider-Man" || name === "spider-man") return "spider";
      if (node.id === "Black_Widow_(Natasha_Romanova)" || name.includes("black widow")) return "widow";
      if (node.id === "Doctor_Strange" || name === "doctor strange") return "strange";
      if (node.id === "Deadpool" || name === "deadpool") return "deadpool";
      if (node.id === "Wolverine_(character)" || name === "wolverine (character)") return "wolverine";
      if (node.id === "Rockman_(character)" || name === "rockman (character)") return "rockman";
      return "unknown";
    };

    function visualMarkup(node, compact = false) {
      const kind = characterClass(node);
      const seedText = node ? `${node.id}:${node.name}` : "mystery-target";
      let seed = 0;
      for (let index = 0; index < seedText.length; index += 1) {
        seed = (seed * 31 + seedText.charCodeAt(index)) >>> 0;
      }
      const hue = seed % 360;
      const accent = `hsl(${hue} 78% 62%)`;
      const secondary = `hsl(${(hue + 48) % 360} 78% 72%)`;
      const initials = node
        ? shortName(node.name).split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase()
        : "?";
      const rotation = seed % 32 - 16;
      const sizeClass = compact ? " character-art--compact" : "";
      return `<div class="character-art character-art--${kind}${sizeClass} character-art--generated" aria-hidden="true">
        <svg class="generated-avatar" viewBox="0 0 190 230" role="img" aria-label="Generated avatar">
          <defs>
            <linearGradient id="avatar-${seed}" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stop-color="${accent}" />
              <stop offset="1" stop-color="${secondary}" />
            </linearGradient>
          </defs>
          <circle cx="95" cy="115" r="83" fill="none" stroke="${secondary}" stroke-width="2" stroke-dasharray="5 9" transform="rotate(${rotation} 95 115)" />
          <path d="M35 202c8-45 31-67 60-67s52 22 60 67" fill="url(#avatar-${seed})" opacity=".92" />
          <circle cx="95" cy="91" r="39" fill="#07162e" stroke="${accent}" stroke-width="5" />
          <path d="M57 91h76M95 53v76" stroke="${secondary}" stroke-width="2" opacity=".6" />
          <circle cx="82" cy="86" r="4" fill="${secondary}" />
          <circle cx="108" cy="86" r="4" fill="${secondary}" />
          <path d="M78 106c10 8 24 8 34 0" fill="none" stroke="${accent}" stroke-width="3" stroke-linecap="round" />
          <rect x="65" y="151" width="60" height="25" rx="12.5" fill="#07162e" stroke="${secondary}" stroke-width="2" />
          <text x="95" y="168" text-anchor="middle" fill="${secondary}" font-size="14" font-family="Manrope, Segoe UI, sans-serif" font-weight="800" letter-spacing="2">${initials}</text>
        </svg>
      </div>`;
    }

    function svgElement(name, attributes = {}) {
      const element = document.createElementNS(SVG_NS, name);
      Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
      return element;
    }

    function point(node, width, height) {
      return { x: 24 + node.x * (width - 48), y: 24 + node.y * (height - 48) };
    }

    function components(removed) {
      const active = new Set(data.nodes.map((node) => node.id).filter((id) => !removed.has(id)));
      const found = [];
      while (active.size) {
        const start = active.values().next().value;
        const component = new Set([start]);
        const queue = [start];
        active.delete(start);
        while (queue.length) {
          const current = queue.shift();
          adjacency[current].forEach((neighbor) => {
            if (active.has(neighbor)) {
              active.delete(neighbor);
              component.add(neighbor);
              queue.push(neighbor);
            }
          });
        }
        found.push(component);
      }
      return found.sort((a, b) => b.size - a.size);
    }

    function networkSvg(container, options = {}) {
      const width = options.width || 860;
      const height = options.height || 520;
      const removed = options.removed || new Set();
      const selected = options.selected || null;
      const highlights = options.highlights || {};
      const beforeAfter = options.beforeAfter || false;
      const svg = svgElement("svg", { viewBox: `0 0 ${width} ${height}`, role: "img" });
      const groups = components(removed);
      const giant = groups[0] || new Set();
      const disconnected = new Set();
      const neighbours = selected ? new Set(adjacency[selected]) : new Set();
      groups.slice(1).forEach((group) => group.forEach((id) => disconnected.add(id)));
      const lines = svgElement("g", { class: "network-edges" });
      data.edges.forEach(([source, target]) => {
        if (removed.has(source) || removed.has(target)) return;
        const a = point(nodeById[source], width, height);
        const b = point(nodeById[target], width, height);
        lines.appendChild(svgElement("line", {
          x1: a.x, y1: a.y, x2: b.x, y2: b.y,
          class: `network-edge ${disconnected.has(source) || disconnected.has(target) ? "network-edge--cut" : ""}${selected && (source === selected || target === selected) ? " network-edge--selected" : ""}${selected && (neighbours.has(source) || neighbours.has(target)) ? " network-edge--neighbour" : ""}`,
        }));
      });
      svg.appendChild(lines);
      const nodes = svgElement("g", { class: "network-nodes" });
      data.nodes.forEach((node) => {
        if (removed.has(node.id)) return;
        const p = point(node, width, height);
        const circle = svgElement("circle", {
          cx: p.x, cy: p.y, r: radiusFor(node, options.clue || "none", beforeAfter),
          class: `network-node ${giant.has(node.id) ? "network-node--giant" : "network-node--cut"}${selected === node.id ? " network-node--selected" : ""}`,
          tabindex: options.interactive ? "0" : "-1",
          "data-node-id": node.id,
        });
        if (highlights[node.id]) circle.classList.add(`network-node--${highlights[node.id]}`);
        if (neighbours.has(node.id)) circle.classList.add("network-node--neighbour");
        circle.addEventListener("mouseenter", () => showNodeLabel(svg, node, p));
        circle.addEventListener("mouseleave", () => svg.querySelector(".network-label")?.remove());
        if (options.interactive) {
          circle.addEventListener("click", () => selectGameNode(node.id));
          circle.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") selectGameNode(node.id);
          });
        }
        nodes.appendChild(circle);
      });
      svg.appendChild(nodes);
      if (selected && nodeById[selected] && !removed.has(selected)) {
        showNodeLabel(svg, nodeById[selected], point(nodeById[selected], width, height));
      }
      return svg;
    }

    function radiusFor(node, clue, compact = false) {
      if (compact) return node.id === state.selected ? 6 : 2.7;
      if (clue === "degree") return 2.5 + Math.sqrt(node.degree) * 0.62;
      if (clue === "betweenness") return 2.5 + Math.sqrt(node.betweenness * 100) * 1.6;
      return node.id === state.selected ? 6 : 3.4;
    }

    function showNodeLabel(svg, node, p) {
      svg.querySelector(".network-label")?.remove();
      const label = svgElement("text", { x: p.x + 8, y: p.y - 8, class: "network-label" });
      label.textContent = shortName(node.name);
      svg.appendChild(label);
    }

    function currentReadout() {
      const groups = components(state.removed);
      const giant = groups[0]?.size || 0;
      return {
        giant,
        separated: data.original_nodes - state.removed.size - giant,
        damage: (1 - giant / data.original_nodes) * 100,
      };
    }

    function gameFeedback(readout) {
      if (readout.damage > 45) return "The giant component is starting to unravel.";
      if (readout.separated >= 3) return "Now we're doing damage.";
      if (readout.separated >= 1) return "A small crack.";
      return "The network barely noticed.";
    }

    function renderGame() {
      const container = $("#game-network");
      container.classList.remove("network-refresh");
      void container.offsetWidth;
      container.classList.add("network-refresh");
      container.replaceChildren(networkSvg(container, {
        removed: state.removed,
        selected: state.selected,
        clue: state.clue,
        interactive: true,
      }));
      const readout = currentReadout();
      $("#removals-left").textContent = 10 - state.removed.size;
      $("#giant-now").textContent = readout.giant;
      $("#components-now").textContent = components(state.removed).length;
      $("#damage-now").textContent = `${readout.damage.toFixed(1)}%`;
      $("#remove-node").disabled = !state.selected || state.removed.size >= 10;
      $("#remove-node").textContent = state.selected ? `Remove ${shortName(nodeById[state.selected].name)}` : "Remove selected character";
      renderSpotlight();
      renderHistory();
      renderProgress();
      if (!state.selected) {
        $("#game-message").textContent = state.removed.size ? "Choose the next character to remove." : "Choose a character to make your first move.";
      }

      function renderProgress() {
        const progress = $("#move-progress");
        progress.innerHTML = `<span>Moves</span>${Array.from({ length: 10 }, (_, index) => `<i class="${index < state.removed.size ? "is-used" : ""}" aria-label="${index < state.removed.size ? "Used" : "Available"} move ${index + 1}"></i>`).join("")}`;
      }

      function renderSpotlight() {
        const spotlight = $("#character-spotlight");
        const node = state.selected ? nodeById[state.selected] : null;
        if (!node) {
          spotlight.innerHTML = `<div class="character-empty">${visualMarkup(null)}<span>Choose your target</span><small>The character enters the spotlight when you select a node.</small></div>`;
          return;
        }
        spotlight.innerHTML = `<div class="character-selected character-selected--${characterClass(node)}">${visualMarkup(node)}<div><span class="spotlight-kicker">Target acquired</span><h3>${shortName(node.name)}</h3><div class="spotlight-metrics"><b>${node.degree}<small>degree · direct neighbours</small></b><b>#${node.betweenness_rank}<small>betweenness rank</small></b><b>${node.nodes_outside_giant}<small>knockout damage · disconnected</small></b></div></div></div>`;
      }

      function renderHistory() {
        const history = $("#removed-history");
        history.innerHTML = state.removalHistory.length ? `<span>Removed so far</span><div class="removed-history-list">${state.removalHistory.map((item) => `<i title="${item.name}: ${item.damage} disconnected when removed"><b>${shortName(item.name).slice(0, 2).toUpperCase()}</b><span>${shortName(item.name)}</span></i>`).join("")}</div>` : "";
      }
    }

    function selectGameNode(id) {
      if (state.removed.has(id)) return;
      state.selected = id;
      $("#character-search").value = nodeById[id].name;
      renderGame();
      $("#game-message").textContent = `${nodeById[id].name} selected. Remove this node?`;
    }

    function renderSearchResults(query) {
      const box = $("#search-results");
      box.replaceChildren();
      if (!query.trim()) return;
      data.nodes
        .filter((node) => node.name.toLowerCase().includes(query.toLowerCase()) && !state.removed.has(node.id))
        .sort((a, b) => {
          const normalizedQuery = query.trim().toLowerCase();
          const aExact = shortName(a.name).toLowerCase() === normalizedQuery ? 0 : 1;
          const bExact = shortName(b.name).toLowerCase() === normalizedQuery ? 0 : 1;
          if (aExact !== bExact) return aExact - bExact;
          const canonical = (node) => ["Spider-Man", "Wolverine_(character)", "Black_Widow_(Natasha_Romanova)", "Doctor_Strange", "Deadpool", "Rockman_(character)"].includes(node.id) ? 0 : 1;
          return canonical(a) - canonical(b);
        })
        .slice(0, 8)
        .forEach((node) => {
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = node.name;
          button.addEventListener("click", () => {
            selectGameNode(node.id);
            box.replaceChildren();
          });
          box.appendChild(button);
        });
    }

    function finishGame() {
      const readout = currentReadout();
      const lines = [
        ["Random removal", attackValue("Random removal", 10)],
        ["Degree", attackValue("Degree (static)", 10)],
        ["Betweenness", attackValue("Betweenness (static)", 10)],
        ["Adaptive betweenness", attackValue("Adaptive betweenness", 10)],
      ];
      const beaten = lines.filter(([, value]) => readout.giant / data.original_nodes < value).map(([label]) => label);
      $("#game-result").hidden = false;
      $("#game-result").innerHTML = `<strong>Your damage score: ${readout.damage.toFixed(1)}%</strong><p>After 10 removals you left ${readout.giant} of 277 nodes in the giant component.</p><p>${beaten.length ? `You beat ${beaten.join(", ")}.` : "The precomputed strategies still broke the network faster."} Adaptive betweenness finishes at ${(100 - attackValue("Adaptive betweenness", 10) * 100).toFixed(1)}% remaining.</p>`;
    }

    function attackValue(strategy, step) {
      return data.attacks[strategy].find((row) => row.removed === step).remaining;
    }

    $("#character-search").addEventListener("input", (event) => renderSearchResults(event.target.value));
    document.querySelectorAll(".clue-button").forEach((button) => button.addEventListener("click", () => {
      state.clue = button.dataset.clue;
      document.querySelectorAll(".clue-button").forEach((item) => item.classList.toggle("is-active", item === button));
      renderGame();
    }));
    $("#remove-node").addEventListener("click", () => {
      if (!state.selected || state.removed.size >= 10) return;
      const selectedId = state.selected;
      const name = nodeById[selectedId].name;
      const spotlight = $("#character-spotlight");
      const button = $("#remove-node");
      button.disabled = true;
      spotlight.classList.add("spotlight-exit");
      window.setTimeout(() => {
        state.removed.add(selectedId);
        state.removalHistory.push({ name, damage: nodeById[selectedId].nodes_outside_giant });
        state.selected = null;
        const readout = currentReadout();
        spotlight.classList.remove("spotlight-exit");
        renderGame();
        $("#game-message").innerHTML = `<strong>${name.toUpperCase()} REMOVED</strong><br>${readout.separated} characters lost contact with the giant component.<br><em>${gameFeedback(readout)}</em>`;
        if (state.removed.size === 10) finishGame();
      }, 240);
    });
    $("#reset-game").addEventListener("click", () => {
      state.removed.clear();
      state.removalHistory = [];
      state.selected = null;
      $("#character-search").value = "";
      $("#game-result").hidden = true;
      renderGame();
    });
    renderGame();
    $("#hero-network").appendChild(networkSvg($("#hero-network"), {
      width: 900,
      height: 500,
      highlights: {
        "Spider-Man": "spider",
        "Rockman_(character)": "rockman",
        "Wolverine_(character)": "wolverine",
        "Black_Widow_(Natasha_Romanova)": "widow",
      },
    }));

    initTransformations();
    initQuiz();
    initLandscape();
    initRace();
    initNullModel();

    function initTransformations() {
      if (!$("#suspect-controls")) return;
      const selected = data.selected[0];
      let currentTransform = selected;
      const controls = $("#suspect-controls");
      data.selected.forEach((id) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = shortName(nodeById[id].name);
        button.className = "suspect-button";
        button.addEventListener("click", () => {
          currentTransform = id;
          renderTransformation(id);
        });
        controls.appendChild(button);
      });
      renderTransformation(selected);
      $("#transform-play").addEventListener("click", () => {
        renderTransformation(currentTransform, true);
      });
      const multiples = $("#small-multiples");
      data.selected.forEach((id) => {
        const card = document.createElement("article");
        card.className = "mini-network";
        card.innerHTML = `<h3>${shortName(nodeById[id].name)}</h3><div></div><strong>${data.removals[id].nodes_outside_giant} disconnected</strong>`;
        card.querySelector("div").appendChild(networkSvg(card, { removed: new Set([id]), selected: id, width: 250, height: 150, beforeAfter: true }));
        multiples.appendChild(card);
      });
    }

    function renderTransformation(id, animate = false) {
      document.querySelectorAll(".suspect-button").forEach((button) => button.classList.toggle("is-active", button.textContent === shortName(nodeById[id].name)));
      const stage = $("#before-after");
      stage.replaceChildren();
      const before = document.createElement("div");
      before.className = "transform-panel";
      before.innerHTML = "<span>Before</span>";
      before.appendChild(networkSvg(before, { width: 520, height: 300, beforeAfter: true }));
      const after = document.createElement("div");
      after.className = "transform-panel";
      after.innerHTML = "<span>After removal</span>";
      after.appendChild(networkSvg(after, { removed: new Set([id]), width: 520, height: 300, beforeAfter: true }));
      if (animate) after.querySelector("svg").classList.add("transform-after");
      stage.append(before, after);
      const row = nodeById[id];
      const result = data.removals[id];
      $("#transformation-note").innerHTML = `<strong>${shortName(row.name)}</strong><b>${result.nodes_outside_giant} nodes outside the giant component</b><span>Betweenness rank #${row.betweenness_rank} · ${row.degree} direct neighbours</span>`;
    }

    function initQuiz() {
      let round = 0;
      let score = 0;
      function renderRound() {
        const pair = data.quiz[round];
        $("#quiz-prompt").innerHTML = `<span>Round ${round + 1} / ${data.quiz.length}</span><strong>Who does more damage if removed?</strong><small>Pick one. The network will reveal the answer.</small>`;
        const options = $("#quiz-options");
        options.replaceChildren();
        pair.forEach((id) => {
          const button = document.createElement("button");
          button.type = "button";
          button.innerHTML = `${visualMarkup(nodeById[id], true)}<b>${shortName(nodeById[id].name)}</b><small>${nodeById[id].betweenness_rank ? `betweenness rank #${nodeById[id].betweenness_rank}` : ""}</small>`;
          button.addEventListener("click", () => answer(id, pair));
          options.appendChild(button);
        });
        $("#quiz-feedback").textContent = `Score: ${score} / ${data.quiz.length}`;
      }
      function answer(id, pair) {
        const actual = pair.slice().sort((a, b) => data.removals[b].nodes_outside_giant - data.removals[a].nodes_outside_giant)[0];
        if (id === actual) score += 1;
        $("#quiz-feedback").innerHTML = `<strong>${id === actual ? "Correct." : "Not this time."}</strong> ${shortName(nodeById[actual].name)} separates ${data.removals[actual].nodes_outside_giant} nodes; ${shortName(nodeById[id].name)} separates ${data.removals[id].nodes_outside_giant}. <button type="button" id="next-quiz">${round === data.quiz.length - 1 ? "Play again" : "Next comparison"}</button>`;
        $("#next-quiz").addEventListener("click", () => {
          if (round === data.quiz.length - 1) { round = 0; score = 0; } else round += 1;
          renderRound();
        });
        document.querySelectorAll("#quiz-options button").forEach((button) => { button.disabled = true; });
      }
      renderRound();
    }

    function initLandscape() {
      const render = () => {
        const width = 920;
        const height = 500;
        const svg = svgElement("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Betweenness versus knockout damage scatterplot" });
        const colorMode = $("#landscape-color").value;
        const sizeMode = $("#landscape-size").value;
        const query = $("#landscape-search").value.toLowerCase();
        const x = (value) => 58 + (value / 0.25) * (width - 100);
        const y = (value) => height - 48 - (value / 0.02) * (height - 90);
        svg.appendChild(svgElement("line", { x1: 58, y1: height - 48, x2: width - 30, y2: height - 48, class: "chart-axis" }));
        svg.appendChild(svgElement("line", { x1: 58, y1: 25, x2: 58, y2: height - 48, class: "chart-axis" }));
        const xLabel = svgElement("text", { x: width / 2, y: height - 10, class: "chart-axis-label" }); xLabel.textContent = "Betweenness"; svg.appendChild(xLabel);
        const yLabel = svgElement("text", { x: 14, y: height / 2, class: "chart-axis-label", transform: `rotate(-90 14 ${height / 2})` }); yLabel.textContent = "Knockout damage"; svg.appendChild(yLabel);
        data.nodes.forEach((node) => {
          const colourValue = colorMode === "degree" ? node.degree : colorMode === "pagerank" ? node.pagerank : node.betweenness_z;
          const sizeValue = sizeMode === "degree" ? Math.sqrt(node.degree) : Math.sqrt(node.pagerank * 10000);
          const color = colorMode === "z" ? zColor(colourValue) : `hsl(${clamp(235 - colourValue * (colorMode === "degree" ? 3 : 9000), 0, 235)}, 75%, 62%)`;
          const match = query && node.name.toLowerCase().includes(query);
          const circle = svgElement("circle", { cx: x(node.betweenness), cy: y(node.knockout_damage), r: clamp(2 + sizeValue, 3, 13), fill: color, class: `landscape-dot${match ? " landscape-dot--match" : ""}`, tabindex: "0" });
          circle.addEventListener("mouseenter", () => { $("#landscape-hover").innerHTML = `<strong>${node.name}</strong> · degree ${node.degree} · betweenness ${node.betweenness.toFixed(3)} · PageRank ${node.pagerank.toFixed(3)} · knockout ${node.nodes_outside_giant} outside · z ${node.betweenness_z.toFixed(2)}`; });
          svg.appendChild(circle);
        });
        ["Spider-Man", "Wolverine_(character)", "Rockman_(character)"].forEach((id) => {
          const node = nodeById[id]; if (!node) return;
          const label = svgElement("text", { x: x(node.betweenness) + 7, y: y(node.knockout_damage) - 7, class: "landscape-label" }); label.textContent = shortName(node.name); svg.appendChild(label);
        });
        $("#landscape").replaceChildren(svg);
      };
      ["landscape-search", "landscape-color", "landscape-size"].forEach((id) => $(`#${id}`).addEventListener("input", render));
      render();
    }

    function initRace() {
      let step = 0;
      let timer = null;
      const strategies = ["Adaptive betweenness", "Betweenness (static)", "Degree (static)", "Closeness (static)", "Random removal"];
      const colors = ["#ffe34f", "#55dde0", "#ff7a45", "#b6a7ff", "#71809b"];
      function render() {
        const width = 920, height = 470;
        const svg = svgElement("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Animated attack strategy race" });
        const px = (value) => 58 + (value / 100) * (width - 94);
        const py = (value) => height - 45 - value * (height - 80);
        svg.appendChild(svgElement("line", { x1: 58, y1: 25, x2: 58, y2: height - 45, class: "chart-axis" }));
        svg.appendChild(svgElement("line", { x1: 58, y1: height - 45, x2: width - 36, y2: height - 45, class: "chart-axis" }));
        strategies.forEach((strategy, index) => {
          const rows = data.attacks[strategy].filter((row) => row.removed <= step);
          const path = rows.map((row, rowIndex) => `${rowIndex ? "L" : "M"}${px(row.removed)},${py(row.remaining)}`).join(" ");
          svg.appendChild(svgElement("path", { d: path, class: "race-line", stroke: colors[index] }));
          const last = rows[rows.length - 1];
          const label = svgElement("text", { x: px(last.removed) + 7, y: py(last.remaining) + 4, class: "race-label", fill: colors[index] }); label.textContent = strategy.replace(" (static)", ""); svg.appendChild(label);
        });
        $("#race-chart").replaceChildren(svg);
        $("#race-step").textContent = `${step} / 100`;
        $("#race-reveal").classList.toggle("is-visible", step >= 100);
        const board = $("#race-leaderboard"); board.replaceChildren();
        strategies.forEach((strategy, index) => {
          const remaining = data.attacks[strategy].find((row) => row.removed === step).remaining;
          board.insertAdjacentHTML("beforeend", `<div class="${step >= 100 && strategy === "Adaptive betweenness" ? "is-winner" : ""}"><span style="--bar:${remaining * 100}%;--race-color:${colors[index]}">${strategy.replace(" (static)", "")}</span><b>${(remaining * 100).toFixed(1)}%</b></div>`);
        });
      }
      function play() {
        if (timer) { clearInterval(timer); timer = null; $("#race-play").textContent = "Resume race"; return; }
        $("#race-play").textContent = "Pause";
        timer = setInterval(() => { if (step >= 100) { clearInterval(timer); timer = null; $("#race-play").textContent = "Replay"; return; } step += 1; render(); }, Number($("#race-speed").value));
      }
      $("#race-play").addEventListener("click", play);
      $("#race-reset").addEventListener("click", () => { clearInterval(timer); timer = null; step = 0; $("#race-play").textContent = "Start race"; render(); });
      $("#race-speed").addEventListener("input", () => { if (timer) { clearInterval(timer); timer = null; play(); } });
      render();
    }

    function initNullModel() {
      const controls = $("#null-controls");
      const ids = Object.keys(data.null_samples);
      ids.forEach((id, index) => {
        const button = document.createElement("button"); button.type = "button"; button.textContent = shortName(nodeById[id].name); button.className = "suspect-button"; button.addEventListener("click", () => renderNull(id)); controls.appendChild(button);
        if (index === 0) button.classList.add("is-active");
      });
      renderNull(ids[0]);
      function renderNull(id) {
        document.querySelectorAll("#null-controls .suspect-button").forEach((button) => button.classList.toggle("is-active", button.textContent === shortName(nodeById[id].name)));
        const samples = data.null_samples[id];
        const real = nodeById[id].betweenness;
        const min = Math.min(...samples, real);
        const max = Math.max(...samples, real);
        const bins = Array.from({ length: 18 }, () => 0);
        samples.forEach((value) => bins[Math.min(17, Math.floor((value - min) / (max - min || 1) * 18))] += 1);
        const width = 760, height = 360;
        const svg = svgElement("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": `Null model distribution for ${nodeById[id].name}` });
        const maxBin = Math.max(...bins);
        bins.forEach((count, index) => svg.appendChild(svgElement("rect", { x: 45 + index * 35, y: height - 45 - count / maxBin * 230, width: 28, height: count / maxBin * 230, class: "null-bar" })));
        const realX = 45 + (real - min) / (max - min || 1) * 630;
        svg.appendChild(svgElement("line", { x1: realX, y1: 25, x2: realX, y2: height - 45, class: "null-real-line" }));
        const label = svgElement("text", { x: clamp(realX + 8, 50, width - 180), y: 30, class: "null-real-label" }); label.textContent = `REAL ${shortName(nodeById[id].name).toUpperCase()}`; svg.appendChild(label);
        $("#null-chart").replaceChildren(svg);
        $("#null-note").innerHTML = `<strong>${shortName(nodeById[id].name)}</strong><b>${nodeById[id].betweenness_z >= 0 ? "+" : ""}${nodeById[id].betweenness_z.toFixed(2)} standard deviations</b><span>The real betweenness is ${nodeById[id].betweenness_z >= 3 ? "far beyond" : "within"} the degree-preserving rewired distribution.</span>`;
      }
    }

    function zColor(value) {
      const t = clamp((value + 3) / 13, 0, 1);
      return `hsl(${240 - t * 210}, 78%, 58%)`;
    }
  }
})();
