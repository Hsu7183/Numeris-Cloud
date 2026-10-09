(() => {
  "use strict";
  const rangeDays = [18, 12, 6];
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
    }, 30000);
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
    }, 30000);
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

  const countCells = (periods, datedCells) => {
    const counts = new Map();
    datedCells.slice(-periods).flatMap(({ cells }) => cells)
      .forEach((key) => counts.set(key, (counts.get(key) || 0) + 1));
    return counts;
  };

  const renderBlankDifferences = (datedCells) => {
    const counts = new Map(rangeDays.map((periods) => [periods, countCells(periods, datedCells)]));
    const headers = Array.from({ length: 20 }, (_, index) => `<th>${index + 1}</th>`).join("");
    return [[12, 18], [6, 12], [6, 18]].map(([short, long]) => {
      let changed = 0;
      let blank = 0;
      const rows = [4, 3, 2, 1, 0].map((rowLabel) => {
        const cells = Array.from({ length: 20 }, (_, index) => {
          const column = index + 1;
          const key = `${rowLabel}:${column}`;
          const shortCount = counts.get(short).get(key) || 0;
          const longCount = counts.get(long).get(key) || 0;
          const difference = shortCount === 0 && longCount > 0;
          const bothBlank = longCount === 0;
          if (difference) changed += 1;
          if (bothBlank) blank += 1;
          const label = difference || bothBlank ? "" : "—";
          const watermark = `<span class="blank-watermark" aria-hidden="true">${column}</span>`;
          const description = `次數列 ${rowLabel}、第 ${column} 欄：近 ${short} 期 ${shortCount} 次，近 ${long} 期 ${longCount} 次`;
          return `<td class="${difference ? "blank-changed" : bothBlank ? "blank-shared" : "blank-unchanged"}" title="${description}" aria-label="${description}">${watermark}<span class="blank-label">${label}</span></td>`;
        }).join("");
        return `<tr><th>${rowLabel}</th>${cells}</tr>`;
      }).join("");
      return `<section class="overlay-panel"><header><strong>近 ${long} → ${short} 期</strong></header><table><thead><tr><th class="blank-summary" colspan="21">空白格增加 ${changed} 格</th></tr><tr><th>次數</th>${headers}</tr></thead><tbody>${rows}</tbody></table><p class="overlay-note">有→空：${changed} 格；兩者皆空：${blank} 格；兩者皆有：${100 - changed - blank} 格。</p></section>`;
    }).join("");
  };

  const renderPanel = (periods, datedCells) => {
    const selected = datedCells.slice(-periods);
    const label = `${selected[0].date.replaceAll("-", "/")}～${selected.at(-1).date.replaceAll("-", "/")}`;
    const counts = countCells(periods, datedCells);
    const headers = Array.from({ length: 20 }, (_, index) => `<th>${index + 1}</th>`).join("");
    const rows = [4, 3, 2, 1, 0].map((rowLabel) => {
      const cells = Array.from({ length: 20 }, (_, index) => {
        const column = index + 1;
        const count = counts.get(`${rowLabel}:${column}`) || 0;
        const watermark = `<span class="overlay-watermark" aria-hidden="true" style="color:#cfd6d1;font-family:Georgia,serif;font-size:.8rem;font-weight:700">${column}</span>`;
        const circle = count
          ? `<span class="overlay-circle" style="position:absolute;inset:4px;margin:auto">${count}</span>`
          : "";
        return `<td style="position:relative">${watermark}${circle}</td>`;
      }).join("");
      return `<tr><th>${rowLabel}</th>${cells}</tr>`;
    }).join("");
    return `<section class="overlay-panel"><header><strong>近 ${periods} 期疊加</strong><span>${label}</span></header><table><thead><tr><th>次數</th>${headers}</tr></thead><tbody>${rows}</tbody></table><p class="overlay-note">最近 ${periods} 個實際開獎期；休假日不計，紅圈內數字為累計出現次數。</p></section>`;
  };

  const placeAdjacentBalls = () => {
    const sourceRows = [...document.querySelectorAll("#adjacent-table tbody tr")];
    document.querySelectorAll("#blank-difference-panels tbody").forEach((body) => {
      sourceRows.forEach((sourceRow) => {
        const rowLabel = sourceRow.querySelector("th").textContent;
        const targetRow = [...body.querySelectorAll("tr")]
          .find((row) => row.querySelector("th").textContent === rowLabel);
        if (!targetRow) return;
        const targetCells = targetRow.querySelectorAll("td");
        sourceRow.querySelectorAll("td").forEach((cell, index) => {
          const ball = cell.querySelector("span");
          if (!ball || !targetCells[index]) return;
          const copy = ball.cloneNode(true);
          copy.classList.add("comparison-ball");
          targetCells[index].querySelector(".blank-label")?.remove();
          targetCells[index].appendChild(copy);
          const description = `${targetCells[index].getAttribute("aria-label")}；本期球號 ${ball.textContent}`;
          targetCells[index].setAttribute("aria-label", description);
          targetCells[index].title = description;
        });
      });
    });
  };

  const loadCheckHistory = async (payload) => {
    const container = document.querySelector("#check-history");
    try {
      const response = await fetch("data/daily539-checks.json", { cache: "no-store" });
      if (!response.ok) throw new Error("核對紀錄讀取失敗");
      const history = await response.json();
      const format = (numbers) => numbers.map((number) => String(number).padStart(2, "0")).join("、");
      const rows = history.records.slice().sort((a, b) => b.target_date.localeCompare(a.target_date)).map((record) => {
        const draw = payload.draws.find((item) => item.draw_date === record.target_date);
        const hits = draw ? record.selected_numbers.filter((number) => draw.numbers.includes(number)) : [];
        return `<tr><td>${record.selection_date}<br><small>資料截止 ${record.cutoff_date}</small></td><td>${record.target_date}<br>${draw ? draw.draw_no : "待開獎"}</td><td>${format(record.selected_numbers)}</td><td>${draw ? format(draw.numbers) : "待核對"}</td><td>${draw ? format(hits) || "無" : "—"}</td><td>${draw ? `命中 ${hits.length} 個` : "待核對"}</td></tr>`;
      }).join("");
      container.innerHTML = rows ? `<table style="min-width:1000px;table-layout:auto"><thead><tr><th>選號日期</th><th>核對日期／期別</th><th>選定號碼</th><th>開獎號碼</th><th>命中號碼</th><th>結果</th></tr></thead><tbody>${rows}</tbody></table>` : "尚無核對紀錄。";
    } catch (error) {
      container.textContent = error.message;
    }
  };

  async function load() {
    try {
      const response = await fetch(`data/daily539.json?load=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error("開獎資料讀取失敗");
      const payload = await response.json();
      await loadCheckHistory(payload);
      const dates = (payload.draws || []).slice(0, 18).map((draw) => draw.draw_date).reverse();
      if (dates.length < 18) throw new Error("不足 18 期開獎資料");
      status.textContent = `正在載入最近 18 期資料（截至 ${dates.at(-1)}）…`;
      const dailyCells = await Promise.all(dates.map(loadMappedCells));
      const datedCells = dates.map((date, index) => ({ date, cells: dailyCells[index] }));
      document.querySelector("#overlay-panels").innerHTML = rangeDays.map((periods) => renderPanel(periods, datedCells)).join("");
      document.querySelector("#blank-difference-panels").innerHTML = renderBlankDifferences(datedCells);
      const adjacentDate = dates.at(-1);
      document.querySelector("#adjacent-table").innerHTML = await loadAdjacentTable(adjacentDate);
      placeAdjacentBalls();
      document.querySelector("#adjacent-date").textContent = `${adjacentDate.replaceAll("-", "/")} 本期相鄰`;
      document.querySelector(".overlay-header span").textContent = `依最近 6／12／18 個實際開獎期累加；休假日不計（截至 ${adjacentDate}）`;
      status.textContent = `已更新至 ${adjacentDate} · 近 6／12／18 期疊加 · 每日自動更新已開啟。`;
      enableAutomaticUpdates();
    } catch (error) {
      status.textContent = `疊加資料載入失敗：${error.message}`;
    }
  }
  load();
})();
