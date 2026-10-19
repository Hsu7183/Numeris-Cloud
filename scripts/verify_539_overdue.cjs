const assert = require('node:assert/strict');
const fs = require('node:fs');
require('../docs/539-overdue.js');
const { analyze } = globalThis.daily539Overdue;
const draws = Array.from({ length: 48 }, () => ({ numbers: [1, 2, 3, 4, 5] }));
const result = analyze(draws);
assert.deepEqual(result.windows.map(x => x.period), [6, 12, 18, 24, 30, 36, 42, 48]);
for (const window of result.windows) {
  assert.deepEqual(window.top.map(x => x.number), [6, 7, 8, 9, 10]);
  assert(window.top.every(x => x.atLeast && x.omission === window.period));
}
assert.equal(result.factors.find(x => x.number === 6).count, 8);
assert.equal(result.factors.find(x => x.number === 1).count, 0);
assert.throws(() => analyze(draws.slice(0, 47)), /不足 48/);
// Every number appears in the last eight draws: verify actual last occurrence.
const cycling = Array.from({ length: 48 }, (_, i) => ({ numbers: Array.from({ length: 5 }, (_, j) => ((i * 5 + j) % 39) + 1) }));
const full = analyze(cycling).windows.at(-1);
assert.deepEqual(full.top.map(x => x.number), [36, 37, 38, 39, 31]);
assert.deepEqual(full.top.map(x => x.omission), [7, 7, 7, 7, 6]);
assert(full.top.every(x => !x.atLeast));
const payload = JSON.parse(fs.readFileSync('docs/data/daily539.json', 'utf8'));
const live = analyze(payload.draws);
assert.equal(live.factors.length, 39);
assert.equal(live.factors.reduce((sum, x) => sum + x.count, 0), 40);
console.log('Verified eight windows, ties, omission boundaries, factor counts and local draw data.');
