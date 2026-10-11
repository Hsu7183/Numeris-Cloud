(() => {
  "use strict";
  const topHeaders = Array.from({length: 10}, (_, i) => Array.from({length: 49}, (_, n) => n + 1).filter(n => n % 10 === i));
  const bottomHeaders = Array.from({length: 4}, (_, i) => Array.from({length: 49}, (_, n) => n + 1).filter(n => (n - 1) % 4 === i));
  const pad = (value) => value === "" ? "" : String(value).padStart(2, "0");
  function board(headers, draws) {
    const header = headers.map((value) => `<th>${pad(value)}</th>`).join("");
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
      const response = await fetch("../data/lotto649.json", { cache: "no-store" });
      if (!response.ok) throw new Error("無法讀取開獎資料");
      const draws = ((await response.json()).draws || []).slice(0, 12).reverse().map((draw) => ({ ...draw, pools: { main: draw.numbers } }));
      document.querySelector("#pattern-status").textContent = `已填入近 ${draws.length} 期，主號 01–49；同號累計出現次數依序標示。`;
      render(withOccurrenceCounts(draws));
    } catch (error) {
      document.querySelector("#pattern-status").textContent = "開獎資料讀取失敗，請重新整理後再試。";
      render([]);
    }
  }
  loadDraws();
})();
