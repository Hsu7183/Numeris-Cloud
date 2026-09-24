(() => {
  "use strict";
  const topHeaders = [[19, 28, 37], [1, 10, 29, 38], [2, 11, 20, 39], [3, 12, 21, 30], [4, 13, 22, 31], [5, 14, 23, 32], [6, 15, 24, 33], [7, 16, 25, 34], [8, 17, 26, 35], [9, 18, 27, 36]];
  const bottomHeaders = [[1, 5, 9, 13, 17, 21, 25, 29, 33, 37], [2, 6, 10, 14, 18, 22, 26, 30, 34, 38], [3, 7, 11, 15, 19, 23, 27, 31, 35, 39], [4, 8, 12, 16, 20, 24, 28, 32, 36, ""]];
  const pad = (value) => value === "" ? "" : String(value).padStart(2, "0");
  function board(headers, draws) {
    const header = headers.map((value) => `<th>${value === "" ? "" : `<span class="number-ball">${pad(value)}</span>`}</th>`).join("");
    const rows = Array.from({ length: 20 }, (_, index) => {
      const row = index + 1;
      const occurrences = draws[index]?.occurrences || {};
      const cells = headers.map((value) => value !== "" && occurrences[value]
        ? `<td class="winning-cell" title="第 ${row} 期開獎號碼 ${pad(value)}，第 ${occurrences[value]} 次出現"><b class="count-ball count-ball-${Math.min(occurrences[value], 4)}">${occurrences[value]}</b></td>`
        : `<td><span>${row}</span></td>`).join("");
      return `<tr><th>${row}</th>${cells}</tr>`;
    }).join("");
    return `<section class="pattern-board"><table><thead><tr><th>行</th>${header}</tr></thead><tbody>${rows}</tbody></table></section>`;
  }
  function render(draws) {
    document.querySelector("#pattern-grid").innerHTML = `<section class="pattern-half upper-half"><h1>上半部</h1><div>${topHeaders.map((headers) => board(headers, draws)).join("")}</div></section><section class="pattern-half lower-half"><h1>下半部</h1><div>${bottomHeaders.map((headers) => board(headers, draws)).join("")}</div></section>`;
  }
  function withOccurrenceCounts(draws) {
    const counts = new Map();
    return draws.map((draw) => {
      const occurrences = {};
      (draw.pools?.main || []).forEach((value) => {
        const count = (counts.get(value) || 0) + 1;
        counts.set(value, count);
        occurrences[value] = count;
      });
      return { ...draw, occurrences };
    });
  }
  async function loadDraws() {
    try {
      const response = await fetch("data/daily539.json", { cache: "no-store" });
      if (!response.ok) throw new Error("無法讀取開獎資料");
      const draws = ((await response.json()).draws || []).slice(0, 12).reverse().map((draw) => ({ ...draw, pools: { main: draw.numbers } }));
      document.querySelector("#pattern-status").textContent = `115/08/29～115/09/21：已填入 ${draws.length} 期開獎號碼（第 1 行為 8/29；同號第 1、2、3 次出現依序標示 1、2、3）`;
      render(withOccurrenceCounts(draws));
    } catch (error) {
      document.querySelector("#pattern-status").textContent = "開獎資料讀取失敗，請重新整理後再試。";
      render([]);
    }
  }
  loadDraws();
})();
