(() => {
  "use strict";
  const limit = Number(document.body.dataset.limit);
  const status = document.querySelector("#adjacent-status");
  const pad = (number) => String(number).padStart(2, "0");
  const summarize = (draws) => {
    const values = Array.from({ length: 39 }, (_, index) => ({ number:index + 1, count:0 }));
    draws.forEach((draw) => (draw.numbers || []).forEach((number) => { values[number - 1].count += 1; }));
    return values.sort((a, b) => b.count - a.count || a.number - b.number);
  };
  const ball = (number, className = "") => `<span class="ball ${className}" data-number="${number}">${pad(number)}</span>`;
  function frequencyPanel(draws, drawn) {
    const groups = new Map();
    summarize(draws).filter((item) => item.count > 0).forEach((item) => {
      const values = groups.get(item.count) || []; values.push(item.number); groups.set(item.count, values);
    });
    return `<section class="panel source"><header><p>資料範圍</p><h1>近 ${limit}<small>期</small></h1></header><p class="group-note">橘球：與本期開出球上下左右相鄰；紅球：開出球彼此緊鄰</p><div class="frequency-groups">${[...groups.entries()].map(([count, numbers]) => `<article class="frequency-group"><strong>${count}<small>次</small></strong><div>${numbers.map((number) => ball(number, drawn.has(number) ? "drawn" : "")).join("")}</div></article>`).join("")}</div></section>`;
  }
  function findAdjacency(container, drawn) {
    const rows = [];
    [...container.querySelectorAll(".frequency-group>div")].forEach((line) => {
      const entries = [...line.querySelectorAll(".ball")].map((element) => {
        const rect = element.getBoundingClientRect(); return { element, number:Number(element.dataset.number), x:rect.left + rect.width / 2, y:rect.top + rect.height / 2, width:rect.width };
      });
      if (entries.length) rows.push({ y:entries[0].y, balls:entries });
    });
    const adjacent = new Set(), connected = new Set();
    drawn.forEach((number) => {
      const rowIndex = rows.findIndex((row) => row.balls.some((entry) => entry.number === number));
      const row = rows[rowIndex]; if (!row) return;
      const index = row.balls.findIndex((entry) => entry.number === number); const target = row.balls[index];
      [row.balls[index - 1], row.balls[index + 1]].filter(Boolean).forEach((candidate) => {
        if (drawn.has(candidate.number)) { connected.add(number); connected.add(candidate.number); } else adjacent.add(candidate.number);
      });
      [rows[rowIndex - 1], rows[rowIndex + 1]].filter(Boolean).forEach((nearRow) => {
        const candidate = nearRow.balls.filter((entry) => Math.abs(entry.x - target.x) <= target.width / 2).sort((a,b) => Math.abs(a.x-target.x)-Math.abs(b.x-target.x))[0];
        if (!candidate) return; if (drawn.has(candidate.number)) { connected.add(number); connected.add(candidate.number); } else adjacent.add(candidate.number);
      });
    });
    return { adjacent, connected };
  }
  function renderSummary(highlights) {
    const values = [...highlights.adjacent].sort((a,b) => a-b);
    return `<section class="panel summary"><header><p>近 ${limit} 期</p><h1>相鄰<small>球號</small></h1></header>${values.length ? `<p class="group-note">上下左右亮燈的球號</p><article class="frequency-group"><strong>${values.length}<small>個</small></strong><div>${values.map((number) => ball(number, "adjacent")).join("")}</div></article>` : '<p class="summary-empty">本範圍沒有相鄰亮燈球號。</p>'}</section>`;
  }
  async function load() {
    try {
      const response = await fetch("data/daily539.json", { cache:"no-store" }); if (!response.ok) throw new Error("無法讀取開獎資料");
      const payload = await response.json(); const draws = payload.draws.slice(0, limit); const drawn = new Set(draws[0]?.numbers || []);
      document.querySelector("#adjacent-results").innerHTML = `<div class="period-layout">${frequencyPanel(draws, drawn)}<div class="summary-slot"></div></div>`;
      const highlights = findAdjacency(document.querySelector(".source"), drawn);
      document.querySelectorAll(".source .ball").forEach((element) => { const number = Number(element.dataset.number); if (highlights.connected.has(number)) element.classList.add("connected"); else if (highlights.adjacent.has(number)) element.classList.add("adjacent"); });
      document.querySelector(".summary-slot").innerHTML = renderSummary(highlights);
      status.textContent = `已載入近 ${draws.length} 期；最新 ${payload.latest_draw_no}期 · ${payload.latest_draw_date}`;
    } catch (error) { status.textContent = "資料讀取失敗，請重新整理後再試。"; }
  }
  load();
})();
