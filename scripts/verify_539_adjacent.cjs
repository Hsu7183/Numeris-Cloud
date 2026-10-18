const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const report = JSON.parse(fs.readFileSync(path.join(root, 'docs/539-adjacent-backtest.json'), 'utf8'));
const source = fs.readFileSync(path.join(root, 'docs/daily539_output.js'), 'utf8');
// Execute the actual page ranking code, with a payload parameter instead of browser storage.
const start = source.indexOf('  const latestNumbers');
const end = source.indexOf('  const scoreStrip');
const calculate = new Function('payload', source.slice(start, end) + '\nreturn scores;');
// Full source data is exported by the replay script for exact parity verification.
const history = JSON.parse(fs.readFileSync(path.join(root, 'reports/539-adjacent-source.json'), 'utf8'));
report.details.forEach((trial, i) => {
  const computed = calculate({draws: history.slice(i, i + 200).reverse()});
  const normalized = computed.map(x => ({number:x.number, score:Math.round(x.score * 10) / 10}));
  if (JSON.stringify(normalized) !== JSON.stringify(trial.ranking)) {
    throw new Error('Ranking mismatch: ' + trial.target_draw_no);
  }
});
console.log(`PASS: all ${report.details.length} historical rankings match output.html JavaScript.`);
