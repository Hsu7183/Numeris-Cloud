(() => {
  'use strict';
  const mounts = [...document.querySelectorAll('[data-aibrief]')];
  if (!mounts.length) return;
  let brief;
  let localDate;
  let lastRequestFailed = false;
  let updateStatus;
  let groups;
  const pad = n => String(n).padStart(2, '0');
  const balls = ns => ns.length ? ns.map(n => `<b class="brief-ball">${pad(n)}</b>`).join('') : '無';
  const fmt = value => new Date(value).toLocaleString('zh-TW', {timeZone:'Asia/Taipei',hour12:false});
  const render = () => {
    mounts.forEach(mount => {
      mount.replaceChildren();
      const heading = document.createElement('h2');
      heading.textContent = 'AI快報 · 球號比對';
      mount.append(heading);
      if (!brief) {
        const message = document.createElement('p');
        message.textContent = '快報資料暫時無法讀取。';
        mount.append(message);
        return;
      }
      const meta = document.createElement('p');
      meta.textContent = `來源開獎日期：${brief.source_draw_date} · 本機獎號：${localDate || '未載入'} · 上次抓取：${fmt(brief.checked_at)}`;
      mount.append(meta);
      const note = document.createElement('p');
      note.textContent = '文章提及的球號（包含冷熱門、歷史及趨勢號碼，不等於全部為推薦選號）';
      mount.append(note);
      const list = document.createElement('div'); list.className = 'brief-balls';
      list.innerHTML = balls(brief.mentioned_numbers);
      mount.append(list);
      if (groups) {
        const title = document.createElement('p');
        title.textContent = '與本頁相鄰統計共同出現的球號：';
        mount.append(title);
        const table = document.createElement('table'); table.className = 'brief-comparison';
        table.innerHTML = '<thead><tr><th>相鄰次數</th><th>AI快報也有提及</th></tr></thead><tbody>' +
          groups.map(([count, ns]) => `<tr><th>${count}次</th><td>${balls(ns.filter(n => brief.mentioned_numbers.includes(n)))}</td></tr>`).join('') + '</tbody>';
        mount.append(table);
      } else {
        const info = document.createElement('p');
        info.textContent = document.querySelector('#adjacent-table') ? '等待本頁相鄰統計載入後比對…' : '到疊加頁可查看與最新相鄰統計的比對結果。';
        mount.append(info);
      }
      if (localDate && localDate !== brief.source_draw_date) {
        const warning = document.createElement('p'); warning.className = 'brief-warning';
        warning.textContent = '兩邊資料日期不同，請留意截止期。'; mount.append(warning);
      }
      const footer = document.createElement('p');
      const link = document.createElement('a'); link.href = 'https://www.pilio.idv.tw/ltobig/sqlaibrief.asp';
      link.textContent = '查看來源AI快報 ↗'; link.target = '_blank'; link.rel = 'noopener';
      footer.append(link, ' · 來源資料更新後，重新整理頁面可讀取最新快報。共同出現不等於命中。');
      mount.append(footer);
      if (lastRequestFailed || updateStatus?.ok === false) {
        const warning = document.createElement('p'); warning.className = 'brief-warning';
        warning.textContent = '最新檢查未成功，以上保留上次有效資料。'; mount.append(warning);
      }
    });
  };
  const refresh = async () => {
    try {
      const [a, d, s] = await Promise.all([
        fetch('../data/649-aibrief.json', {cache:'no-store'}),
        fetch('../data/lotto649.json', {cache:'no-store'}),
        fetch('../data/649-aibrief-status.json', {cache:'no-store'}),
      ]);
      if (!a.ok) throw new Error('brief unavailable');
      const next = await a.json();
      if (!Array.isArray(next.mentioned_numbers) || !next.mentioned_numbers.every(n => Number.isInteger(n) && n >= 1 && n <= 49)) throw new Error('invalid balls');
      brief = next;
      if (d.ok) localDate = (await d.json()).latest_draw_date;
      updateStatus = s.ok ? await s.json() : null;
      lastRequestFailed = false;
    } catch (_) { lastRequestFailed = true; }
    render();
  };
  const adjacent = document.querySelector('#adjacent-table');
  if (adjacent) {
    const readGroups = () => {
      const rows = [...adjacent.querySelectorAll('tbody tr')];
      if (!rows.length) return;
      groups = rows.map(row => [Number(row.querySelector('th').textContent), [...row.querySelectorAll('td span')].map(el => Number(el.textContent))]);
      render();
    };
    new MutationObserver(readGroups).observe(adjacent, {childList:true,subtree:true});
    readGroups();
  }
  refresh();
  window.addEventListener('focus', refresh);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
