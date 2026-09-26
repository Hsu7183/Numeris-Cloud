(() => {
  "use strict";
  const ranges = [[1, 13], [14, 26], [27, 39]];
  const status = document.querySelector("#excel539-status");
  const pad = (number) => String(number).padStart(2, "0");
  const grid = (start, end, draws) => {
    const numbers = Array.from({ length:end - start + 1 }, (_, index) => start + index);
    const headers = numbers.map((number) => `<th>${pad(number)}</th>`).join("");
    const rows = draws.map((draw, index) => {
      const values = new Set(draw.numbers || []);
      const cells = numbers.map((number) => values.has(number)
        ? `<td title="${draw.draw_no}期 · ${draw.draw_date} · ${pad(number)}"><span class="draw-mark">○</span></td>`
        : "<td></td>").join("");
      return `<tr><th class="row-label">${index + 1}</th>${cells}</tr>`;
    }).join("");
    return `<section class="excel539-block"><header><strong>539</strong><span>${pad(start)}–${pad(end)} 號</span></header><table class="excel539-table"><thead><tr><th class="row-label">期</th>${headers}</tr></thead><tbody>${rows}</tbody></table><p class="excel539-note">紅圈表示該期開出號碼</p></section>`;
  };
  const resultsGrid = (draw) => {
    const numbers = draw?.numbers || [];
    const rows = Array.from({ length: 5 }, (_, index) => {
      const number = numbers[index];
      return `<tr><th class="row-label">${index + 1}</th><td>${number ? `<span class="result-number">${pad(number)}</span>` : ""}</td></tr>`;
    }).join("");
    return `<section class="excel539-block excel539-results"><header><strong>539</strong><span>本期開獎號碼</span></header><table class="excel539-table"><thead><tr><th class="row-label">順序</th><th>號碼</th></tr></thead><tbody>${rows}</tbody></table><p class="excel539-note">最新一期五個開出號碼</p></section>`;
  };
  async function load() {
    try {
      const response = await fetch("data/daily539.json", { cache:"no-store" });
      if (!response.ok) throw new Error("資料讀取失敗");
      const payload = await response.json();
      const draws = (payload.draws || []).slice(0, 1);
      document.querySelector("#excel539-grids").innerHTML = `${ranges.map(([start, end]) => grid(start, end, draws)).join("")}${resultsGrid(draws[0])}`;
      status.textContent = `已填入最新一期：${draws[0]?.draw_no || "—"}期 · ${draws[0]?.draw_date || "—"}`;
    } catch (error) { status.textContent = "開獎資料讀取失敗，請重新整理後再試。"; }
  }
  load();
})();
