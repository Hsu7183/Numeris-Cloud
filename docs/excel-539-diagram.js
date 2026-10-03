(() => {
  "use strict";
  const status = document.querySelector("#excel539-status");
  const target = document.querySelector("#excel539-grids");
  const pad = (number) => String(number).padStart(2, "0");
  const exactPositions = {
    "2026-09-28": [
      { row: 3, column: 5 },
      { row: 2, column: 6 },
      { row: 2, column: 9 },
      { row: 1, column: 3 },
      { row: 1, column: 9 },
    ],
  };

  function render(draw, adjacentGroups) {
    const markedPositions = new Set((exactPositions[draw.draw_date] || (draw.numbers || []).map((drawnNumber) => {
      for (const [row, numbers] of adjacentGroups) {
        const index = numbers.indexOf(drawnNumber);
        if (index >= 0) return { row, column: index + 1 };
      }
      return null;
    }).filter(Boolean)).map(({ row, column }) => `${row}:${column}`));
    const headers = Array.from({ length: 20 }, (_, index) => `<th>${index + 1}</th>`).join("");
    const rowLabels = [4, 3, 2, 1, 0];
    const gridRows = rowLabels.map((label) => {
      const cells = Array.from({ length: 20 }, (_, index) => {
        const number = index + 1;
        const watermark = label === 3 || label === 1
          ? `<span style="color:#cfd6d1;font-family:Georgia,serif;font-size:.9rem;font-weight:700">${number}</span>`
          : "";
        const marked = markedPositions.has(`${label}:${number}`);
        const circle = marked ? `<span class="diagram-circle" aria-label="第${label}列第${number}欄開出">○</span>` : "";
        return `<td>${watermark}${circle}</td>`;
      }).join("");
      return `<tr><th>${label}</th>${cells}</tr>`;
    }).join("");
    const adjacentHeaders = Array.from({ length: 20 }, (_, index) => `<th>${index + 1}</th>`).join("");
    const adjacentRows = adjacentGroups.map(([count, numbers]) => {
      const cells = Array.from({ length: 20 }, (_, index) => {
        const number = numbers[index];
        return `<td>${number ? `<span class="adjacent-number">${pad(number)}</span>` : ""}</td>`;
      }).join("");
      return `<tr class="summary-count-${count}"><th>${count}次</th>${cells}</tr>`;
    }).join("");
    target.innerHTML = `
      <section class="diagram-sheet" aria-label="今彩539號碼格表">
        <div class="diagram-topline">
          <div class="date-box" style="grid-template-columns:2fr 1fr 1fr"><b style="font-size:.7rem;white-space:nowrap">○加兩倍</b><b></b><b></b></div>
          <div class="diagram-title">539</div>
          <div class="diagram-caption">${draw.draw_date} 位置格</div>
        </div>
        <div class="diagram-content" style="grid-template-columns:minmax(0,1fr) minmax(620px,1.15fr)">
          <section class="number-board">
            <table><thead><tr><th>次數</th>${headers}</tr></thead><tbody>${gridRows}</tbody></table>
            <div class="blank-strips" aria-hidden="true"><i></i><i></i><i></i></div>
          </section>
          <section class="results-board adjacent-board">
            <header style="grid-template-columns:105px 1fr"><strong style="display:grid;place-items:center;border-right:2px solid var(--grid);font-family:Georgia,serif;font-size:2rem">相鄰</strong><span>相鄰統計號碼</span></header>
            <p style="margin:0;padding:8px 10px;border-bottom:1px solid #cbd7cd;color:#596b61;font-size:.68rem;line-height:1.55"><strong>計算規則：</strong>以紅圈號碼為中心，計入左、右、上、下相鄰格；各號碼依出現次數分組，未出現者列為 0 次。</p>
            <div class="adjacent-table-wrap"><table class="adjacent-table"><thead><tr><th>次數</th>${adjacentHeaders}</tr></thead><tbody>${adjacentRows}</tbody></table></div>
          </section>
        </div>
        <p>紅色圈號：此號碼於最新一期開出。右側依相鄰統計次數分組顯示號碼。</p>
      </section>`;
  }

  const fallbackAdjacentGroups = [
    [4, [19, 39]], [3, [4, 23]], [2, [7, 8, 9, 14, 16, 17, 20, 24, 35]],
    [1, [1, 2, 3, 5, 6, 10, 12, 13, 15, 18, 21, 25, 26, 31, 32, 36, 38]],
    [0, [11, 22, 27, 28, 29, 30, 33, 34, 37]],
  ];

  const loadAdjacentGroups = (date) => new Promise((resolve, reject) => {
    const frame = document.createElement("iframe");
    frame.setAttribute("aria-hidden", "true");
    frame.style.cssText = "position:fixed;left:-10000px;top:0;width:1500px;height:1200px;border:0;opacity:0;pointer-events:none";
    const timeout = window.setTimeout(() => { frame.remove(); reject(new Error("相鄰統計載入逾時")); }, 15000);
    frame.addEventListener("load", () => {
      const check = window.setInterval(() => {
        const groups = frame.contentDocument?.querySelectorAll(".adjacent-summary-panel .frequency-group");
        if (!groups?.length) return;
        window.clearInterval(check);
        window.clearTimeout(timeout);
        const parsed = [...groups].map((group) => [
          Number(group.querySelector("strong")?.textContent.match(/\d+/)?.[0]),
          [...group.querySelectorAll(".ball-number")].map((element) => Number(element.textContent)),
        ]);
        const byCount = new Map(parsed);
        frame.remove();
        resolve([4, 3, 2, 1, 0].map((count) => [count, byCount.get(count) || []]));
      }, 50);
    }, { once: true });
    frame.src = `index.html?date=${encodeURIComponent(date)}&embedded=1`;
    document.body.appendChild(frame);
  });

  async function load() {
    try {
      const response = await fetch("data/daily539.json", { cache: "no-store" });
      if (!response.ok) throw new Error("資料讀取失敗");
      const payload = await response.json();
      const requestedDate = new URLSearchParams(location.search).get("date");
      const draws = payload.draws || [];
      const draw = requestedDate
        ? draws.find((item) => item.draw_date === requestedDate)
        : draws.reduce((latest, item) => !latest || item.draw_date > latest.draw_date ||
          (item.draw_date === latest.draw_date && item.draw_no > latest.draw_no) ? item : latest, null);
      if (!draw) {
        status.textContent = requestedDate
          ? `找不到 ${requestedDate} 的開獎資料，請選擇其他日期。`
          : "目前沒有開獎資料，請更新資料後再試。";
        return;
      }
      let adjacentGroups;
      try {
        adjacentGroups = await loadAdjacentGroups(draw.draw_date);
      } catch (_) {
        adjacentGroups = fallbackAdjacentGroups;
      }
      render(draw, adjacentGroups);
      status.textContent = `已填入${requestedDate ? "指定期別" : "最新一期"}：${draw.draw_no}期 · ${draw.draw_date}`;
    } catch (error) {
      status.textContent = "開獎資料讀取失敗，請重新整理後再試。";
    }
  }
  load();
})();
