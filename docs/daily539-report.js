(async () => {
  const cards = [...document.querySelectorAll('[data-daily-report]')];
  try {
    const response = await fetch('reports/daily539/latest.json', {cache:'no-store'});
    if (!response.ok) throw Error('報表資料暫時無法讀取');
    const data = await response.json();
    const today = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    const version = encodeURIComponent(data.generated_at);
    for (const card of cards) {
      card.querySelector('[data-report-status]').textContent = `${data.report_date} 總表｜開獎日期 ${data.cutoff.draw_date}（${data.cutoff.draw_no} 期）`;
      card.querySelector('[data-report-note]').textContent =
        (data.report_date < today ? '目前顯示最近成功產生的存檔；今日報表尚待更新。' : '') +
        `日期選號目標 ${data.target_date}：` + (data.provisional ? '暫算，尚待前一日開獎資料。' : '已扣除截至前一日重複開出的號碼。') +
        ` AI快報開獎日期 ${data.ai_brief_comparison?.source_draw_date || '待更新'}；加州天天樂 ${data.california_daily?.draw?.draw_date || '當日資料待更新'}。`;
      for (const a of card.querySelectorAll('[data-report-pdf],[data-report-open],[data-report-preview-link]')) a.href = `reports/daily539/latest.pdf?v=${version}`;
      card.querySelector('[data-report-pdf]').download = `今彩539_A4總表_${data.report_date}.pdf`;
      card.querySelector('[data-report-preview]').src = `reports/daily539/latest.png?v=${version}`;
    }
  } catch (error) {
    for (const card of cards) card.querySelector('[data-report-status]').textContent = '無法核對最新日期；下方可開啟最近保存的 PDF。';
  }
  const archive = document.getElementById('report-archive');
  if (archive) {
    try {
      const r = await fetch('reports/daily539/archive.json', {cache:'no-store'});
      if (!r.ok) throw Error('讀取失敗');
      const dates = await r.json();
      for (const date of dates) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) continue;
        const a = document.createElement('a');a.textContent = date+' PDF';a.href = `reports/daily539/archive/${date}.pdf`;a.download = `今彩539_A4總表_${date}.pdf`;archive.append(a);
      }
    } catch (_) {archive.textContent = '存檔清單暫時無法載入。';}
  }
})();
