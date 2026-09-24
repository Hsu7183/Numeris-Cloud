(() => {
  "use strict";
  const button = document.querySelector("#fetch-draws");
  const status = document.querySelector("#status");
  const results = document.querySelector("#results");
  let drawnNumbers = new Set();
  let adjacentNumbers = new Set();
  const ball = (number) => {
    const stateClass = drawnNumbers.has(number) ? "drawn-ball" : (
      adjacentNumbers.has(number) ? "adjacent-ball" : ""
    );
    return `<span class="ball ${stateClass}"><span class="ball-number">${String(number).padStart(2, "0")}</span></span>`;
  };
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[character]);

  function summarize(draws) {
    const numbers = Array.from({ length: 39 }, (_, index) => ({
      number: index + 1, count: 0, appearances: [],
    }));
    draws.forEach((draw, drawIndex) => draw.numbers.forEach((number) => {
      const summary = numbers[number - 1];
      summary.count += 1;
      summary.appearances.push({ drawIndex: drawIndex + 1, drawNo: draw.draw_no });
    }));
    return numbers.sort((first, second) => second.count - first.count || first.number - second.number);
  }

  function renderColumn(limit, draws, label = String(limit), groupSlice = null) {
    const frequencies = summarize(draws.slice(0, limit));
    const groups = new Map();
    frequencies.filter((item) => item.count > 0).forEach((item) => {
      const items = groups.get(item.count) || [];
      items.push(item.number);
      groups.set(item.count, items);
    });
    const groupEntries = [...groups.entries()];
    const displayedGroups = groupSlice ? groupEntries.slice(...groupSlice) : groupEntries;
    return `<section class="comparison-panel">
      <header><p>最近</p><h2>${label}<small>期</small></h2><span>共 ${Math.min(limit, draws.length)} 期${groupSlice ? " · 次數分段" : ""}</span></header>
      <p class="group-note">同一次數的球號併列</p>
      <div class="frequency-groups">${displayedGroups.map(([count, numbers]) => `
        <article class="frequency-group">
          <strong>${count}<small>次</small></strong>
          <div>${numbers.map(ball).join("")}</div>
        </article>`).join("")}</div>
    </section>`;
  }

  function renderPanels(draws, splitAt) {
    document.querySelector("#comparison-list").innerHTML = [
      renderColumn(20, draws),
      renderColumn(50, draws),
      renderColumn(100, draws),
      renderColumn(200, draws, "200①", [0, splitAt]),
      renderColumn(200, draws, "200②", [splitAt]),
    ].join("");
  }

  function chartAdjacency(panels) {
    const rows = [];
    for (const panel of panels) {
      const panelLeft = panel.getBoundingClientRect().left;
      const positionedBalls = [...panel.querySelectorAll(".ball")].map((element) => {
      const rect = element.getBoundingClientRect();
      return {
        element,
        number: Number(element.textContent),
        x: rect.left - panelLeft + rect.width / 2,
        y: rect.top + rect.height / 2,
        width: rect.width,
      };
      });
      const panelRows = [];
      for (const ballPosition of positionedBalls.sort((first, second) => first.y - second.y || first.x - second.x)) {
        const row = panelRows.at(-1);
        if (!row || Math.abs(row.y - ballPosition.y) > 3) {
          panelRows.push({ y: ballPosition.y, balls: [ballPosition] });
        } else {
          row.balls.push(ballPosition);
        }
      }
      rows.push(...panelRows);
    }
    rows.forEach((row) => row.balls.sort((first, second) => first.x - second.x));
    const result = { adjacent: new Set(), connectedDrawn: new Set() };
    for (const targetNumber of drawnNumbers) {
      const rowIndex = rows.findIndex((row) => row.balls.some((ballPosition) => ballPosition.number === targetNumber));
      const row = rows[rowIndex];
      const targetIndex = row?.balls.findIndex((ballPosition) => ballPosition.number === targetNumber) ?? -1;
      const target = targetIndex >= 0 ? row.balls[targetIndex] : null;
      if (!target) continue;
      for (const adjacent of [row.balls[targetIndex - 1], row.balls[targetIndex + 1]]) {
        if (!adjacent) continue;
        if (drawnNumbers.has(adjacent.number)) {
          result.connectedDrawn.add(targetNumber);
          result.connectedDrawn.add(adjacent.number);
        } else {
          result.adjacent.add(adjacent.number);
        }
      }
      for (const nearbyRow of [rows[rowIndex - 1], rows[rowIndex + 1]]) {
        if (!nearbyRow) continue;
        const aligned = nearbyRow.balls
          .filter((candidate) => Math.abs(candidate.x - target.x) <= target.width / 2)
          .sort((first, second) => Math.abs(first.x - target.x) - Math.abs(second.x - target.x))[0];
        if (!aligned) continue;
        if (drawnNumbers.has(aligned.number)) {
          result.connectedDrawn.add(targetNumber);
          result.connectedDrawn.add(aligned.number);
        } else {
          result.adjacent.add(aligned.number);
        }
      }
    }
    return result;
  }

  function renderAdjacentSummary(panelHighlights, label = "20／50／100／200 累計") {
    // 1–39 全部列入，未曾亮燈的球號也會顯示為 0 次。
    const counts = new Map(Array.from({ length: 39 }, (_, index) => [index + 1, 0]));
    panelHighlights.forEach((highlight) => {
      const scopeNumbers = new Set([
        ...highlight.adjacent,
        ...highlight.connectedDrawn,
      ]);
      scopeNumbers.forEach((number) => counts.set(number, (counts.get(number) || 0) + 1));
    });
    const groups = new Map();
    [...counts.entries()]
      .sort((first, second) => second[1] - first[1] || first[0] - second[0])
      .forEach(([number, count]) => {
        const values = groups.get(count) || [];
        values.push(number);
        groups.set(count, values);
      });
    return `<section class="comparison-panel adjacent-summary-panel">
      <header><p>跨期</p><h2>相鄰<small>統計</small></h2><span>${label}</span></header>
      <p class="group-note">含 0 次；各次數以不同顏色區隔</p>
      <div class="frequency-groups">${[...groups.entries()].map(([count, numbers]) => `
        <article class="frequency-group summary-count summary-count-${Math.min(count, 7)}">
          <strong>${count}<small>次</small></strong>
          <div>${numbers.map((number) => `<span class="ball summary-ball"><span class="ball-number">${String(number).padStart(2, "0")}</span></span>`).join("")}</div>
        </article>`).join("")}</div>
    </section>`;
  }

  function render(payload) {
    const latestNumbers = payload.draws[0].numbers;
    drawnNumbers = new Set(latestNumbers);
    document.querySelector("#range-title").textContent = `1–39 號 · 20 / 50 / 100 / 200（前後段）比較`;
    document.querySelector("#latest-draw").textContent = `${payload.latest_draw_no}期 · ${payload.latest_draw_date}`;
    const all200Groups = summarize(payload.draws.slice(0, 200)).filter((item) => item.count > 0);
    const distinct200Counts = [...new Set(all200Groups.map((item) => item.count))];
    const splitAt = Math.ceil(distinct200Counts.length / 2);
    adjacentNumbers = new Set();
    renderPanels(payload.draws, splitAt);
    const panels = [...document.querySelectorAll(".comparison-panel")];
    const panelHighlights = [
      chartAdjacency([panels[0]]),
      chartAdjacency([panels[1]]),
      chartAdjacency([panels[2]]),
      chartAdjacency([panels[3], panels[4]]),
    ];
    panels.forEach((panel, index) => {
      const highlights = panelHighlights[Math.min(index, 3)];
      panel.querySelectorAll(".ball").forEach((element) => {
        const number = Number(element.textContent);
        if (highlights.connectedDrawn.has(number)) {
          element.classList.add("connected-drawn-ball");
        } else if (highlights.adjacent.has(number)) {
          element.classList.add("adjacent-ball");
        }
      });
    });
    adjacentNumbers = panelHighlights[0].adjacent;
    document.querySelector("#comparison-list").insertAdjacentHTML(
      "beforeend",
      renderAdjacentSummary(panelHighlights),
    );
    const legend = document.querySelector("#highlight-legend");
    const formatNumbers = (numbers) => [...numbers].sort((a, b) => a - b)
      .map((number) => String(number).padStart(2, "0")).join("、");
    legend.innerHTML = `<span class="legend-dot drawn-dot"></span>開出球 <span class="legend-dot connected-dot"></span>開出球彼此緊鄰 <span class="legend-dot adjacent-dot"></span>上下左右亮燈；20期：${formatNumbers(adjacentNumbers)}`;
    legend.classList.remove("hidden");
    results.classList.remove("hidden");
  }

  button.addEventListener("click", async () => {
    button.disabled = true;
    button.classList.add("loading");
    status.textContent = "正在抓取今彩539資料…";
    try {
      const response = await fetch("data/daily539.json", { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || "資料暫時無法取得");
      render(payload);
      localStorage.setItem("daily539OutputData", JSON.stringify(payload));
      const updatedAt = payload.generated_at ? new Date(payload.generated_at).toLocaleString("zh-TW", { timeZone: "Asia/Taipei", hour12: false }) : "—";
      status.textContent = `已取得 ${payload.draw_count} 期資料 · 最新：${payload.latest_draw_date} · 資料更新：${updatedAt}`;
    } catch (error) {
      status.textContent = error.message || "抓取失敗，請稍後再試";
      status.classList.add("error");
    } finally {
      button.disabled = false;
      button.classList.remove("loading");
    }
  });

  button.click();
})();
