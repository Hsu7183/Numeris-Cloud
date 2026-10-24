(() => {
  "use strict";
  const pad = (number) => String(number).padStart(2, "0");
  const status = document.querySelector("#sheet-status");
  const dateNav = document.querySelector("#draw-date-nav");
  const officialDraws = {};
  const officialMappedPositions = {};
  const officialAdjacentGroups = {};
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
    const headers = Array.from({ length: 49 }, (_, index) => `<th>${index + 1}</th>`).join("");
    const rows = Array.from({ length: 5 }, (_, row) => {
      const rowLabel = 4 - row;
      const cells = Array.from({ length: 49 }, (_, index) => {
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
    const headers = Array.from({ length: 49 }, (_, index) => `<th>${index + 1}</th>`).join("");
    const rows = groups.map(([count, numbers]) => {
      const cells = Array.from({ length: 49 }, (_, index) => {
        const number = numbers[index];
        return `<td>${number ? `<span style="display:inline-grid;place-items:center;width:20px;height:20px;border:1px solid;border-radius:50%;font-family:Georgia,serif;font-size:.58rem;font-weight:900;${colors[count]}">${pad(number)}</span>` : ""}</td>`;
      }).join("");
      return `<tr><th>${count}</th>${cells}</tr>`;
    }).join("");
    document.querySelector("#draw-grid").innerHTML = `<thead><tr><th style="width:42px">次數</th>${headers}</tr></thead><tbody>${rows}</tbody>`;
  };
  const renderDateNav = (draws, selectedDate) => {
    const recentDraws = draws.slice(0, 48).reverse();
    const links = recentDraws.map((item) => {
      const [, month, day] = item.draw_date.split("-");
      const selected = item.draw_date === selectedDate ? "color:#d84b47;font-weight:900" : "";
      return `<a href="handwritten-649-grid.html?date=${item.draw_date}" style="${selected}">${Number(month)}/${Number(day)}</a>`;
    }).join("");
    dateNav.innerHTML = `<strong style="align-self:center">最近 48 期：</strong><a href="handwritten-649-overlay.html" style="font-weight:900">6／12／18／24／30／36／42／48期疊加</a>${links}`;
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
      const response = await fetch("../data/lotto649.json", { cache: "no-store" });
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
      if (!adjacentGroups) {
        try {
          adjacentGroups = await loadDynamicAdjacentGroups(draw.draw_date);
        } catch (_) {
          throw new Error('相鄰統計計算失敗，請重新整理');
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
