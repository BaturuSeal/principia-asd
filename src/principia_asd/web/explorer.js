'use strict';

// One entry point for the public collection and a visitor's private workspace.
// Hosted pages never probe a loopback service or persist private workspace paths.
const explorerState = {collection: 'public', query: '', domain: '', equations: false, limit: 12};
const discoveryDrafts = new Map();
const isLocalScenario = s => s.task?.test_exposure === 'local-user-split';
const hasEquations = s => s.tasks.some(t => t.equation_templates?.length);

function explorer() {
  const local = isPublic ? [] : state.scenarios.filter(isLocalScenario);
  const publicScenarios = state.scenarios.filter(s => !isLocalScenario(s));
  const domains = [...new Set(state.scenarios.map(s => s.domain))].sort();
  const s = state.scenarios.find(s => s.scenario_id === state.selected) || state.scenarios[0];
  if (s) { state.selected = s.scenario_id; chooseTask(s); }
  $('#view').innerHTML = `<div class="explorer-heading"><div><div class="eyebrow">Scientific rule discovery</div><h1>Explorer</h1><p class="lead">Start with a public example, or investigate a question in your own data.</p></div><div class="explorer-counts"><span><strong>${publicScenarios.length}</strong> public examples</span><span><strong>${publicScenarios.filter(hasEquations).length}</strong> with equation systems</span></div></div>
    <section class="discovery-launcher" aria-labelledby="launcher-title">
      <div class="launcher-heading"><div><span class="eyebrow">Your next investigation</span><h2 id="launcher-title">Discover a rule</h2></div><span class="workspace-badge">${isPublic ? 'Runs privately on your computer' : '<span class="dot"></span>Local workspace ready'}</span></div>
      <div class="launcher-fields"><div><label for="explorer-scenario">Scenario</label><select id="explorer-scenario">${publicScenarios.length ? `<optgroup label="Public examples">${scenarioOptions(publicScenarios)}</optgroup>` : ''}${local.length ? `<optgroup label="My scenarios">${scenarioOptions(local)}</optgroup>` : ''}</select></div><div><label for="explorer-task">Task</label><select id="explorer-task"></select></div><button class="primary" id="configure-discovery" ${s ? '' : 'disabled'}>${isPublic ? 'Try it yourself' : 'Configure discovery'} <span aria-hidden="true">→</span></button></div>
      <div class="launcher-footer"><button class="link" id="explorer-task-details" aria-haspopup="dialog">View inputs &amp; output</button><span id="explorer-task-summary"></span><button class="link" id="launcher-import" aria-haspopup="dialog">＋ Add a local scenario</button></div>
      ${isPublic ? '<p class="launcher-note">Browsing needs no setup. To run a method, first install and start the local companion on your computer.</p>' : ''}
    </section>
    <section class="explorer-library" aria-label="Scenario collection"><div class="collection-heading"><div class="collection-tabs" role="tablist" aria-label="Scenario collection"><button id="public-scenarios-tab" role="tab" aria-controls="collection-panel">Public examples <span>${publicScenarios.length}</span></button><button id="local-scenarios-tab" role="tab" aria-controls="collection-panel">My scenarios <span>${isPublic ? 'Local' : local.length}</span></button></div><button id="collection-import" class="small" aria-haspopup="dialog">＋ Add scenario</button></div>
    <div id="collection-panel" role="tabpanel"><p id="collection-description" class="collection-description"></p><div class="toolbar explorer-toolbar" id="collection-filters"><input id="search-scenarios" aria-label="Search scenarios" placeholder="Search a phenomenon, domain or scenario…" value="${esc(explorerState.query)}"><select id="domain-filter" aria-label="Filter domain"><option value="">All domains</option>${domains.map(d => `<option ${d === explorerState.domain ? 'selected' : ''}>${esc(d)}</option>`).join('')}</select><label class="equation-filter"><input type="checkbox" id="equation-filter" ${explorerState.equations ? 'checked' : ''}>Equation systems</label></div><div class="collection-results"><p id="library-count" role="status"></p><button class="link hidden" id="clear-filters">Clear filters</button></div><div class="cards explorer-cards" id="scenario-cards"></div><div class="collection-more" id="collection-more"></div></div></section>`;
  const refreshTask = () => {
    const current = state.scenarios.find(s => s.scenario_id === state.selected);
    if (!current) return;
    const t = chooseTask(current);
    $('#explorer-task').innerHTML = current.tasks.map(t => `<option value="${esc(t.task_id)}" ${t.task_id === state.task ? 'selected' : ''}>${esc(t.display_title)}${t.custom ? ' · custom' : ''}</option>`).join('');
    $('#explorer-task-summary').textContent = `${t.inputs.length} inputs · ${t.metric.primary.toUpperCase()} · ${hasEquations(current) && t.equation_templates?.length ? 'Connected equations' : 'Prediction task'}`;
    $('#explorer-task-details').dataset.taskDetail = t.task_id;
    bindTaskCards($('#view'));
  };
  refreshTask();
  $('#explorer-scenario').onchange = () => { state.selected = $('#explorer-scenario').value; state.task = null; refreshTask(); };
  $('#explorer-task').onchange = () => { state.task = $('#explorer-task').value; refreshTask(); };
  $('#configure-discovery').onclick = () => openDiscovery();
  $('#launcher-import').onclick = () => importScenarioDialog();
  $('#collection-import').onclick = () => importScenarioDialog();
  const selectCollection = collection => {
    if (explorerState.collection !== collection) {
      explorerState.query = ''; explorerState.domain = ''; explorerState.equations = false;
      $('#search-scenarios').value = ''; $('#domain-filter').value = ''; $('#equation-filter').checked = false;
    }
    explorerState.collection = collection; explorerState.limit = 12;
    renderExplorerCollection();
  };
  $('#public-scenarios-tab').onclick = () => selectCollection('public');
  $('#local-scenarios-tab').onclick = () => selectCollection('local');
  for (const id of ['public-scenarios-tab', 'local-scenarios-tab']) {
    $('#'+id).onkeydown = event => {
      if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
      event.preventDefault();
      const localTab = event.key === 'End' || (event.key !== 'Home' && explorerState.collection !== 'local');
      selectCollection(localTab ? 'local' : 'public');
      $(localTab ? '#local-scenarios-tab' : '#public-scenarios-tab').focus();
    };
  }
  const filter = () => {
    explorerState.query = $('#search-scenarios').value;
    explorerState.domain = $('#domain-filter').value;
    explorerState.equations = $('#equation-filter').checked;
    explorerState.limit = 12; renderExplorerCollection();
  };
  $('#search-scenarios').oninput = filter;
  $('#domain-filter').onchange = filter;
  $('#equation-filter').onchange = filter;
  $('#clear-filters').onclick = () => {
    $('#search-scenarios').value = ''; $('#domain-filter').value = ''; $('#equation-filter').checked = false; filter();
  };
  renderExplorerCollection();
}

function scenarioOptions(scenarios) {
  return scenarios.map(s => `<option value="${esc(s.scenario_id)}" ${s.scenario_id === state.selected ? 'selected' : ''}>${esc(s.title)}</option>`).join('');
}

function renderExplorerCollection() {
  const local = explorerState.collection === 'local';
  for (const [id, selected] of [['public-scenarios-tab', !local], ['local-scenarios-tab', local]]) {
    const button = $('#'+id); button.classList.toggle('active', selected);
    button.setAttribute('aria-selected', String(selected)); button.tabIndex = selected ? 0 : -1;
  }
  $('#collection-panel').setAttribute('aria-labelledby', local ? 'local-scenarios-tab' : 'public-scenarios-tab');
  const all = isPublic && local ? [] : state.scenarios.filter(s => isLocalScenario(s) === local);
  const q = explorerState.query.trim().toLowerCase();
  const list = all.filter(s => (!explorerState.equations || hasEquations(s)) && (!explorerState.domain || s.domain === explorerState.domain) && [s.title,s.description,s.domain,s.scenario_id].join(' ').toLowerCase().includes(q))
    .sort((a,b) => Number(hasEquations(b))-Number(hasEquations(a)) || a.title.localeCompare(b.title));
  $('#collection-description').textContent = local ? (isPublic ? 'Your private collection lives in the local companion on your computer.' : 'Imported folders, your own questions, and personal investigations. These scenarios stay in this workspace.') : 'Curated scientific examples with documented tasks and explored rules. Choose an example to inspect the evidence or try a method yourself.';
  $('#collection-filters').classList.toggle('hidden', local && !all.length);
  $('#library-count').textContent = local && !all.length ? '' : `Showing ${Math.min(list.length,explorerState.limit)} of ${list.length} ${local ? 'local scenarios' : 'examples'}`;
  $('#clear-filters').classList.toggle('hidden', !(q || explorerState.domain || explorerState.equations) || (local && !all.length));
  $('#scenario-cards').innerHTML = local && !all.length ? `<article class="local-empty"><div class="local-folder-icon" aria-hidden="true">＋</div><div><h3>A place for your own questions</h3><p>${isPublic ? 'Add a data folder in the local companion. Your scenarios and new results stay on that device; this website cannot list or receive them.' : 'Start with a folder of numeric CSV measurements. Choose an output, permitted inputs and independent groups to create your first scenario.'}</p><button class="primary" id="empty-import">${isPublic ? 'Set up local discovery' : 'Add a local scenario'}</button><span class="hint">${isPublic ? 'macOS / Linux · Python 3.11+' : 'CSV or CSV.gz · up to 10 MB expanded'}</span></div></article>` : list.slice(0, explorerState.limit).map(s => {
    const count = state.boards.filter(b => b.scenario_id === s.scenario_id).reduce((n,b) => n+(b.rule_count ?? b.rules?.length ?? 0),0);
    return `<article class="scenario-card"><div class="scenario-card-top"><span class="scenario-domain">${esc(s.domain)}</span><span class="scenario-id">${esc(s.scenario_id)}</span></div><h3><a href="#scenario/${esc(s.scenario_id)}">${esc(s.title)}</a></h3><p class="description">${esc(s.description)}</p><div class="scenario-metadata"><span>${s.tasks.length} ${s.tasks.length === 1 ? 'task' : 'tasks'}</span><span>${local ? 'Private to this workspace' : `${count} explored rules`}</span>${hasEquations(s) ? '<span class="equation-label">Equation systems</span>' : ''}</div><div class="card-footer"><a href="#scenario/${esc(s.scenario_id)}">View scenario <span aria-hidden="true">↗</span></a><button class="small" data-select="${esc(s.scenario_id)}" aria-label="Try it yourself: ${esc(s.title)}">Try it yourself</button></div></article>`;
  }).join('') || '<div class="empty filtered-empty"><h3>No matching scenarios</h3><p>Try a broader search or clear the filters.</p></div>';
  if ($('#empty-import')) $('#empty-import').onclick = () => importScenarioDialog();
  document.querySelectorAll('[data-select]').forEach(button => button.onclick = () => tryScenario(button.dataset.select));
  $('#collection-more').innerHTML = list.length > explorerState.limit ? '<button id="more-scenarios">Show more scenarios</button>' : '';
  if ($('#more-scenarios')) $('#more-scenarios').onclick = () => { explorerState.limit += 12; renderExplorerCollection(); };
}

function openDiscovery() {
  if (isPublic) { companionDialog(state.selected,state.task); return; }
  if (!state.scenarios.length) { importScenarioDialog(); return; }
  renderDiscoveryForm();
  if (!$('#discovery-dialog').open) $('#discovery-dialog').showModal();
}

function rememberDiscovery() {
  if (!$('#method')) return;
  discoveryDrafts.set(`${state.selected}/${state.task}`, {
    method: $('#method').value, protocol: $('#protocol').value, objective: $('#objective').value,
    budget: $('#budget').value, models: Object.fromEntries(Object.keys(state.config.model_roles).map(role => [role,$('#model-'+role).value]))
  });
}

function importScenarioDialog() {
  if (isPublic) { companionDialog(null,null,true); return; }
  $('#import-content').innerHTML = `<div class="eyebrow">My scenarios</div><h2 id="import-title">Add a local scenario</h2><p class="description">Read measurements from a folder on this computer. Your original files remain unchanged; the scenario and its results stay in your private workspace.</p><label for="local-path">Local data folder</label><div class="folder-input"><input id="local-path" placeholder="/path/to/measurements" autocomplete="off" spellcheck="false"><button id="inspect-local">Inspect folder</button></div><p class="hint">Numeric CSV or CSV.gz · up to 10 MB expanded · an independent group column is required.</p><label for="local-name">Scenario name <span class="muted">(optional)</span></label><input id="local-name" maxlength="120" placeholder="For example: Membrane transport experiment"><div id="import-error" class="error hidden" role="alert"></div><div id="import-fields"></div>`;
  $('#inspect-local').onclick = inspectLocal;
  $('#local-path').onkeydown = e => { if(e.key === 'Enter') { e.preventDefault(); inspectLocal(); } };
  $('#import-dialog').showModal();
}

// A loopback link is a handoff, not a connection test. Never send a folder or key.
function companionWorkspaceUrl(raw, sid, tid, importing=false) {
  const url = new URL(raw.trim());
  if (url.protocol !== 'http:' || !['127.0.0.1','localhost','[::1]'].includes(url.hostname) || url.username || url.password || url.search || (url.pathname && url.pathname !== '/') || url.hash) {
    throw Error('Use the local address printed by the companion, such as http://127.0.0.1:8150/. Remote addresses and URL credentials are not allowed.');
  }
  url.pathname = '/';
  url.hash = importing ? 'explorer-local' : 'explorer'+(sid ? '/'+encodeURIComponent(sid) : '')+(sid && tid ? '/'+encodeURIComponent(tid) : '');
  return url.href;
}

function companionDialog(sid=state.selected, tid=state.task, importing=false) {
  const s = state.scenarios.find(s => s.scenario_id === sid && !isLocalScenario(s));
  const t = s?.tasks.find(t => t.task_id === tid);
  sid = s?.scenario_id; tid = t?.task_id;
  const command = 'python3 -m venv ~/.principia-asd-venv\n~/.principia-asd-venv/bin/pip install .\n~/.principia-asd-venv/bin/principia-asd companion --bundle-root . --open-browser';
  $('#setup-content').innerHTML = `<div class="eyebrow">Private discovery · on your computer</div><h2 id="setup-title">Set up your local workspace</h2><p class="description">The public website displays shared examples. Running a method requires the companion on <strong>this computer</strong> — opening a link alone does not install or start it.</p>${s ? `<div class="handoff-selection"><span>Continue with</span><strong>${esc(s.title)}</strong>${t ? `<small>${esc(t.display_title)}</small>` : ''}</div>` : ''}<div class="tabs setup-tabs" role="tablist" aria-label="Local setup"><button id="setup-first" role="tab" aria-controls="setup-install" aria-selected="true" class="active">First-time setup</button><button id="setup-existing" role="tab" aria-controls="setup-connect" aria-selected="false" tabindex="-1">Already running</button></div>
    <div id="setup-install" role="tabpanel" aria-labelledby="setup-first"><ol class="installation-steps"><li><div><h3>Download and extract</h3><p>Open the extracted <code>public-release</code> folder in a terminal.</p>${state.config.companion_download ? `<a class="button-link" href="${esc(siteUrl(state.config.companion_download.url))}" download>Download companion · ${fmt(state.config.companion_download.bytes/1e6)} MB ↓</a>` : '<p class="hint">This preview has no bundled download. Use your existing public-release distribution.</p>'}</div></li><li><div><h3>Install and start</h3><p>Requires Python 3.11+ on macOS or Linux. Keep the terminal open while working.</p><div class="command-box"><button class="small" id="copy-setup-command">Copy commands</button><pre id="setup-command">${esc(command)}</pre></div></div></li><li><div><h3>Continue in the local browser tab</h3><p>The command opens your workspace automatically. Add your SiliconFlow key in API settings if your method uses a model. Numerical reference methods need no key.</p><button id="setup-ready">My companion is running →</button></div></li></ol><p class="setup-platform-note">On a phone, tablet or unsupported Windows installation? You can browse all explored rules here. Run the companion on a supported desktop computer for private discovery.</p></div>
    <div id="setup-connect" class="hidden" role="tabpanel" aria-labelledby="setup-existing"><h3>Open the companion you started</h3><p class="description">Use the address printed in its terminal. If you chose another port, change the address below. The public site does not test or access your local network.</p><label for="workspace-address">Companion address</label><input id="workspace-address" type="url" value="http://127.0.0.1:8150/" spellcheck="false" autocomplete="off"><label class="ready-check"><input type="checkbox" id="workspace-running"><span>The companion is running on this computer.</span></label><p id="workspace-address-error" class="error hidden" role="alert"></p><a id="workspace-link" class="button-link primary disabled-link" aria-disabled="true" tabindex="-1" rel="noreferrer" referrerpolicy="no-referrer">Continue to my workspace →</a><p class="hint">Continue in this tab. Your selected public example is carried over; no files, keys or personal results are sent. Use your browser’s Back button to return here.</p><details><summary>Connection refused or the workspace did not open?</summary><p>Start the companion first and keep its terminal open. Check that the address matches the one printed there. If port 8150 is in use, restart the command with <code>--port 8152</code> and enter <code>http://127.0.0.1:8152/</code> above.</p><p>If your browser blocks navigation, copy the local address into a new browser tab. Never enter a remote server address here.</p></details></div>`;
  const switchTab = existing => {
    $('#setup-install').classList.toggle('hidden',existing); $('#setup-connect').classList.toggle('hidden',!existing);
    for (const [id,active] of [['setup-first',!existing],['setup-existing',existing]]) {
      const b=$('#'+id); b.classList.toggle('active',active); b.setAttribute('aria-selected',String(active)); b.tabIndex=active?0:-1;
    }
  };
  $('#setup-first').onclick=()=>switchTab(false);
  $('#setup-existing').onclick=()=>switchTab(true);
  $('#setup-ready').onclick=()=>{switchTab(true);$('#workspace-running').focus();};
  for(const id of ['setup-first','setup-existing']) $('#'+id).onkeydown=e=>{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
    e.preventDefault();const existing=e.key==='End'||(e.key!=='Home'&&$('#setup-existing').getAttribute('aria-selected')!=='true');
    switchTab(existing);$(existing?'#setup-existing':'#setup-first').focus();
  };
  $('#copy-setup-command').onclick=async()=>{try{await navigator.clipboard.writeText(command);$('#copy-setup-command').textContent='Copied';}catch{$('#copy-setup-command').textContent='Select the commands to copy';}};
  const validateAddress=()=>{
    const a=$('#workspace-link');a.removeAttribute('href');a.setAttribute('aria-disabled','true');a.classList.add('disabled-link');a.tabIndex=-1;
    $('#workspace-address-error').classList.add('hidden');
    try {
      const url=companionWorkspaceUrl($('#workspace-address').value,sid,tid,importing);
      if($('#workspace-running').checked){a.href=url;a.setAttribute('aria-disabled','false');a.classList.remove('disabled-link');a.tabIndex=0;}
    }catch(e){$('#workspace-address-error').textContent=e.message;$('#workspace-address-error').classList.remove('hidden');}
  };
  $('#workspace-address').oninput=validateAddress;$('#workspace-running').onchange=validateAddress;
  $('#workspace-link').onclick=e=>{if(!$('#workspace-link').getAttribute('href'))e.preventDefault();};
  $('#setup-dialog').showModal();
}

function bindExplorerDialogs() {
for (const id of ['setup','discovery','import']) {
  const dialog=$('#'+id+'-dialog');
  dialog.querySelector('.close').onclick=()=>dialog.close();
  dialog.onclick=e=>{if(e.target===dialog)dialog.close();};
}
$('#discovery-dialog').addEventListener('close',()=>{
  rememberDiscovery();$('#discovery-content').replaceChildren();
  if (['','explorer','scenarios','discover','explorer-local'].includes(location.hash.slice(1).split('/')[0])) explorer();
});

}
