/* Interaction contracts for public/local navigation. No browser or external requests. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname,'../src/principia_asd/web');
function harness(publicSite=false) {
  const nodes=new Map();
  const node=selector=>{
    if(!nodes.has(selector)) {
      const attrs=new Map(), classes=new Set();
      nodes.set(selector,{innerHTML:'',textContent:'',value:'',checked:false,open:false,dataset:{},
        classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c),toggle(c,on){if(on)classes.add(c);else classes.delete(c);}},
        setAttribute:(k,v)=>attrs.set(k,v),getAttribute:k=>attrs.get(k)||null,removeAttribute:k=>attrs.delete(k),
        querySelector:s=>node(selector+' '+s),querySelectorAll:()=>[],showModal(){this.open=true;},close(){this.open=false;},focus(){},addEventListener(){},replaceChildren(){this.innerHTML='';}});
    }
    return nodes.get(selector);
  };
  const context=vm.createContext({URL,Map,console,document:{documentElement:{dataset:publicSite?{deployment:'public',basePath:'/web/asd-test/'}:{}},querySelector:node,querySelectorAll:()=>[]},window:{addEventListener(){},scrollTo(){}},location:{hash:'#explorer'},clearInterval(){},navigator:{clipboard:{writeText:async()=>{}}},fetch(){throw Error('Unexpected network request');}});
  vm.runInContext(fs.readFileSync(path.join(root,'explorer.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(root,'app.js'),'utf8').replace(';init();',';'),context);
  const task={task_id:'task-a',display_title:'Pressure response',inputs:['x'],output:'y',variables:[{key:'x',label:'Pressure',role:'input',units:'Pa'},{key:'y',label:'Flux',role:'output',units:'kg/s'}],metric:{primary:'mae'},test_exposure:'retrospective'};
  context.fixture={config:{methods:[],companion_download:{url:'/downloads/principia-asd.zip',bytes:26000000}},scenarios:[{scenario_id:'P100-001',title:'Gas transport',domain:'Physics',description:'Public <example>',task,tasks:[task],rows:{train:20}},{scenario_id:'LOCAL-1',title:'Private observations',domain:'Physics',description:'Local data',task:{...task,test_exposure:'local-user-split'},tasks:[{...task,task_id:'local-a'}],rows:{train:20}}],boards:[{scenario_id:'P100-001',rule_count:4}],selected:'P100-001',task:'task-a'};
  vm.runInContext('Object.assign(state,fixture)',context);
  return {node,run:source=>vm.runInContext(source,context)};
}
const local=harness();
local.run('explorer()');
assert.match(local.node('#view').innerHTML,/Discover a rule/);
assert.match(local.node('#scenario-cards').innerHTML,/Gas transport/);
assert.doesNotMatch(local.node('#scenario-cards').innerHTML,/Private observations/);
assert.match(local.node('#scenario-cards').innerHTML,/Public &lt;example&gt;/);
assert.match(local.node('#scenario-cards').innerHTML,/4 explored rules/);
local.node('#search-scenarios').value='Gas transport';local.node('#search-scenarios').oninput();
local.node('#local-scenarios-tab').onclick();
assert.equal(local.node('#search-scenarios').value,'');
assert.match(local.node('#scenario-cards').innerHTML,/Private observations/);
assert.doesNotMatch(local.node('#scenario-cards').innerHTML,/Gas transport/);
assert.equal(local.node('#local-scenarios-tab').getAttribute('aria-selected'),'true');
local.node('#public-scenarios-tab').onclick();
local.node('#search-scenarios').value='No matching topic';local.node('#search-scenarios').oninput();
assert.match(local.node('#scenario-cards').innerHTML,/No matching scenarios/);
local.node('#clear-filters').onclick();
assert.match(local.node('#scenario-cards').innerHTML,/Gas transport/);
const hosted=harness(true);
hosted.run('companionDialog("P100-001","task-a")');
assert.match(hosted.node('#setup-content').innerHTML,/\/web\/asd-test\/downloads\/principia-asd.zip/);
assert.match(hosted.node('#setup-content').innerHTML,/--open-browser/);
assert.doesNotMatch(hosted.node('#setup-content').innerHTML,/target="_blank"/);
assert.match(hosted.node('#setup-content').innerHTML,/referrerpolicy="no-referrer"/);
assert.equal(hosted.node('#workspace-link').getAttribute('href'),null);
hosted.node('#workspace-address').value='http://127.0.0.1:8154/';
hosted.node('#workspace-running').checked=true;hosted.node('#workspace-running').onchange();
assert.equal(hosted.node('#workspace-link').href,'http://127.0.0.1:8154/#explorer/P100-001/task-a');
assert.equal(hosted.node('#workspace-link').getAttribute('aria-disabled'),'false');
for(const address of ['https://example.com/','http://127.0.0.1.evil.test/','javascript:alert(1)','file:///tmp/a','http://user:pass@localhost:8150/','http://localhost:8150/?key=secret','http://localhost:8150/private','http://localhost:8150/#secret','https://localhost:8150/']){
  assert.throws(()=>hosted.run(`companionWorkspaceUrl(${JSON.stringify(address)},'P100-001','task-a')`));
  hosted.node('#workspace-address').value=address;hosted.node('#workspace-address').oninput();
  assert.equal(hosted.node('#workspace-link').getAttribute('href'),null);
  assert.equal(hosted.node('#workspace-link').getAttribute('aria-disabled'),'true');
}
assert.equal(hosted.run("companionWorkspaceUrl('http://localhost:8158/',null,null,true)"),'http://localhost:8158/#explorer-local');
assert.equal(hosted.run("companionWorkspaceUrl('http://[::1]:8158/',null,null)"),'http://[::1]:8158/#explorer');
assert.equal(hosted.run("companionWorkspaceUrl('http://127.0.0.1:8150/','S/a','T/b')"),'http://127.0.0.1:8150/#explorer/S%2Fa/T%2Fb');
// Unknown or private IDs never become a public-to-local handoff.
hosted.run('companionDialog("LOCAL-1","local-a")');
hosted.node('#workspace-address').value='http://localhost:8150/';hosted.node('#workspace-running').checked=true;hosted.node('#workspace-running').onchange();
assert.equal(hosted.node('#workspace-link').href,'http://localhost:8150/#explorer');
local.run("location.hash='#scenarios';route()");
assert.match(local.node('#view').innerHTML,/Discover a rule/);
local.run("location.hash='#explorer/ABSENT';route()");
assert.match(local.node('#error').textContent,/not included/);
console.log('PASS: public/local collections, filters, legacy route, escaping, setup gating, custom ports, subpath downloads and loopback handoff privacy');
