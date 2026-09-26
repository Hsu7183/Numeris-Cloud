(() => {
  "use strict";
  const pad = (number) => String(number).padStart(2, "0");
  const status = document.querySelector("#sheet-status");
  const renderNumberGrid = (draw) => {
    const drawn = new Set(draw.numbers || []);
    const headers = Array.from({ length: 20 }, (_, index) => `<th>${index + 1}</th>`).join("");
    const labels = [4, 3, 2, 1, 0];
    const rows = labels.map((label) => {
      const cells = Array.from({ length: 20 }, (_, index) => {
        const number = index + 1;
        return `<td>${label === 1 && drawn.has(number) ? `<span class="circle">○</span>` : ""}</td>`;
      }).join("");
      return `<tr><th>${label}</th>${cells}</tr>`;
    }).join("");
    document.querySelector("#number-grid").innerHTML = `<thead><tr><th>行</th>${headers}</tr></thead><tbody>${rows}</tbody>`;
  };
  const renderAdjacentGrid = (draws) => {
    const windows = [20, 50, 100, 200];
    const rows = windows.map((limit) => {
      const counts = new Map(Array.from({ length: 39 }, (_, index) => [index + 1, 0]));
      draws.slice(0, limit).forEach((draw) => {
        (draw.numbers || []).forEach((number) => {
          for (const neighbor of [number - 1, number + 1]) {
            if (neighbor >= 1 && neighbor <= 39) counts.set(neighbor, counts.get(neighbor) + 1);
          }
        });
      });
      const top = [...counts.entries()].filter(([, count]) => count > 0)
        .sort((first, second) => second[1] - first[1] || first[0] - second[0]).slice(0, 8);
      return `<article class="adjacent-row"><strong>近 ${limit} 期</strong><div>${top.map(([number, count]) => `<span class="adjacent-ball" title="${count} 次">${pad(number)}<small>${count}</small></span>`).join("")}</div></article>`;
    }).join("");
    document.querySelector("#adjacent-grid").innerHTML = rows;
  };
  async function load() {
    try {
      const response = await fetch("data/daily539.json", { cache: "no-store" });
      if (!response.ok) throw new Error("資料讀取失敗");
      const payload = await response.json();
      const draw = payload.draws?.[0];
      if (!draw) throw new Error("沒有開獎資料");
      renderNumberGrid(draw);
      renderAdjacentGrid(payload.draws || []);
      status.textContent = `已填入最新一期：${draw.draw_no}期 · ${draw.draw_date}`;
    } catch (error) {
      status.textContent = "開獎資料讀取失敗，請重新整理後再試。";
    }
  }
  load();
})();
