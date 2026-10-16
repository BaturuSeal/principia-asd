/* Render-contract regressions. No browser, network, provider or workspace writes. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../src/principia_asd/web/app.js'), 'utf8');
const elements = new Map();
const element = selector => {
  if (!elements.has(selector)) elements.set(selector, {
    innerHTML: '', textContent: '', classList: {add(){}, remove(){}},
    querySelector: element, addEventListener(){}, close(){},
  });
  return elements.get(selector);
};
const context = vm.createContext({
  document: {documentElement: {dataset: {}}, querySelector: element, querySelectorAll: () => []},
  window: {addEventListener(){}, scrollTo(){}}, location: {hash: '#run/test'},
  clearInterval(){}, setInterval(){throw Error('Terminal runs must stop polling');},
  fetch(){throw Error('No network allowed in render tests');}, console,
});
assert.equal(source.split(';init();').length, 2);
vm.runInContext(source.replace(';init();', ';'), context);
const record = {
  run_id: 'test', scenario_id: 'S', method_id: 'equation_search', status: 'complete',
  events: [], accounting: {structures: 2, fitting_attempts: 4, model_calls: 0},
  method_evidence: {
    version: 'equation-search-v1', selection: 'Development selection', scope: 'Unreviewed hypothesis',
    candidates: [{equation_system: {name: 'Thermal <response>', nodes: [{}, {}]}, dev_error: .2, parameters: {a: 1}, origin: 'Sourced template'}],
    failures: [{reason: 'Unit mismatch'}],
  },
  rules: [{rule_id: 'r1', dev_error: .2}],
  evaluation: {receipts: [{rule_id: 'r1', status: 'invalid'}]},
};
context.record = record;
vm.runInContext(`api=async p=>p==='/api/config'?{methods:[{method_id:'equation_search',name:'Scientific equation search'}]}:record;`, context);
(async()=>{
  await vm.runInContext("monitor('test')", context);
  const html=element('#view').innerHTML;
  assert.match(html, /Frozen rule portfolio/);
  assert.match(html, /Equation search/);
  assert.match(html, /Thermal &lt;response&gt;/);
  assert.match(html, /Unit mismatch/);
  assert.match(html, /invalid/);
  assert.equal(element('#error').textContent, '');
  const unknown = vm.runInContext("methodEvidence({version:'future-method',facts:[]},[])", context);
  assert.match(unknown, /Recorded method evidence/);
  context.board = {track:'primary',rules:['a','b','c'].map(rule_id=>({rule_id,method_id:'equation_search',status:'complete'})),rule_presentations:{a:{family_name:'Affine response',structure_id:'one'},b:{family_name:'Affine response',structure_id:'one'},c:{family_name:'Affine response',structure_id:'two'}}};
  const table = vm.runInContext("tableForTask({review_advisories:[]},{metric:{primary:'mae'}},board)",context);
  assert.match(table,/Affine response · Form 1 · Fit 2/);
  assert.match(table,/Affine response · Form 2/);
  assert.match(table,/Frozen primary comparison/);
  assert.doesNotMatch(table,/separate from the frozen primary comparison/);
  console.log('PASS: equation evidence, failed assessment, escaping, unknown-method fallback, distinct form labels and primary-track scope');
})().catch(e=>{console.error(e);process.exitCode=1;});
