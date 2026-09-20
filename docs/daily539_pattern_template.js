(() => {
  "use strict";
  const numbers = Array.from({ length: 39 }, (_, index) => index + 1);
  const headers = () => `<tr class="number-header"><th></th>${numbers.map((number) => `<th>${number}</th>`).join("")}</tr>`;
  const rows = (draws, offset) => Array.from({ length: 9 }, (_, index) => {
    const row = index + 1;
    const draw = draws[offset + index];
    const occurrences = draw?.occurrences || {};
    const cells = numbers.map((number) => occurrences[number]
      ? `<td class="winning-cell" title="${draw.draw_date}：${String(number).padStart(2, "0")} 第 ${occurrences[number]} 次"><b>${occurrences[number]}</b></td>`
      : "<td></td>").join("");
    return `<tr class="month-row"><th>${row}</th>${cells}</tr>`;
  }).join("");
  const block = (index, draws) => `<section class="month-block"><table>${index === 0 ? "" : headers()}<tbody>${rows(draws, index * 9)}</tbody></table></section>`;
  const withOccurrenceCounts = (draws) => {
    const counts = new Map();
    return draws.map((draw) => {
      const occurrences = {};
      (draw.numbers || []).forEach((number) => {
        const count = (counts.get(number) || 0) + 1;
        counts.set(number, count);
        occurrences[number] = count;
      });
      return { ...draw, occurrences };
    });
  };
  const render = (draws) => {
    document.querySelector("#month-grid").innerHTML = `<section class="month-title"><span>年</span><strong>　　月</strong><b>日　一　二　三　四　五　六</b></section><table class="top-number-header">${headers()}</table>${[0, 1, 2].map((index) => block(index, draws)).join("")}<footer>M 0 0 9</footer>`;
  };
  async function loadDraws() {
    try {
      const response = await fetch("data/daily539.json", { cache: "no-store" });
      if (!response.ok) throw new Error("無法讀取開獎資料");
      const payload = await response.json();
      const draws = withOccurrenceCounts((payload.draws || []).slice().reverse());
      document.querySelector("#month-status").textContent = `已填入近 ${draws.length} 期：第 1 行最早（${draws[0]?.draw_date || "—"}），第 12 行最新（${draws.at(-1)?.draw_date || "—"}）`;
      render(draws);
    } catch (error) {
      document.querySelector("#month-status").textContent = "開獎資料讀取失敗，請重新整理後再試。";
      render([]);
    }
  }
  loadDraws();
})();
