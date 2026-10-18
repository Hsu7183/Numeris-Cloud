const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const root = path.resolve(__dirname, '..');
const code = fs.readFileSync(path.join(root, 'docs/daily539_output.js'), 'utf8');
const payload = JSON.parse(fs.readFileSync(path.join(root, 'docs/data/daily539.json'), 'utf8'));
async function check(pathname, fail, cached) {
  const nodes = {'#matrix-wrap': {}, '#output-meta': {}};
  let requested;
  const context = {
    document: {querySelector: selector => nodes[selector]},
    location: {pathname},
    localStorage: {getItem: () => cached},
    fetch: async url => {requested = url; if (fail) throw Error('offline'); return {ok:true, json:async()=>payload};},
  };
  await vm.runInNewContext(code, context);
  return {nodes, requested};
}
(async () => {
  for (const pathname of ['/output.html', '/539/output']) {
    const result = await check(pathname, false, null);
    assert.equal(result.requested, pathname === '/539/output' ? '/539/pages/data/daily539.json' : 'data/daily539.json');
    assert.ok(result.nodes['#output-meta'].textContent.includes(payload.latest_draw_no));
    assert.equal((result.nodes['#matrix-wrap'].innerHTML.match(/class="score-line-item"/g)||[]).length,39);
    assert.equal((result.nodes['#matrix-wrap'].innerHTML.match(/class="score-item"/g)||[]).length,39);
  }
  assert.ok((await check('/output.html',true,JSON.stringify(payload))).nodes['#output-meta'].textContent);
  assert.ok((await check('/output.html',true,'invalid')).nodes['#matrix-wrap'].innerHTML.includes('class="empty"'));
  console.log('PASS: fresh static/app loads, both ranking tables, offline fallback and malformed cache.');
})().catch(error => {console.error(error);process.exitCode=1;});
