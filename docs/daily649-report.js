(async () => {
  const cards = [...document.querySelectorAll('[data-lotto-report]')];
  try {
    const response = await fetch('reports/lotto649/latest.json', {cache:'no-store'});
    if (!response.ok) throw Error('報表資料暫時無法讀取');
    const data = await response.json();
    const today = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    const version = encodeURIComponent(data.generated_at);
    for (const card of cards) {
      card.querySelector('[data-report-status]').textContent = `${data.report_date} 總表｜資料截至 ${data.cutoff.draw_date}（${data.cutoff.draw_no} 期）`;
      card.querySelector('[data-report-note]').textContent =
        (data.report_date < today ? '目前顯示最近成功產生的存檔；今日報表尚待更新。' : '') +
        '49碼、每組6個主號；特別號另列，所有統計不含特別號。';
      for (const a of card.querySelectorAll('[data-report-pdf],[data-report-open],[data-report-preview-link]')) a.href = `reports/lotto649/latest.pdf?v=${version}`;
      card.querySelector('[data-report-pdf]').download = `大樂透_A4總表_${data.report_date}.pdf`;
      card.querySelector('[data-report-preview]').src = `reports/lotto649/latest.png?v=${version}`;
    }
  } catch (error) {
    for (const card of cards) card.querySelector('[data-report-status]').textContent = '無法核對最新日期；下方可開啟最近保存的 PDF。';
  }
  const archive = document.getElementById('lotto-report-archive');
  if (archive) {
    try {
      const r = await fetch('reports/lotto649/archive.json', {cache:'no-store'});
      if (!r.ok) throw Error('讀取失敗');
      const dates = await r.json();
      for (const date of dates) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) continue;
        const a = document.createElement('a');a.textContent = date+' PDF';a.href = `reports/lotto649/archive/${date}.pdf`;a.download = `大樂透_A4總表_${date}.pdf`;archive.append(a);
      }
    } catch (_) {archive.textContent = '存檔清單暫時無法載入。';}
  }
})();
