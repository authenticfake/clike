# gateway/router/telemetry_ui.py
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from utils.service_auth import COOKIE_NAME, configured_token, tokens_match

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
  .kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}
  .kpi{background:#fff;border-radius:14px;padding:12px 14px;box-shadow:0 6px 16px rgba(0,0,0,.06)}
  .kpi .v{font-size:22px;font-weight:600;margin-top:4px}
  .kpi .s{font-size:12px;opacity:.65;margin-top:2px}
  tr.click{cursor:pointer} tr.click:hover{background:#f6fffe} tr.sel{background:#e7f8f6}
  .wide{grid-column:1 / -1}
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
      <div class="tab" data-tab="reqs">Requirements</div>
      <div class="tab" data-tab="kpis">KPIs &amp; estimate</div>
      <div class="tab" data-tab="table">Table</div>
    </div>

    <!-- OVERVIEW -->
    <section id="tab-overview">
      <div class="grid">
        <div class="card"><h3>Cost by Day</h3><canvas id="costDay"></canvas></div>
        <div class="card"><h3>Runs by Day</h3><canvas id="runsDay"></canvas></div>
        <div class="card"><h3>Tokens per Day (In/Out)</h3><canvas id="tokensDay"></canvas></div>
        <div class="card"><h3>Cost by Phase <span class="muted" style="font-size:12px;font-weight:400">— click a phase to see its requirements</span></h3><canvas id="costPhase"></canvas></div>
        <div class="card"><h3>Cost by Provider</h3><canvas id="costProvider"></canvas></div>
        <div class="card"><h3>Cost by Model</h3><canvas id="costModel"></canvas></div>
        <div class="card">
          <h3>Top 10 Costly Runs</h3>
          <table id="topTable"><thead>
            <tr><th>#</th><th>Run</th><th>Phase</th><th>Model</th><th>Provider</th><th>Cost (USD)</th><th>Time</th></tr>
          </thead><tbody></tbody></table>
        </div>
        <div class="card"><h3>Tokens Series (time)</h3><canvas id="tokensSeries"></canvas></div>
        <div id="phaseDrill" class="card wide hidden">
          <h3 id="phaseDrillTitle"></h3>
          <div class="grid">
            <div><canvas id="phaseDrillChart"></canvas></div>
            <div style="max-height:360px;overflow:auto">
              <table id="phaseDrillTable"><thead>
                <tr><th>REQ</th><th>Runs</th><th>Time</th><th>Cost (USD)</th><th>Tokens in</th><th>Out</th></tr>
              </thead><tbody></tbody></table>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- REQUIREMENTS -->
    <section id="tab-reqs" class="hidden">
      <div class="grid">
        <div class="card wide">
          <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">
            <h3 style="margin:0">Top requirements by</h3>
            <select id="reqMetric">
              <option value="cost_usd">cost</option><option value="duration_ms">time</option>
              <option value="repairs">repairs</option><option value="eval_failed">failed evals</option>
              <option value="tokens_in">input tokens</option>
            </select>
          </div>
          <canvas id="reqRankChart"></canvas>
        </div>
        <div class="card wide">
          <h3>Ranking <span class="muted" style="font-size:12px;font-weight:400">— click a column to sort, a row for its phases</span></h3>
          <div style="max-height:480px;overflow:auto">
          <table id="reqTable"><thead><tr>
            <th>#</th><th class="sortable" data-k="req_id">REQ</th><th class="sortable" data-k="cost_usd">Cost (USD)</th>
            <th class="sortable" data-k="duration_ms" title="Agent and model work plus eval sandbox time">Time</th>
            <th class="sortable" data-k="agent_ms">Agent time</th><th class="sortable" data-k="sandbox_ms">Eval time</th>
            <th class="sortable" data-k="span_s" title="First to last run (wall clock, waits included)">Elapsed</th>
            <th class="sortable" data-k="kit_runs">KIT runs</th><th class="sortable" data-k="repairs">Repairs</th>
            <th class="sortable" data-k="eval_runs">Evals</th><th class="sortable" data-k="eval_failed">Failed</th>
            <th>First eval</th><th>Gate</th><th class="sortable" data-k="tokens_in">Tokens in</th>
          </tr></thead><tbody></tbody></table>
          </div>
        </div>
        <div id="reqDetail" class="card wide hidden">
          <h3 id="reqDetailTitle"></h3>
          <div class="grid">
            <div><canvas id="reqDetailChart"></canvas></div>
            <div><table id="reqDetailTable"><thead>
              <tr><th>Phase</th><th>Runs</th><th>Time</th><th>Cost (USD)</th><th>Tokens in</th><th>Out</th><th>Cached</th></tr>
            </thead><tbody></tbody></table></div>
          </div>
        </div>
      </div>
    </section>

    <!-- KPIS -->
    <section id="tab-kpis" class="hidden">
      <div class="help muted" style="margin-bottom:10px">Over the requirements (REQ-…) of the selection. Median and p90 (9 REQs out of 10 cost or take less) are the basis of the estimate; the phases without a REQ (idea, spec, plan, extend, finalize) are shown apart.</div>
      <div id="kpiTiles" class="kpis"></div>
      <div class="card" style="margin-top:16px">
        <h3>Estimate</h3>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <label>Requirements to build</label><input id="estN" type="number" min="1" max="1000" value="5" style="width:90px">
          <button id="estGo">Estimate</button><span id="estOut"></span>
        </div>
        <div class="help muted" style="margin-top:8px">Range from this project's history: median (typical) to p90 (prudent), for REQs of similar size. Time is work time (agents, models, eval sandbox), not calendar time.</div>
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
              <th title="Prompt-cache tokens: reads (OpenAI cached input, Anthropic cache hits) and Anthropic cache writes">Cached</th>
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
function fmtDur(ms){ const s=Math.round(n(ms)/1000); if(s<60) return s+' s'; const m=Math.round(s/60); if(m<60) return m+' min'; return Math.floor(m/60)+' h '+String(m%60).padStart(2,'0')+' min'; }
function fmtInt(x){ return n(x).toLocaleString('en-US'); }
function fmtPct(x){ return (x===null||x===undefined) ? '—' : Math.round(n(x)*100)+'%'; }
function seriesToISO(ts){ return new Date(ts*1000).toISOString().slice(0,19).replace('T',' '); }
function esc(v){ return String(v ?? '').replace(/[&<>"'`]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;','`':'&#96;'}[c])); }
async function login(){
  const token = window.prompt('CLike service token (CLIKE_API_TOKEN):');
  if (!token) return false;
  const r = await fetch('/v1/metrics/login', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({token})});
  return r.ok;
}
async function j(url){
  let r = await fetch(url, {credentials:'same-origin'});
  if (r.status === 401 && await login()) r = await fetch(url, {credentials:'same-origin'});
  if(!r.ok) throw new Error(await r.text());
  return await r.json();
}

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
  sel.innerHTML = ids.map(id => `<option value="${esc(id)}">${esc(id)}</option>`).join('');
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
    .concat(files.map(f => `<option value="${esc(f.relpath)}">${esc(f.relpath)}</option>`));
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
  document.getElementById('phaseFilter').innerHTML = '<option value="">(phase)</option>' + phases.map(p=>`<option>${esc(p)}</option>`).join('');
  document.getElementById('providerFilter').innerHTML = '<option value="">(provider)</option>' + providers.map(p=>`<option>${esc(p)}</option>`).join('');
  document.getElementById('modelFilter').innerHTML = '<option value="">(model)</option>' + models.map(m=>`<option>${esc(m)}</option>`).join('');

  const days = Object.keys(agg.by_day||{}).sort();
  renderChart('costDay','line',{labels:days,datasets:[{label:'Cost (USD)',data:days.map(d=>(agg.by_day[d]?.cost_usd)||0)}]},
    {scales:{y:{beginAtZero:true}}});
  renderChart('runsDay','bar',{labels:days,datasets:[{label:'Runs',data:days.map(d=>(agg.by_day[d]?.runs)||0)}]},
    {scales:{y:{beginAtZero:true}}});
  renderChart('tokensDay','bar',{labels:days,datasets:[
      {label:'Input',data:days.map(d=>(agg.by_day[d]?.tokens_in)||0),stack:'tok'},
      {label:'Output',data:days.map(d=>(agg.by_day[d]?.tokens_out)||0),stack:'tok'},
      {label:'Cached',data:days.map(d=>(agg.by_day[d]?.tokens_cached)||0)}
    ]},{scales:{y:{beginAtZero:true}}});

  renderChart('costPhase','doughnut',{labels:phases,datasets:[{data:phases.map(p=>(agg.per_phase[p]?.cost_usd)||0)}]},
    {onClick:(_e,els)=>{ if(els.length){ showPhase(phases[els[0].index]); } }});
  await loadReqs();
  document.getElementById('phaseDrill').classList.add('hidden');
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
      <td class="muted">${esc(r.run_id)}</td>
      <td>${esc(r.phase)}</td>
      <td>${esc(r.model)}</td>
      <td>${esc(r.provider)}</td>
      <td>${fmtUSD((r.pricing?.total_cost) ?? r.cost_usd_est ?? 0)}</td>
      <td>${new Date((r.timestamp||0)*1000).toLocaleString()}</td>
    </tr>`).join('');
}

let REQS = null; let reqSortKey = 'cost_usd'; let reqSortDir = 'desc';
async function loadReqs(estimate){
  const s = apiScope();
  const est = estimate ? `&estimate_reqs=${encodeURIComponent(estimate)}` : '';
  REQS = (s.scope === 'project')
    ? await j(`/v1/metrics/harper/reqs?project_id=${encodeURIComponent(s.pid)}${est}`)
    : await j(`/v1/metrics/harper/reqs_file?relpath=${encodeURIComponent(s.rel)}${est}`);
  return REQS;
}
function showPhase(phase){
  if(!REQS) return;
  const items = (REQS.phase_reqs||{})[phase] || [];
  const box = document.getElementById('phaseDrill'); box.classList.remove('hidden');
  document.getElementById('phaseDrillTitle').textContent = `Phase ${phase} by requirement — ${items.length} item(s)`;
  const top = items.slice(0, 15);
  renderChart('phaseDrillChart','bar',{labels:top.map(x=>x.req_id),datasets:[{label:'Cost (USD)',data:top.map(x=>x.cost_usd)}]},
    {indexAxis:'y',scales:{x:{beginAtZero:true}}});
  document.querySelector('#phaseDrillTable tbody').innerHTML = items.map(x=>`
    <tr class="click" data-req="${esc(x.req_id)}"><td>${esc(x.req_id)}</td><td>${x.runs}</td><td>${fmtDur(x.duration_ms)}</td>
    <td>${fmtUSD(x.cost_usd)}</td><td>${fmtInt(x.tokens_in)}</td><td>${fmtInt(x.tokens_out)}</td></tr>`).join('');
  document.querySelectorAll('#phaseDrillTable tr.click').forEach(tr=>tr.addEventListener('click',()=>openReq(tr.dataset.req)));
  box.scrollIntoView({behavior:'smooth',block:'nearest'});
}
function renderReqs(){
  if(!REQS) return;
  const metric = document.getElementById('reqMetric').value;
  const ranked = [...REQS.reqs].sort((a,b)=>n(b[metric])-n(a[metric])).slice(0,15);
  const label = document.querySelector('#reqMetric option:checked').textContent;
  const val = x => metric==='duration_ms' ? Math.round(n(x[metric])/60000) : n(x[metric]);
  renderChart('reqRankChart','bar',{labels:ranked.map(x=>x.req_id),datasets:[{label: metric==='duration_ms' ? 'time (min)' : label,data:ranked.map(val)}]},
    {indexAxis:'y',scales:{x:{beginAtZero:true}}});
  const rows = [...REQS.reqs].sort((a,b)=>{
    const va=a[reqSortKey], vb=b[reqSortKey];
    const c = (typeof va==='string') ? String(va).localeCompare(String(vb)) : n(va)-n(vb);
    return reqSortDir==='asc' ? c : -c;
  });
  document.querySelector('#reqTable tbody').innerHTML = rows.map((x,i)=>`
    <tr class="click" data-req="${esc(x.req_id)}"><td>${i+1}</td><td>${esc(x.req_id)}</td><td>${fmtUSD(x.cost_usd)}</td>
    <td>${fmtDur(x.duration_ms)}</td><td>${fmtDur(x.agent_ms)}</td><td>${fmtDur(x.sandbox_ms)}</td><td>${fmtDur(n(x.span_s)*1000)}</td>
    <td>${x.kit_runs}</td><td>${x.repairs}</td><td>${x.eval_runs}</td><td>${x.eval_failed}</td>
    <td>${esc(x.eval_first||'—')}</td><td>${esc(x.gate||'—')}</td><td>${fmtInt(x.tokens_in)}</td></tr>`).join('');
  document.querySelectorAll('#reqTable tr.click').forEach(tr=>tr.addEventListener('click',()=>openReq(tr.dataset.req)));
}
function openReq(req){
  if(!REQS) return;
  const x = REQS.reqs.find(r=>r.req_id===req); if(!x) return;
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active', t.dataset.tab==='reqs'));
  showTab('reqs');
  document.querySelectorAll('#reqTable tr').forEach(tr=>tr.classList.toggle('sel', tr.dataset.req===req));
  const box = document.getElementById('reqDetail'); box.classList.remove('hidden');
  document.getElementById('reqDetailTitle').textContent =
    `${req} — ${fmtUSD(x.cost_usd)}, ${fmtDur(x.duration_ms)} of work, ${x.repairs} repair(s), ${x.eval_runs} eval(s), gate ${x.gate||'—'}`;
  const phases = Object.keys(x.per_phase||{});
  renderChart('reqDetailChart','bar',{labels:phases,datasets:[{label:'time (min)',data:phases.map(p=>Math.round(n(x.per_phase[p].duration_ms)/60000))}]},
    {scales:{y:{beginAtZero:true}}});
  document.querySelector('#reqDetailTable tbody').innerHTML = phases.map(p=>{ const v=x.per_phase[p]; return `
    <tr><td>${esc(p)}</td><td>${v.runs}</td><td>${fmtDur(v.duration_ms)}</td><td>${fmtUSD(v.cost_usd)}</td>
    <td>${fmtInt(v.tokens_in)}</td><td>${fmtInt(v.tokens_out)}</td><td>${fmtInt(v.tokens_cached)}</td></tr>`; }).join('');
  box.scrollIntoView({behavior:'smooth',block:'nearest'});
}
function renderKpis(){
  if(!REQS) return;
  const k = REQS.kpis||{}; const o = k.other_phases||{};
  const tile = (t,v,sub) => `<div class="kpi"><div class="muted">${t}</div><div class="v">${v}</div><div class="s">${sub||''}</div></div>`;
  document.getElementById('kpiTiles').innerHTML = [
    tile('Requirements measured', k.reqs||0, 'REQ-… with telemetry'),
    tile('Cost per REQ', fmtUSD(k.cost_per_req?.median), `p90 ${fmtUSD(k.cost_per_req?.p90)} · mean ${fmtUSD(k.cost_per_req?.mean)}`),
    tile('Work time per REQ', fmtDur(k.time_per_req_ms?.median), `p90 ${fmtDur(k.time_per_req_ms?.p90)}`),
    tile('Elapsed per REQ', fmtDur(n(k.span_per_req_s?.median)*1000), `first to last run · p90 ${fmtDur(n(k.span_per_req_s?.p90)*1000)}`),
    tile('Repairs per REQ', n(k.repairs_per_req).toFixed(2), 'KIT runs after the first'),
    tile('Eval first-pass rate', fmtPct(k.eval_first_pass_rate), `${n(k.eval_runs_per_req).toFixed(1)} evals per REQ`),
    tile('Gate pass rate', fmtPct(k.gate_pass_rate), 'last gate of each REQ'),
    tile('Prompt cache hit', fmtPct(k.cache_hit_rate), 'cached / input tokens'),
    tile('Agent share of time', fmtPct(k.agent_time_share), 'the rest is eval sandbox'),
    tile('Phases without a REQ', fmtUSD(o.cost_usd), `${o.runs||0} runs · ${fmtDur(o.duration_ms)} (idea, spec, plan, extend, finalize)`),
  ].join('');
}
async function runEstimate(){
  const nReq = Math.max(1, Math.min(1000, Number(document.getElementById('estN').value)||1));
  const d = await loadReqs(nReq);
  const e = d.estimate;
  document.getElementById('estOut').textContent = e
    ? `${e.reqs} REQ(s): cost ${fmtUSD(e.cost_usd.median)} – ${fmtUSD(e.cost_usd.p90)}, work time ${fmtDur(e.time_ms.median)} – ${fmtDur(e.time_ms.p90)} (from ${e.basis_reqs} measured REQs)`
    : 'No measured requirements yet.';
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
      <td class="muted">${esc(r.run_id)}</td>
      <td>${esc(r.phase)}</td>
      <td>${esc(r.model)}</td>
      <td>${esc(r.provider)}</td>
      <td>${fmtUSD((r.pricing?.total_cost) ?? r.cost_usd_est ?? 0)}</td>
      <td>${(r.usage?.prompt_tokens ?? r.usage?.input_tokens ?? 0)}</td>
      <td>${(r.usage?.completion_tokens ?? r.usage?.output_tokens ?? 0)}</td>
      <td>${(r._tokens_cached ?? 0)}</td>
    </tr>`).join('');

  const pages = Math.max(1, Math.ceil((data.total||0) / Number(ps)));
  document.getElementById('pageInfo').textContent = `Page ${data.page||1} / ${pages} — ${data.total||0} rows`;
  document.getElementById('prev').disabled = ((data.page||1)<=1);
  document.getElementById('next').disabled = ((data.page||1)>=pages);
}

function showTab(name){
  ['overview','reqs','kpis','table'].forEach(t=>document.getElementById('tab-'+t).classList.toggle('hidden', t!==name));
}
function activateTabs(){
  const tabs = document.querySelectorAll('.tab');
  tabs.forEach(t => t.addEventListener('click', () => {
    tabs.forEach(x=>x.classList.remove('active')); t.classList.add('active');
    showTab(t.dataset.tab);
    if(t.dataset.tab==='table'){ curPage=1; loadTable(); }
    if(t.dataset.tab==='reqs'){ renderReqs(); }
    if(t.dataset.tab==='kpis'){ renderKpis(); }
  }));
  document.getElementById('reqMetric').addEventListener('change', renderReqs);
  document.getElementById('estGo').addEventListener('click', runEstimate);
  document.querySelectorAll('#reqTable th.sortable').forEach(th=>th.addEventListener('click',()=>{
    const k = th.dataset.k;
    if(reqSortKey===k){ reqSortDir = (reqSortDir==='asc'?'desc':'asc'); } else { reqSortKey=k; reqSortDir = (k==='req_id'?'asc':'desc'); }
    renderReqs();
  }));
}

document.getElementById('refresh').addEventListener('click', async ()=>{
  await loadOverview();
  if(!document.getElementById('tab-table').classList.contains('hidden')) loadTable();
  if(!document.getElementById('tab-reqs').classList.contains('hidden')) renderReqs();
  if(!document.getElementById('tab-kpis').classList.contains('hidden')) renderKpis();
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


_COOKIE_MAX_AGE_S = 8 * 3600


@router.post("/login")
async def login(request: Request) -> Response:
    """Exchange the service token for an HttpOnly, SameSite=Strict cookie (telemetry UI only)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    token = str((body or {}).get("token") or "").strip()
    if not tokens_match(token, configured_token()):
        return JSONResponse({"code": "unauthorized", "detail": "Invalid service token"}, status_code=401)
    resp = Response(status_code=204)
    resp.set_cookie(
        COOKIE_NAME, token, max_age=_COOKIE_MAX_AGE_S, httponly=True, samesite="strict", path="/v1/metrics"
    )
    return resp


@router.post("/logout")
def logout() -> Response:
    resp = Response(status_code=204)
    resp.delete_cookie(COOKIE_NAME, path="/v1/metrics")
    return resp
