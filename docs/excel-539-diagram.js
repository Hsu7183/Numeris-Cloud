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
    const adjacentGroups = [
      [4, [19, 39]],
      [3, [4, 23]],
      [2, [7, 8, 9, 14, 16, 17, 20, 24, 35]],
      [1, [1, 2, 3, 5, 6, 10, 12, 13, 15, 18, 21, 25, 26, 31, 32, 36, 38]],
      [0, [11, 22, 27, 28, 29, 30, 33, 34, 37]],
    ];
    const adjacentRows = adjacentGroups.map(([count, numbers]) => `<article class="adjacent-row summary-count-${count}"><strong>${count}次</strong><div>${numbers.map((number) => `<span class="adjacent-number">${pad(number)}</span>`).join("")}</div></article>`).join("");
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
            <header><strong>相鄰</strong><span>相鄰統計號碼</span></header>
            <div class="adjacent-list">${adjacentRows}</div>
          </section>
        </div>
        <p>空白紅圈：此號碼於最新一期開出。右側依相鄰統計次數分組顯示號碼。</p>
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
