# gateway/router/telemetry_ui.py
from __future__ import annotations
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/v1/metrics", tags=["metrics-ui"])

_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>CLike • Harper Telemetry</title>
<style>
  :root{ --teal:#1fb2a6; --ocra:#ffb000; --coral:#ff6f61; --ink:#0f172a; --bg:#fffbea; }
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;margin:0;background:var(--bg);color:var(--ink)}
  header{display:flex;align-items:center;gap:12px;padding:14px 18px;background:linear-gradient(90deg,var(--ocra),#ffd45e)}
  header img{width:36px;height:36px;border-radius:8px;box-shadow:0 2px 6px rgba(0,0,0,.15)}
  header h1{font-size:18px;margin:0}
  .shell{padding:18px}
  .toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:16px}
  .tabs{display:flex;gap:6px;margin:0 0 12px 0}
  .tab{padding:8px 12px;border-radius:10px;cursor:pointer;background:#fff;border:1px solid #eee}
  .tab.active{background:var(--teal);color:#fff;border-color:transparent}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  @media (max-width:1000px){ .grid{grid-template-columns:1fr} }
  .card{background:#fff;border-radius:14px;padding:14px;box-shadow:0 6px 16px rgba(0,0,0,.06)}
  canvas{height:320px;max-width:100%}
  table{width:100%;border-collapse:collapse;font-size:12px}
  th,td{border-bottom:1px solid #eee;padding:6px 8px;text-align:left}
  th.sortable{cursor:pointer}
  .badge{padding:2px 6px;border-radius:999px;background:var(--teal);color:#fff;font-size:11px}
  select,input,button{padding:8px 10px;border:1px solid #ddd;border-radius:10px;background:#fff}
  button{background:var(--teal);color:#fff;border:none;cursor:pointer}
  .muted{opacity:.65}
  .hidden{display:none}
  .pager{display:flex;gap:8px;align-items:center;justify-content:flex-end;margin-top:10px}
  .empty{padding:24px;border:1px dashed #ddd;border-radius:12px;background:#fff}
  .help{font-size:12px}
</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
</head>
<body>
<header>
  <img src="/static/clike_64x64.png" alt="CLike" onerror="this.style.visibility='hidden'">
  <h1>CLike • Harper Telemetry <span class="badge">beta</span></h1>
</header>

<div class="shell">
  <div class="toolbar">
    <label>Project</label>
    <select id="project"></select>

    <label>File</label>
    <select id="file"></select>

    <button id="refresh">Load</button>
    <span id="summary" class="muted"></span>
  </div>
  <div class="help muted">Suggerimento: scegli un <b>File</b> per analizzare solo quel file; scegli “(whole project)” per l’intero progetto.</div>

  <div id="emptyState" class="empty hidden">
    Nessun file di telemetria trovato. Verifica la cartella <code>telemetry/</code>.
  </div>

  <div id="tabsRoot" class="">
    <div class="tabs">
      <div class="tab active" data-tab="overview">Overview</div>
      <div class="tab" data-tab="table">Table</div>
    </div>

    <!-- OVERVIEW -->
    <section id="tab-overview">
      <div class="grid">
        <div class="card"><h3>Cost by Day</h3><canvas id="costDay"></canvas></div>
        <div class="card"><h3>Runs by Day</h3><canvas id="runsDay"></canvas></div>
        <div class="card"><h3>Tokens per Day (In/Out)</h3><canvas id="tokensDay"></canvas></div>
        <div class="card"><h3>Cost by Phase</h3><canvas id="costPhase"></canvas></div>
        <div class="card"><h3>Cost by Provider</h3><canvas id="costProvider"></canvas></div>
        <div class="card"><h3>Cost by Model</h3><canvas id="costModel"></canvas></div>
        <div class="card">
          <h3>Top 10 Costly Runs</h3>
          <table id="topTable"><thead>
            <tr><th>#</th><th>Run</th><th>Phase</th><th>Model</th><th>Provider</th><th>Cost (USD)</th><th>Time</th></tr>
          </thead><tbody></tbody></table>
        </div>
        <div class="card"><h3>Tokens Series (time)</h3><canvas id="tokensSeries"></canvas></div>
      </div>
    </section>

    <!-- TABLE -->
    <section id="tab-table" class="hidden">
      <div class="card">
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">
          <input id="searchRun" placeholder="Search run_id…" />
          <select id="phaseFilter"><option value="">(phase)</option></select>
          <select id="providerFilter"><option value="">(provider)</option></select>
          <select id="modelFilter"><option value="">(model)</option></select>
          <select id="pageSize">
            <option>25</option><option>50</option><option>100</option><option>200</option>
          </select>
          <button id="applyFilter">Apply</button>
        </div>
        <table id="rawTable">
          <thead>
            <tr>
              <th class="sortable" data-k="timestamp">Timestamp</th>
              <th>Run</th>
              <th class="sortable" data-k="phase">Phase</th>
              <th class="sortable" data-k="model">Model</th>
              <th class="sortable" data-k="provider">Provider</th>
              <th class="sortable" data-k="cost">Cost (USD)</th>
              <th class="sortable" data-k="tokens_in">In</th>
              <th class="sortable" data-k="tokens_out">Out</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
        <div class="pager">
          <button id="prev">Prev</button>
          <span id="pageInfo" class="muted"></span>
          <button id="next">Next</button>
        </div>
      </div>
    </section>
  </div>
</div>

<script>
const C = {}; // charts
let sortKey = "timestamp";
let sortDir = "desc";
let curPage = 1;

function n(x){ return Number(x||0); }
function fmtUSD(x){ return '$'+(Math.round(n(x)*100)/100).toFixed(2); }
function seriesToISO(ts){ return new Date(ts*1000).toISOString().slice(0,19).replace('T',' '); }
async function j(url){ const r = await fetch(url); if(!r.ok) throw new Error(await r.text()); return await r.json(); }

function showEmptyState(show){
  document.getElementById('emptyState').classList.toggle('hidden', !show);
  document.getElementById('tabsRoot').classList.toggle('hidden', show);
}

async function initProjects(){
  const res = await j('/v1/metrics/harper/projects');
  const ids = (res.projects||[]).map(p=>p.id);
  const sel = document.getElementById('project');
  const fileSel = document.getElementById('file');

  if(ids.length === 0){
    sel.innerHTML = '';
    fileSel.innerHTML = '';
    showEmptyState(true);
    document.getElementById('summary').textContent = '';
    return;
  }

  showEmptyState(false);

  const lastProj = localStorage.getItem('harper:lastProject');
  const initial = (lastProj && ids.includes(lastProj)) ? lastProj : ids[0];
  sel.innerHTML = ids.map(id => `<option value="${id}">${id}</option>`).join('');
  sel.value = initial;

  await loadFilesForProject(initial); // popola combo file

  sel.addEventListener('change', async ()=>{
    localStorage.setItem('harper:lastProject', sel.value);
    curPage = 1;
    // reset filters
    document.getElementById('searchRun').value = '';
    document.getElementById('phaseFilter').value = '';
    document.getElementById('providerFilter').value = '';
    document.getElementById('modelFilter').value = '';
    await loadFilesForProject(sel.value);
    await loadOverview();
    if(!document.getElementById('tab-table').classList.contains('hidden')) await loadTable();
  });

  document.getElementById('file').addEventListener('change', async ()=>{
    curPage = 1;
    await loadOverview();
    if(!document.getElementById('tab-table').classList.contains('hidden')) await loadTable();
  });

  await loadOverview();
}

async function loadFilesForProject(projectId){
  const fileSel = document.getElementById('file');
  const res = await j(`/v1/metrics/harper/files?project_id=${encodeURIComponent(projectId)}`);
  const files = res.files || [];

  // option "(whole project)" = stringa vuota
  const options = [`<option value="">(whole project)</option>`]
    .concat(files.map(f => `<option value="${f.relpath}">${f.relpath}</option>`));
  fileSel.innerHTML = options.join('');

  // seleziona ultimo file scelto per quel progetto, altrimenti il primo
  const key = `harper:lastFile:${projectId}`;
  const last = localStorage.getItem(key);
  if(last && files.some(f=>f.relpath===last)){
    fileSel.value = last;
  }else{
    fileSel.value = files.length ? files[0].relpath : '';
  }
  localStorage.setItem(key, fileSel.value);
}

function rememberFileSelection(){
  const pid = document.getElementById('project').value;
  const rel = document.getElementById('file').value;
  localStorage.setItem(`harper:lastFile:${pid}`, rel);
}

function apiScope(){
  const pid = document.getElementById('project').value;
  const rel = document.getElementById('file').value;
  // se relpath empty => ambito progetto
  if(rel === '') return { scope: 'project', pid, rel: null };
  return { scope: 'file', pid, rel };
}

function renderChart(id, type, data, options){
  if(C[id]) C[id].destroy();
  C[id] = new Chart(document.getElementById(id), { type, data, options });
}

async function loadOverview(){
  rememberFileSelection();
  const s = apiScope();

  let agg, ser, top;
  if(s.scope === 'project'){
    agg = await j(`/v1/metrics/harper/aggregate?project_id=${encodeURIComponent(s.pid)}`);
    ser = await j(`/v1/metrics/harper/series?project_id=${encodeURIComponent(s.pid)}`);
    top = await j(`/v1/metrics/harper/top?project_id=${encodeURIComponent(s.pid)}&limit=10`);
  }else{
    agg = await j(`/v1/metrics/harper/aggregate_file?relpath=${encodeURIComponent(s.rel)}`);
    ser = await j(`/v1/metrics/harper/series_file?relpath=${encodeURIComponent(s.rel)}`);
    top = await j(`/v1/metrics/harper/top_file?relpath=${encodeURIComponent(s.rel)}&limit=10`);
  }

  const title = (s.scope==='project')
    ? `${s.pid} — runs: ${agg.total_runs||0}, cost: ${fmtUSD(agg.total_cost_usd||0)}`
    : `${s.rel} — runs: ${agg.total_runs||0}, cost: ${fmtUSD(agg.total_cost_usd||0)}`;
  document.getElementById('summary').textContent = title;

  // quick filters
  const phases = Object.keys(agg.per_phase||{});
  const providers = Object.keys(agg.per_provider||{});
  const models = Object.keys(agg.per_model||{});
  document.getElementById('phaseFilter').innerHTML = '<option value="">(phase)</option>' + phases.map(p=>`<option>${p}</option>`).join('');
  document.getElementById('providerFilter').innerHTML = '<option value="">(provider)</option>' + providers.map(p=>`<option>${p}</option>`).join('');
  document.getElementById('modelFilter').innerHTML = '<option value="">(model)</option>' + models.map(m=>`<option>${m}</option>`).join('');

  const days = Object.keys(agg.by_day||{}).sort();
  renderChart('costDay','line',{labels:days,datasets:[{label:'Cost (USD)',data:days.map(d=>(agg.by_day[d]?.cost_usd)||0)}]},
    {scales:{y:{beginAtZero:true}}});
  renderChart('runsDay','bar',{labels:days,datasets:[{label:'Runs',data:days.map(d=>(agg.by_day[d]?.runs)||0)}]},
    {scales:{y:{beginAtZero:true}}});
  renderChart('tokensDay','bar',{labels:days,datasets:[
      {label:'Input',data:days.map(d=>(agg.by_day[d]?.tokens_in)||0),stack:'tok'},
      {label:'Output',data:days.map(d=>(agg.by_day[d]?.tokens_out)||0),stack:'tok'}
    ]},{scales:{y:{beginAtZero:true}}});

  renderChart('costPhase','doughnut',{labels:phases,datasets:[{data:phases.map(p=>(agg.per_phase[p]?.cost_usd)||0)}]});
  renderChart('costProvider','pie',{labels:providers,datasets:[{data:providers.map(p=>(agg.per_provider[p]?.cost_usd)||0)}]});
  renderChart('costModel','bar',{labels:models,datasets:[{label:'USD',data:models.map(m=>(agg.per_model[m]?.cost_usd)||0)}]},
    {indexAxis:'y',scales:{x:{beginAtZero:true}}});

  const sLabels = (ser.series||[]).map(x=>new Date((x.t||0)*1000).toLocaleString());
  renderChart('tokensSeries','line',{labels:sLabels,datasets:[
    {label:'Input tokens',data:(ser.series||[]).map(x=>x.tokens_in||0)},
    {label:'Output tokens',data:(ser.series||[]).map(x=>x.tokens_out||0)}
  ]},{scales:{y:{beginAtZero:true}}});

  const tb = document.querySelector('#topTable tbody');
  tb.innerHTML = (top.top||[]).map((r,i)=>`
    <tr>
      <td>${i+1}</td>
      <td class="muted">${r.run_id||''}</td>
      <td>${r.phase||''}</td>
      <td>${r.model||''}</td>
      <td>${r.provider||''}</td>
      <td>${fmtUSD((r.pricing?.total_cost) ?? r.cost_usd_est ?? 0)}</td>
      <td>${new Date((r.timestamp||0)*1000).toLocaleString()}</td>
    </tr>`).join('');
}

async function loadTable(){
  const s = apiScope();
  const q  = document.getElementById('searchRun').value || '';
  const ph = document.getElementById('phaseFilter').value || '';
  const pr = document.getElementById('providerFilter').value || '';
  const mo = document.getElementById('modelFilter').value || '';
  const ps = document.getElementById('pageSize').value;

  let url;
  if(s.scope === 'project'){
    url = `/v1/metrics/harper/raw?project_id=${encodeURIComponent(s.pid)}&q=${encodeURIComponent(q)}&phase=${encodeURIComponent(ph)}&provider=${encodeURIComponent(pr)}&model=${encodeURIComponent(mo)}&sort=${sortKey}:${sortDir}&page=${curPage}&page_size=${ps}`;
  }else{
    url = `/v1/metrics/harper/raw_file?relpath=${encodeURIComponent(s.rel)}&q=${encodeURIComponent(q)}&phase=${encodeURIComponent(ph)}&provider=${encodeURIComponent(pr)}&model=${encodeURIComponent(mo)}&sort=${sortKey}:${sortDir}&page=${curPage}&page_size=${ps}`;
  }
  const data = await j(url);

  const tbody = document.querySelector('#rawTable tbody');
  tbody.innerHTML = (data.items||[]).map(r=>`
    <tr>
      <td>${new Date((r.timestamp||0)*1000).toLocaleString()}</td>
      <td class="muted">${r.run_id||''}</td>
      <td>${r.phase||''}</td>
      <td>${r.model||''}</td>
      <td>${r.provider||''}</td>
      <td>${fmtUSD((r.pricing?.total_cost) ?? r.cost_usd_est ?? 0)}</td>
      <td>${(r.usage?.prompt_tokens ?? r.usage?.input_tokens ?? 0)}</td>
      <td>${(r.usage?.completion_tokens ?? r.usage?.output_tokens ?? 0)}</td>
    </tr>`).join('');

  const pages = Math.max(1, Math.ceil((data.total||0) / Number(ps)));
  document.getElementById('pageInfo').textContent = `Page ${data.page||1} / ${pages} — ${data.total||0} rows`;
  document.getElementById('prev').disabled = ((data.page||1)<=1);
  document.getElementById('next').disabled = ((data.page||1)>=pages);
}

function activateTabs(){
  const tabs = document.querySelectorAll('.tab');
  tabs.forEach(t => t.addEventListener('click', () => {
    tabs.forEach(x=>x.classList.remove('active')); t.classList.add('active');
    document.getElementById('tab-overview').classList.toggle('hidden', t.dataset.tab!=='overview');
    document.getElementById('tab-table').classList.toggle('hidden', t.dataset.tab!=='table');
    if(t.dataset.tab==='table'){ curPage=1; loadTable(); }
  }));
}

document.getElementById('refresh').addEventListener('click', ()=>{
  loadOverview();
  if(!document.getElementById('tab-table').classList.contains('hidden')) loadTable();
});

document.getElementById('applyFilter').addEventListener('click', ()=>{ curPage=1; loadTable(); });
document.getElementById('prev').addEventListener('click', ()=>{ if(curPage>1){curPage--; loadTable();} });
document.getElementById('next').addEventListener('click', ()=>{ curPage++; loadTable(); });

document.querySelectorAll('#rawTable th.sortable').forEach(th=>{
  th.addEventListener('click', ()=>{
    const k = th.dataset.k;
    if(sortKey===k){ sortDir = (sortDir==='asc'?'desc':'asc'); }
    else { sortKey = k; sortDir='desc'; }
    if(k==='phase' || k==='model' || k==='provider'){ sortKey='timestamp'; } // backend ordina solo campi numerici
    curPage=1; loadTable();
  });
});

initProjects().then(()=>{ activateTabs(); });
</script>
</body>
</html>
"""

@router.get("/harper/ui", response_class=HTMLResponse)
def ui() -> HTMLResponse:
    return HTMLResponse(_HTML)
