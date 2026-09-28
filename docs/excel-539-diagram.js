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
        const watermark = label === 3 || label === 1
          ? `<span style="color:#cfd6d1;font-family:Georgia,serif;font-size:.9rem;font-weight:700">${number}</span>`
          : "";
        const marked = label === 4 && drawn.has(number);
        const circle = marked ? `<span class="diagram-circle" aria-label="${pad(number)} 開出">○</span>` : "";
        return `<td>${watermark}${circle}</td>`;
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
          <div class="date-box" style="grid-template-columns:2fr 1fr 1fr"><b style="font-size:.7rem;white-space:nowrap">○加兩倍</b><b></b><b></b></div>
          <div class="diagram-title">539</div>
          <div class="diagram-caption">最新一期位置格</div>
        </div>
        <div class="diagram-content" style="grid-template-columns:minmax(0,1fr) 520px">
          <section class="number-board">
            <table><thead><tr><th>次數</th>${headers}</tr></thead><tbody>${gridRows}</tbody></table>
            <div class="blank-strips" aria-hidden="true"><i></i><i></i><i></i></div>
          </section>
          <section class="results-board adjacent-board">
            <header style="grid-template-columns:105px 1fr"><strong style="display:grid;place-items:center;border-right:2px solid var(--grid);font-family:Georgia,serif;font-size:2rem">相鄰</strong><span>相鄰統計號碼</span></header>
            <p style="margin:0;padding:8px 10px;border-bottom:1px solid #cbd7cd;color:#596b61;font-size:.68rem;line-height:1.55"><strong>計算規則：</strong>以紅圈號碼為中心，計入左、右、上、下相鄰格；各號碼依出現次數分組，未出現者列為 0 次。</p>
            <div class="adjacent-list">${adjacentRows}</div>
          </section>
        </div>
        <p>紅色圈號：此號碼於最新一期開出。右側依相鄰統計次數分組顯示號碼。</p>
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
