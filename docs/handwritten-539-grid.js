(() => {
  "use strict";
  const pad = (number) => String(number).padStart(2, "0");
  const status = document.querySelector("#sheet-status");
  const dateNav = document.querySelector("#draw-date-nav");
  const defaultAdjacentGroups = [
    [4, [19, 39]],
    [3, [4, 23]],
    [2, [7, 8, 9, 14, 16, 17, 20, 24, 35]],
    [1, [1, 2, 3, 5, 6, 10, 12, 13, 15, 18, 21, 25, 26, 31, 32, 36, 38]],
    [0, [11, 22, 27, 28, 29, 30, 33, 34, 37]],
  ];
  const officialDraws = {
    "2026-09-26": {
      draw_no: "115000234",
      draw_date: "2026-09-26",
      numbers: [18, 39, 34, 30, 17],
    },
  };
  const officialMappedPositions = {
    "2026-09-28": [
      { row: 3, column: 5 }, { row: 2, column: 6 }, { row: 2, column: 9 },
      { row: 1, column: 3 }, { row: 1, column: 9 },
    ],
  };
  const officialAdjacentGroups = {
    "2026-09-07": [
      [4, [7]], [3, [12, 23, 27, 33]], [2, [10, 18, 19, 21, 25, 35]],
      [1, [1, 5, 6, 8, 9, 11, 13, 22, 24, 26, 28, 29, 30, 31, 34, 36, 37]],
      [0, [2, 3, 4, 14, 15, 16, 17, 20, 32, 38, 39]],
    ],
    "2026-09-08": [
      [4, [12]], [3, [16, 28, 32]], [2, [1, 2, 4, 5, 6, 7, 11, 13, 19, 23, 25, 35]],
      [1, [8, 9, 14, 21, 22, 24, 29, 30, 31, 33, 34, 36, 39]],
      [0, [3, 10, 15, 17, 18, 20, 26, 27, 37, 38]],
    ],
    "2026-09-09": [
      [4, []], [3, [2, 6, 7, 19, 23, 25, 29, 35]], [2, [3, 5, 12, 13, 17, 30]],
      [1, [4, 8, 9, 10, 11, 16, 20, 28, 31, 32, 33, 34, 39]],
      [0, [1, 14, 15, 18, 21, 22, 24, 26, 27, 36, 37, 38]],
    ],
    "2026-09-10": [
      [4, [2]], [3, [13, 16, 21, 23, 25]], [2, [5, 6, 8, 14, 17, 29, 30, 32, 34, 38]],
      [1, [4, 7, 9, 10, 11, 12, 15, 19, 20, 24, 31, 33]],
      [0, [1, 3, 18, 22, 26, 27, 28, 35, 36, 37, 39]],
    ],
    "2026-09-11": [
      [4, [19]], [3, [5, 28, 35]], [2, [7, 8, 17, 18, 24, 29, 34]],
      [1, [1, 2, 3, 4, 10, 11, 12, 13, 14, 15, 16, 20, 21, 25, 26, 27, 30, 31, 36, 39]],
      [0, [6, 9, 22, 23, 32, 33, 37, 38]],
    ],
    "2026-09-12": [
      [4, [8]], [3, [5, 7, 29]], [2, [3, 10, 12, 16, 18, 21, 22, 28, 32, 34]],
      [1, [2, 4, 9, 11, 14, 15, 17, 19, 20, 23, 26, 30, 35, 36, 37, 38]],
      [0, [1, 6, 13, 24, 25, 27, 31, 33, 39]],
    ],
    "2026-09-14": [
      [4, []], [3, [24, 36]], [2, [3, 5, 10, 11, 17, 20, 26, 29, 31, 33]],
      [1, [1, 8, 9, 12, 13, 14, 15, 18, 23, 28, 34, 35, 37, 39]],
      [0, [2, 4, 6, 7, 16, 19, 21, 22, 25, 27, 30, 32, 38]],
    ],
    "2026-09-15": [
      [4, []], [3, [6, 19, 25, 34]], [2, [2, 5, 7, 8, 11, 23, 27, 28, 29]],
      [1, [4, 13, 14, 15, 16, 17, 18, 21, 22, 24, 30, 31, 33, 35, 37, 38, 39]],
      [0, [1, 3, 9, 10, 12, 20, 26, 32, 36]],
    ],
    "2026-09-16": [
      [4, [12, 19, 25]], [3, [6, 7]], [2, [4, 5, 8, 10, 11, 15, 17, 18, 23, 29]],
      [1, [3, 9, 13, 14, 21, 32, 35]],
      [0, [1, 2, 16, 20, 22, 24, 26, 27, 28, 30, 31, 33, 34, 36, 37, 38, 39]],
    ],
    "2026-09-17": [
      [4, [4]], [3, [3, 6]], [2, [7, 9, 12, 14, 17, 18, 19, 23, 25, 29, 35]],
      [1, [2, 5, 8, 10, 16, 21, 24, 26, 32, 33, 38]],
      [0, [1, 11, 13, 15, 20, 22, 27, 28, 30, 31, 34, 36, 37, 39]],
    ],
    "2026-09-18": [
      [4, [4, 6]], [3, [2, 18, 30]], [2, [1, 5, 7, 10, 17, 22, 25, 29, 32]],
      [1, [3, 8, 9, 11, 12, 13, 15, 16, 19, 21, 23, 28, 31, 33, 34, 35, 38]],
      [0, [14, 20, 24, 26, 27, 36, 37, 39]],
    ],
    "2026-09-19": [
      [4, [4, 6, 25]], [3, [19, 24, 28, 32]], [2, [22, 23, 29, 35, 36]],
      [1, [2, 7, 8, 12, 13, 14, 15, 17, 18, 21, 26, 27, 30, 31, 33, 34, 38]],
      [0, [1, 3, 5, 9, 10, 11, 16, 20, 37, 39]],
    ],
    "2026-09-21": [
      [4, [2, 24]],
      [3, [8, 16]],
      [2, [6, 18, 19, 25, 26, 29, 32, 35, 39]],
      [1, [1, 3, 9, 10, 11, 12, 14, 15, 17, 20, 21, 22, 23, 27, 28, 33, 34, 36, 37]],
      [0, [4, 5, 7, 13, 30, 31, 38]],
    ],
    "2026-09-22": [
      [4, [15]],
      [3, [18]],
      [2, [4, 5, 7, 11, 12, 16, 21, 26, 27, 28, 30, 34]],
      [1, [2, 8, 13, 14, 19, 20, 22, 23, 25, 29, 31, 32, 35, 37, 38]],
      [0, [1, 3, 6, 9, 10, 17, 24, 33, 36, 39]],
    ],
    "2026-09-23": [
      [4, [14]],
      [3, [1, 3, 7, 10, 16]],
      [2, [2, 6, 9, 11, 12, 18, 29]],
      [1, [5, 8, 15, 19, 20, 21, 22, 23, 24, 26, 27, 28, 30, 32, 34, 35, 38]],
      [0, [4, 13, 17, 25, 31, 33, 36, 37, 39]],
    ],
    "2026-09-24": [
      [4, [3, 23]],
      [3, [8, 12, 19, 30]],
      [2, [1, 4, 5, 7, 13, 17, 26, 35]],
      [1, [2, 6, 10, 11, 16, 18, 20, 22, 25, 28, 34]],
      [0, [9, 14, 15, 21, 24, 27, 29, 31, 32, 33, 36, 37, 38, 39]],
    ],
    "2026-09-26": [
      [4, []],
      [3, [8, 25, 26, 33]],
      [2, [6, 11, 13, 15, 19, 28, 31]],
      [1, [2, 3, 4, 7, 9, 12, 14, 23, 24, 29, 30, 34, 35, 36]],
      [0, [1, 5, 10, 16, 17, 18, 20, 21, 22, 27, 32, 37, 38, 39]],
    ],
  };
  const renderNumberGrid = (draw, adjacentGroups) => {
    const calculatedPositions = (draw.numbers || []).map((drawnNumber) => {
      for (const [count, numbers] of adjacentGroups) {
        const index = numbers.indexOf(drawnNumber);
        if (index >= 0) return { row: count, column: index + 1 };
      }
      return null;
    }).filter(Boolean);
    const mappedCells = new Set((officialMappedPositions[draw.draw_date] || calculatedPositions)
      .map(({ row, column }) => `${row}:${column}`));
    const headers = Array.from({ length: 20 }, (_, index) => `<th>${index + 1}</th>`).join("");
    const rows = Array.from({ length: 5 }, (_, row) => {
      const rowLabel = 4 - row;
      const cells = Array.from({ length: 20 }, (_, index) => {
        const number = index + 1;
        const watermark = row === 1 || row === 3 ? `<span class="watermark" style="color:#cfd6d1;font-family:Georgia,serif;font-size:.9rem;font-weight:700">${number}</span>` : "";
        const circle = mappedCells.has(`${rowLabel}:${number}`) ? `<span class="circle" style="position:absolute;inset:0;display:grid;place-items:center;font-size:2.45rem">○</span>` : "";
        return `<td>${watermark}${circle}</td>`;
      }).join("");
      return `<tr><th>${rowLabel}</th>${cells}</tr>`;
    }).join("");
    document.querySelector("#number-grid").innerHTML = `<thead><tr><th>次數</th>${headers}</tr></thead><tbody>${rows}</tbody>`;
    document.querySelector("#winning-numbers").innerHTML = `本期中獎號碼：${(draw.numbers || []).map((number) => `<b style="display:inline-grid;place-items:center;width:24px;height:24px;margin-left:3px;border-radius:50%;background:#d84b47;color:#fff;font-family:Georgia,serif;font-size:.68rem">${pad(number)}</b>`).join("")}`;
  };
  const renderAdjacentGrid = (adjacentGroups) => {
    const groups = adjacentGroups;
    const colors = {
      4: "background:#ff878d;border-color:#9d2030;color:#53000a",
      3: "background:#ffbc36;border-color:#bd6800;color:#4a2900",
      2: "background:#73e5df;border-color:#007c81;color:#003e41",
      1: "background:#bdf26a;border-color:#398b5b;color:#083c24",
      0: "background:#e4e9e5;border-color:#aab6ae;color:#526158",
    };
    const headers = Array.from({ length: 20 }, (_, index) => `<th>${index + 1}</th>`).join("");
    const rows = groups.map(([count, numbers]) => {
      const cells = Array.from({ length: 20 }, (_, index) => {
        const number = numbers[index];
        return `<td>${number ? `<span style="display:inline-grid;place-items:center;width:20px;height:20px;border:1px solid;border-radius:50%;font-family:Georgia,serif;font-size:.58rem;font-weight:900;${colors[count]}">${pad(number)}</span>` : ""}</td>`;
      }).join("");
      return `<tr><th>${count}</th>${cells}</tr>`;
    }).join("");
    document.querySelector("#draw-grid").innerHTML = `<thead><tr><th style="width:42px">次數</th>${headers}</tr></thead><tbody>${rows}</tbody>`;
  };
  const renderDateNav = (draws, selectedDate) => {
    const recentDraws = draws.slice(0, 18).reverse();
    const links = recentDraws.map((item) => {
      const [, month, day] = item.draw_date.split("-");
      const selected = item.draw_date === selectedDate ? "color:#d84b47;font-weight:900" : "";
      return `<a href="handwritten-539-grid.html?date=${item.draw_date}" style="${selected}">${Number(month)}/${Number(day)}</a>`;
    }).join("");
    dateNav.innerHTML = `<a href="handwritten-539-overlay.html" style="font-weight:900">6／12／18天疊加</a>${links}`;
  };
  const loadDynamicAdjacentGroups = (date) => new Promise((resolve, reject) => {
    const frame = document.createElement("iframe");
    frame.setAttribute("aria-hidden", "true");
    frame.style.cssText = "position:fixed;left:-10000px;top:0;width:1500px;height:1200px;border:0;opacity:0;pointer-events:none";
    const timeout = window.setTimeout(() => {
      frame.remove();
      reject(new Error("相鄰統計載入逾時"));
    }, 15000);
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
        const result = [4, 3, 2, 1, 0].map((count) => [count, byCount.get(count) || []]);
        frame.remove();
        resolve(result);
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
      const draw = requestedDate
        ? (payload.draws || []).find((item) => item.draw_date === requestedDate) || officialDraws[requestedDate]
        : payload.draws?.[0];
      if (!draw) throw new Error("沒有開獎資料");
      renderDateNav(payload.draws || [], draw.draw_date);
      status.textContent = `正在計算${requestedDate ? "指定期別" : "最新一期"}相鄰統計：${draw.draw_no}期 · ${draw.draw_date}`;
      let adjacentGroups = officialAdjacentGroups[draw.draw_date];
      if (!adjacentGroups && draw.draw_date === "2026-09-25") adjacentGroups = defaultAdjacentGroups;
      if (!adjacentGroups) {
        try {
          adjacentGroups = await loadDynamicAdjacentGroups(draw.draw_date);
        } catch (_) {
          adjacentGroups = defaultAdjacentGroups;
        }
      }
      renderNumberGrid(draw, adjacentGroups);
      renderAdjacentGrid(adjacentGroups);
      status.textContent = `${requestedDate ? "指定期別" : "已填入最新一期"}：${draw.draw_no}期 · ${draw.draw_date}`;
    } catch (error) {
      status.textContent = "開獎資料讀取失敗，請重新整理後再試。";
    }
  }
  load();
})();
