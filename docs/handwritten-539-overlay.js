(() => {
  "use strict";
  const dates = [
    "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11", "2026-09-12",
    "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-19",
    "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-26",
  ];
  const ranges = [
    { days: 6, label: "2026/09/07～2026/09/12" },
    { days: 12, label: "2026/09/07～2026/09/19" },
    { days: 18, label: "2026/09/07～2026/09/26" },
  ];
  const status = document.querySelector("#overlay-status");
  const source = document.querySelector("#overlay-source");
  document.querySelector("#today-date").textContent = `畫面日期：${new Intl.DateTimeFormat("zh-TW", { timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit", weekday: "long" }).format(new Date())}`;
  let loadedDataVersion = "";

  const readDataVersion = async () => {
    const response = await fetch(`data/daily539.json?check=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error("無法檢查最新資料");
    const payload = await response.json();
    return `${payload.latest_draw_date || ""}|${payload.generated_at || ""}`;
  };

  const enableAutomaticUpdates = async () => {
    try {
      loadedDataVersion = await readDataVersion();
    } catch (_) {
      // 初次檢查失敗不影響目前已載入的格表。
    }
    const checkForUpdate = async () => {
      try {
        const latestVersion = await readDataVersion();
        if (loadedDataVersion && latestVersion !== loadedDataVersion) {
          location.reload();
          return;
        }
        loadedDataVersion = latestVersion;
      } catch (_) {
        // 保留目前畫面，下一輪再檢查。
      }
    };
    window.setInterval(checkForUpdate, 5 * 60 * 1000);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) checkForUpdate();
    });
    window.addEventListener("focus", checkForUpdate);
  };

  const loadMappedCells = (date) => new Promise((resolve, reject) => {
    const frame = document.createElement("iframe");
    const timeout = window.setTimeout(() => {
      frame.remove();
      reject(new Error(`${date} 載入逾時`));
    }, 10000);
    frame.addEventListener("load", () => {
      const check = window.setInterval(() => {
        const documentRef = frame.contentDocument;
        const ready = documentRef?.querySelector("#sheet-status")?.textContent.startsWith("指定期別");
        if (!ready) return;
        window.clearInterval(check);
        window.clearTimeout(timeout);
        const cells = [...documentRef.querySelectorAll("#number-grid tbody tr")].flatMap((row) => {
          const rowLabel = row.querySelector("th")?.textContent;
          return [...row.querySelectorAll("td")]
            .map((cell, index) => cell.querySelector(".circle") ? `${rowLabel}:${index + 1}` : null)
            .filter(Boolean);
        });
        frame.remove();
        resolve(cells);
      }, 30);
    }, { once: true });
    frame.src = `handwritten-539-grid.html?date=${date}`;
    source.appendChild(frame);
  });

  const loadAdjacentTable = (date) => new Promise((resolve, reject) => {
    const frame = document.createElement("iframe");
    const timeout = window.setTimeout(() => {
      frame.remove();
      reject(new Error(`${date} 相鄰表格載入逾時`));
    }, 10000);
    frame.addEventListener("load", () => {
      const check = window.setInterval(() => {
        const documentRef = frame.contentDocument;
        const ready = documentRef?.querySelector("#sheet-status")?.textContent.startsWith("指定期別");
        const table = documentRef?.querySelector("#draw-grid");
        if (!ready || !table?.innerHTML) return;
        window.clearInterval(check);
        window.clearTimeout(timeout);
        const html = table.outerHTML;
        frame.remove();
        resolve(html);
      }, 30);
    }, { once: true });
    frame.src = `handwritten-539-grid.html?date=${date}`;
    source.appendChild(frame);
  });

  const renderPanel = ({ days, label }, dailyCells) => {
    const counts = new Map();
    dailyCells.slice(0, days).flat().forEach((key) => counts.set(key, (counts.get(key) || 0) + 1));
    const headers = Array.from({ length: 20 }, (_, index) => `<th>${index + 1}</th>`).join("");
    const rows = [4, 3, 2, 1, 0].map((rowLabel) => {
      const cells = Array.from({ length: 20 }, (_, index) => {
        const column = index + 1;
        const count = counts.get(`${rowLabel}:${column}`) || 0;
        const watermark = rowLabel === 3 || rowLabel === 1
          ? `<span style="color:#cfd6d1;font-family:Georgia,serif;font-size:.8rem;font-weight:700">${column}</span>`
          : "";
        const circle = count
          ? `<span class="overlay-circle" style="position:absolute;inset:4px;margin:auto">${count}</span>`
          : "";
        return `<td style="position:relative">${watermark}${circle}</td>`;
      }).join("");
      return `<tr><th>${rowLabel}</th>${cells}</tr>`;
    }).join("");
    return `<section class="overlay-panel"><header><strong>${days} 天疊加</strong><span>${label}</span></header><table><thead><tr><th>次數</th>${headers}</tr></thead><tbody>${rows}</tbody></table><p class="overlay-note">共 ${days} 個開獎日；紅圈內數字為該框格累計出現次數。</p></section>`;
  };

  Promise.all(dates.map(loadMappedCells)).then(async (dailyCells) => {
    document.querySelector("#overlay-panels").innerHTML = ranges.map((range) => renderPanel(range, dailyCells)).join("");
    const adjacentDate = dates.at(-1);
    document.querySelector("#adjacent-table").innerHTML = await loadAdjacentTable(adjacentDate);
    document.querySelector("#adjacent-date").textContent = `${adjacentDate.replaceAll("-", "/")} 本期相鄰`;
    status.textContent = "已完成 6、12、18 個開獎日疊加 · 每日自動更新已開啟。";
    enableAutomaticUpdates();
  }).catch((error) => {
    status.textContent = `疊加資料載入失敗：${error.message}`;
  });
})();
