(() => {
  "use strict";
  const pad = (number) => String(number).padStart(2, "0");
  const status = document.querySelector("#sheet-status");
  const renderNumberGrid = (draw) => {
    const drawn = new Set(draw.numbers || []);
    const headers = Array.from({ length: 20 }, (_, index) => `<th>${index + 1}</th>`).join("");
    const rows = Array.from({ length: 10 }, (_, row) => {
      const cells = Array.from({ length: 20 }, (_, index) => {
        const number = index + 1;
        return `<td>${row === 0 && drawn.has(number) ? `<span class="circle">○</span>` : ""}</td>`;
      }).join("");
      return `<tr><th>${row + 1}</th>${cells}</tr>`;
    }).join("");
    document.querySelector("#number-grid").innerHTML = `<thead><tr><th>行</th>${headers}</tr></thead><tbody>${rows}</tbody>`;
  };
  const renderDrawGrid = (draw) => {
    const rows = Array.from({ length: 5 }, (_, index) => `<tr><th>${index + 1}</th><td>${pad(draw.numbers?.[index] || "")}</td></tr>`).join("");
    document.querySelector("#draw-grid").innerHTML = `<thead><tr><th>順序</th><th>號碼</th></tr></thead><tbody>${rows}</tbody>`;
  };
  async function load() {
    try {
      const response = await fetch("data/daily539.json", { cache: "no-store" });
      if (!response.ok) throw new Error("資料讀取失敗");
      const payload = await response.json();
      const draw = payload.draws?.[0];
      if (!draw) throw new Error("沒有開獎資料");
      renderNumberGrid(draw);
      renderDrawGrid(draw);
      status.textContent = `已填入最新一期：${draw.draw_no}期 · ${draw.draw_date}`;
    } catch (error) {
      status.textContent = "開獎資料讀取失敗，請重新整理後再試。";
    }
  }
  load();
})();
