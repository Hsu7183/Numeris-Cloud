(() => {
  "use strict";
  const payload = JSON.parse(localStorage.getItem("daily539OutputData") || "null");
  const wrap = document.querySelector("#matrix-wrap");
  if (!payload?.draws?.length) {
    wrap.innerHTML = '<p class="empty">尚未讀取球號。請返回統計頁按「抓取近 20 期獎號」。</p>';
    return;
  }

  const latestNumbers = payload.draws[0].numbers;
  const rangeValues = [20, 50, 100, 200];

  function groupedNumbers(limit) {
    const counts = Array.from({ length: 39 }, () => 0);
    payload.draws.slice(0, limit).forEach((draw) => draw.numbers.forEach((number) => {
      counts[number - 1] += 1;
    }));
    const groups = new Map();
    counts.forEach((count, index) => {
      if (!count) return;
      const numbers = groups.get(count) || [];
      numbers.push(index + 1);
      groups.set(count, numbers);
    });
    return [...groups.entries()]
      .sort((first, second) => second[0] - first[0])
      .map(([, numbers]) => numbers);
  }

  function neighboringNumbers(limit, target) {
    const groups = groupedNumbers(limit);
    const groupIndex = groups.findIndex((numbers) => numbers.includes(target));
    const row = groups[groupIndex] || [];
    const index = row.indexOf(target);
    const neighbours = new Set([row[index - 1], row[index + 1]]);
    for (const nearbyRow of [groups[groupIndex - 1], groups[groupIndex + 1]]) {
      if (nearbyRow?.[index] !== undefined) neighbours.add(nearbyRow[index]);
    }
    neighbours.delete(undefined);
    neighbours.delete(target);
    return neighbours;
  }

  const headers = Array.from({ length: 39 }, (_, index) => `<th>${index + 1}</th>`).join("");
  const scoreByNumber = new Map(Array.from({ length: 39 }, (_, index) => [index + 1, 0]));
  const rows = rangeValues.map((limit) => latestNumbers.map((number, index) => {
    const neighbours = neighboringNumbers(limit, number);
    neighbours.forEach((neighbour) => {
      const key = `${limit}:${neighbour}`;
      scoreByNumber.set(key, (scoreByNumber.get(key) || 0) + 1);
    });
    const cells = Array.from({ length: 39 }, (_, cellIndex) => {
      const value = cellIndex + 1;
      const type = neighbours.has(value) ? "neighbor" : "";
      return `<td class="${type}">${type ? String(value).padStart(2, "0") : ""}</td>`;
    }).join("");
    return `<tr>${index === 0 ? `<th class="range" rowspan="5">${limit}<small>期</small></th>` : ""}<th class="ball-index">${index + 1}</th><th class="ball-value">${String(number).padStart(2, "0")}</th>${cells}</tr>`;
  }).join("")).join("");
  rangeValues.forEach((limit) => {
    for (let number = 1; number <= 39; number += 1) {
      const appearances = scoreByNumber.get(`${limit}:${number}`) || 0;
      if (appearances) {
        scoreByNumber.set(number, scoreByNumber.get(number) + 1 + (appearances - 1) * 0.1);
      }
    }
  });
  const scores = Array.from({ length: 39 }, (_, index) => ({
    number: index + 1,
    score: scoreByNumber.get(index + 1),
  })).sort((first, second) => second.score - first.score || first.number - second.number);
  const scoreStrip = scores.map((item, index) => `<div class="score-item">
    <span>${index + 1}</span><b>${String(item.number).padStart(2, "0")}</b><strong>${item.score.toFixed(1)}</strong>
  </div>`).join("");
  const scoreLine = scores.map((item, index) => `<div class="score-line-item">
    <span>${index + 1}</span><b>${String(item.number).padStart(2, "0")}</b><strong>${item.score.toFixed(1)}</strong>
  </div>`).join("");
  document.querySelector("#output-meta").textContent = `最新 ${payload.latest_draw_no} 期 · ${payload.latest_draw_date} · 每期數範圍各顯示 5 顆球與相鄰球`;
  const columns = '<col class="range-col"><col class="index-col"><col class="value-col">' + '<col class="matrix-col">'.repeat(39);
  wrap.innerHTML = `<table><colgroup>${columns}</colgroup><thead><tr><th rowspan="2">期數</th><th rowspan="2">球序</th><th rowspan="2">開出球</th><th colspan="39">球號 1–39</th></tr><tr>${headers}</tr></thead><tbody>${rows}</tbody></table><p class="key"><span class="neighbor-key"></span>相鄰球（顯示球號）</p><section class="score-section"><div><strong>相鄰分數排名</strong><span>每期數範圍首次出線 1 分；同範圍每多出現一次加 0.1 分。</span></div><div class="score-line">${scoreLine}</div><div class="score-strip">${scoreStrip}</div></section>`;
})();
