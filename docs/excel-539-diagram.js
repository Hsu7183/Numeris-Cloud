(() => {
  "use strict";
  const status = document.querySelector("#excel539-status");
  const target = document.querySelector("#excel539-grids");
  const pad = (number) => String(number).padStart(2, "0");

  function render(draw) {
    const drawn = new Set(draw.numbers || []);
    const headers = Array.from({ length: 20 }, (_, index) => `<th>${index + 1}</th>`).join("");
    const rowLabels = [4, 3, 2, 1, 0];
    const gridRows = rowLabels.map((label) => {
      const cells = Array.from({ length: 20 }, (_, index) => {
        const number = index + 1;
        const marked = label === 1 && drawn.has(number);
        return `<td>${marked ? `<span class="diagram-circle" aria-label="${pad(number)} 開出"></span>` : ""}</td>`;
      }).join("");
      return `<tr><th>${label}</th>${cells}</tr>`;
    }).join("");
    const adjacentNumbers = new Set();
    (draw.numbers || []).forEach((number) => {
      [number - 1, number + 1].forEach((neighbor) => {
        if (neighbor >= 1 && neighbor <= 39 && !drawn.has(neighbor)) adjacentNumbers.add(neighbor);
      });
    });
    const adjacentRows = `<article class="adjacent-row latest-adjacent-row"><strong>${draw.draw_no}期 · 最近一期</strong><div>${[...adjacentNumbers].sort((first, second) => first - second).map((number) => `<span class="adjacent-number">${pad(number)}</span>`).join("")}</div></article>`;
    target.innerHTML = `
      <section class="diagram-sheet" aria-label="今彩539號碼格表">
        <div class="diagram-topline">
          <div class="date-box"><b>年</b><b>月</b><b>日</b></div>
          <div class="diagram-title">539</div>
          <div class="diagram-caption">最新一期位置格</div>
        </div>
        <div class="diagram-content">
          <section class="number-board">
            <table><thead><tr><th>次數</th>${headers}</tr></thead><tbody>${gridRows}</tbody></table>
            <div class="blank-strips" aria-hidden="true"><i></i><i></i><i></i></div>
          </section>
          <section class="results-board adjacent-board">
            <header><strong>相鄰</strong><span>最近一期相鄰號碼</span></header>
            <div class="adjacent-list">${adjacentRows}</div>
          </section>
        </div>
        <p>空白紅圈：此號碼於最新一期開出。右側只列出此期五個開出號碼的相鄰號碼。</p>
      </section>`;
  }

  async function load() {
    try {
      const response = await fetch("data/daily539.json", { cache: "no-store" });
      if (!response.ok) throw new Error("資料讀取失敗");
      const payload = await response.json();
      const draw = payload.draws?.[0];
      if (!draw) throw new Error("沒有開獎資料");
      render(draw);
      status.textContent = `已填入最新一期：${draw.draw_no}期 · ${draw.draw_date}`;
    } catch (error) {
      status.textContent = "開獎資料讀取失敗，請重新整理後再試。";
    }
  }
  load();
})();
