import os
import time
import json
import urllib.request
import urllib.error
from flask import Flask, jsonify

app = Flask(__name__)

# ── Cache ─────────────────────────────────────────────────────────────────────
_cache = {"data": None, "fetched_at": 0}
_commentary_cache = {"text": None, "fetched_at": 0}
CACHE_TTL      = 4 * 60 * 60
COMMENTARY_TTL = 6 * 60 * 60

FRED_API_KEY      = os.environ.get("FRED_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
START_DATE        = "2019-01-01"

# ── FRED fetch ────────────────────────────────────────────────────────────────

def fetch_series(series_id):
    if not FRED_API_KEY:
        raise ValueError("FRED_API_KEY environment variable is not set.")
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}"
        f"&api_key={FRED_API_KEY}"
        f"&observation_start={START_DATE}"
        "&sort_order=asc&file_type=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "macro-regime-dashboard/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"FRED HTTP {e.code} for {series_id}: {body[:300]}")
    if "error_message" in data:
        raise ValueError(f"FRED error: {data['error_message']}")
    return [
        {"date": o["date"], "value": float(o["value"])}
        for o in data["observations"]
        if o["value"] != "."
    ]

def get_data():
    now = time.time()
    if _cache["data"] and (now - _cache["fetched_at"]) < CACHE_TTL:
        return _cache["data"]
    curve = fetch_series("T10Y2Y")
    bei   = fetch_series("T5YIE")
    _cache["data"] = {
        "curve": curve,
        "bei":   bei,
        "fetched_at": time.strftime("%B %d, %Y at %H:%M UTC", time.gmtime()),
    }
    _cache["fetched_at"] = now
    return _cache["data"]

# ── Anthropic commentary ──────────────────────────────────────────────────────

def get_commentary():
    now = time.time()
    if _commentary_cache["text"] and (now - _commentary_cache["fetched_at"]) < COMMENTARY_TTL:
        return _commentary_cache["text"]
    if not ANTHROPIC_API_KEY:
        return None

    data  = get_data()
    curve = data["curve"]
    bei   = data["bei"]

    c45 = curve[-45:] if len(curve) >= 45 else curve
    b45 = bei[-45:]   if len(bei)   >= 45 else bei

    def fmt(series):
        step = max(1, len(series) // 6)
        return ", ".join(f"{d['date']}: {d['value']:.2f}%" for d in series[::step][-6:])

    prompt = (
        "You are a concise macro analyst. Based on the following recent FRED data, "
        "write exactly 3 sentences summarising current US macro conditions and what "
        "they imply for markets. Be direct and specific — no preamble, no sign-off.\n\n"
        f"10Y-2Y Yield Curve (last ~45 trading days, sampled):\n{fmt(c45)}\n"
        f"Latest: {curve[-1]['date']} = {curve[-1]['value']:.2f}%\n\n"
        f"5Y Breakeven Inflation (last ~45 trading days, sampled):\n{fmt(b45)}\n"
        f"Latest: {bei[-1]['date']} = {bei[-1]['value']:.2f}%\n\n"
        f"45-day change — Curve: {curve[-1]['value'] - c45[0]['value']:+.2f}%, "
        f"Breakevens: {bei[-1]['value'] - b45[0]['value']:+.2f}%"
    )

    body = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        }
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                result = json.loads(r.read())
            text = result["content"][0]["text"].strip()
            _commentary_cache["text"] = text
            _commentary_cache["fetched_at"] = now
            return text
        except urllib.error.HTTPError as e:
            if e.code == 529:
                time.sleep(3 * (attempt + 1))
                continue
            err_body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Anthropic API error {e.code}: {err_body[:200]}")

    raise RuntimeError("Anthropic API overloaded after 3 retries.")

# ── HTML ──────────────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>US Macro Regime Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
:root {
  --bg:#f7f6f3; --surface:#ffffff; --surface2:#f0efe9;
  --border:rgba(0,0,0,0.10); --border-med:rgba(0,0,0,0.18);
  --text:#1a1917; --muted:#6b6a65; --faint:#9b9a96;
  --blue:#185FA5; --coral:#993C1D;
  --r:10px; --rs:6px;
}
@media (prefers-color-scheme:dark) {
  :root {
    --bg:#1a1917; --surface:#242320; --surface2:#2e2d29;
    --border:rgba(255,255,255,0.09); --border-med:rgba(255,255,255,0.18);
    --text:#f0efe9; --muted:#9b9a96; --faint:#6b6a65;
    --blue:#85B7EB; --coral:#F0997B;
  }
}
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:var(--bg); color:var(--text); min-height:100vh; padding:2rem 1.5rem; }
.page { max-width:960px; margin:0 auto; }
h1 { font-size:18px; font-weight:500; letter-spacing:-.3px; margin-bottom:4px; }
.sub { font-size:13px; color:var(--muted); margin-bottom:1rem; }
.card { background:var(--surface); border:.5px solid var(--border); border-radius:var(--r); padding:1rem 1.25rem; }
.section { margin-bottom:12px; }

/* Regime row */
.regime-row { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:10px; }
.regime-pill { display:inline-flex; align-items:center; padding:4px 12px; border-radius:20px; font-size:12px; font-weight:500; }
.pill-gold  { background:#EAF3DE; color:#27500A; }
.pill-boom  { background:#FAEEDA; color:#633806; }
.pill-stag  { background:#FCEBEB; color:#501313; }
.pill-bust  { background:#E6F1FB; color:#042C53; }
.pill-neutral { background:var(--surface2); color:var(--muted); }
.change-badge { display:inline-flex; align-items:center; gap:4px; padding:4px 10px; border-radius:20px; font-size:11px; font-weight:500; background:#FAEEDA; color:#633806; }
.change-badge.hidden { display:none; }
.regime-sep { font-size:14px; color:var(--faint); }
.regime-lbl { font-size:12px; color:var(--muted); }

/* Commentary */
.commentary-card { margin-bottom:12px; }
.commentary-top { display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }
.commentary-label { font-size:12px; color:var(--muted); }
#commentary-text { font-size:13px; color:var(--text); line-height:1.7; }
#commentary-text.loading { color:var(--muted); font-style:italic; }
#commentary-text.err { color:var(--faint); font-style:italic; }
.retry-btn { height:28px; padding:0 12px; border:.5px solid var(--border-med); border-radius:var(--rs); background:var(--surface2); color:var(--muted); font-size:12px; cursor:pointer; }
.retry-btn:hover { color:var(--text); }

/* SMA controls */
.controls { display:flex; align-items:center; gap:16px; margin-bottom:12px; }
.ctrl-group label { font-size:12px; color:var(--muted); display:block; margin-bottom:4px; }
.slider-row { display:flex; align-items:center; gap:8px; }
input[type=range] { -webkit-appearance:none; width:110px; height:4px; background:var(--border-med); border-radius:2px; outline:none; border:none; }
input[type=range]::-webkit-slider-thumb { -webkit-appearance:none; width:16px; height:16px; border-radius:50%; background:var(--blue); cursor:pointer; }

/* Charts */
.charts-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:12px; }
.chart-card { background:var(--surface); border:.5px solid var(--border); border-radius:var(--r); padding:1rem 1.25rem 0.75rem; }
.clabel { font-size:12px; color:var(--muted); margin-bottom:8px; }
.chart-wrap { position:relative; width:100%; height:185px; }

/* Signal strip under each chart */
.signal-strip { display:flex; align-items:baseline; gap:10px; padding-top:10px; border-top:.5px solid var(--border); margin-top:10px; }
.sig-val { font-size:20px; font-weight:500; color:var(--text); }
.sig-sub { font-size:11px; color:var(--muted); line-height:1.4; }

/* Bottom grid: quadrant + ETFs */
.bottom-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }

/* Quadrant */
.quad-grid { display:grid; grid-template-columns:18px 1fr 1fr; grid-template-rows:20px 1fr 1fr; gap:4px; height:180px; margin-bottom:6px; }
.ax { font-size:10px; font-weight:700; color:var(--text); display:flex; align-items:center; justify-content:center; text-align:center; line-height:1.3; }
.ax.vert { writing-mode:vertical-rl; transform:rotate(180deg); }
.quad { display:flex; align-items:center; justify-content:center; text-align:center; border-radius:var(--rs); font-size:12px; font-weight:500; padding:6px 4px; line-height:1.35; opacity:.2; transition:opacity .35s, box-shadow .35s; }
.quad.lit { opacity:1; box-shadow:0 0 0 2px currentColor; }
.q-boom { background:#FAEEDA; color:#633806; }
.q-gold { background:#EAF3DE; color:#27500A; }
.q-stag { background:#FCEBEB; color:#501313; }
.q-bust { background:#E6F1FB; color:#042C53; }
.qnote { font-size:10px; color:var(--faint); }

/* ETF panel */
.etf-panel { display:flex; flex-direction:column; gap:10px; }
.etf-block-label { font-size:11px; font-weight:500; letter-spacing:.04em; text-transform:uppercase; margin-bottom:6px; }
.etf-block-label.long  { color:#27500A; }
.etf-block-label.short { color:#501313; }
.etf-tags { display:flex; flex-wrap:wrap; gap:4px; }
.etf-tag { font-size:11px; padding:2px 8px; border-radius:4px; font-weight:500; }
.etf-tag.long  { background:#EAF3DE; color:#27500A; }
.etf-tag.short { background:#FCEBEB; color:#501313; }
.etf-header { font-size:12px; color:var(--muted); margin-bottom:8px; }
.etf-desc { font-size:11px; color:var(--faint); line-height:1.5; margin-top:8px; padding-top:8px; border-top:.5px solid var(--border); }

#status { font-size:13px; color:var(--muted); min-height:16px; margin-bottom:8px; }
#status.err { color:#a32d2d; }

@media (max-width:640px) { .charts-grid,.bottom-grid { grid-template-columns:1fr; } }
</style>
</head>
<body>
<div class="page">

  <h1>US Macro Regime Dashboard</h1>
  <p class="sub" id="fetchedAt">Yield curve (T10Y2Y) + 5Y breakeven inflation (T5YIE) &middot; Loading&hellip;</p>

  <!-- Regime change row -->
  <div class="regime-row" id="regimeRow" style="display:none">
    <span class="regime-lbl">30d ago:</span>
    <span class="regime-pill pill-neutral" id="pill30d">&hellip;</span>
    <span class="regime-sep">&rarr;</span>
    <span class="regime-lbl">Now:</span>
    <span class="regime-pill pill-neutral" id="pillNow">&hellip;</span>
    <span class="change-badge hidden" id="changeBadge">&#9651; Regime change</span>
  </div>

  <!-- Commentary (moved here, above SMA slider) -->
  <div class="card commentary-card section">
    <div class="commentary-top">
      <span class="commentary-label">Market conditions (last 30&ndash;45 days)</span>
      <button class="retry-btn" id="retryBtn" onclick="loadCommentary(true)" style="display:none">Retry &uarr;</button>
    </div>
    <p id="commentary-text" class="loading">Loading commentary&hellip;</p>
  </div>

  <!-- SMA slider -->
  <div class="controls section">
    <div class="ctrl-group">
      <label>SMA window: <span id="wout" style="font-weight:500;color:var(--text)">20 days</span></label>
      <div class="slider-row">
        <span style="font-size:12px;color:var(--faint)">5</span>
        <input type="range" id="wslider" min="5" max="90" value="20" step="1" oninput="onWin(this.value)"/>
        <span style="font-size:12px;color:var(--faint)">90</span>
      </div>
    </div>
  </div>

  <p id="status"></p>

  <!-- Charts with signal strip underneath each -->
  <div class="charts-grid section">
    <div class="chart-card">
      <p class="clabel" id="clabel">Yield curve (10Y&minus;2Y) &mdash; SMA 20d</p>
      <div class="chart-wrap"><canvas id="cChart" role="img" aria-label="Smoothed yield curve signal over time"></canvas></div>
      <div class="signal-strip">
        <span class="sig-val" id="cval">&mdash;</span>
        <span class="sig-sub" id="csub">Loading&hellip;</span>
      </div>
    </div>
    <div class="chart-card">
      <p class="clabel" id="blabel">5Y breakeven inflation &mdash; SMA 20d</p>
      <div class="chart-wrap"><canvas id="bChart" role="img" aria-label="Smoothed 5-year breakeven inflation over time"></canvas></div>
      <div class="signal-strip">
        <span class="sig-val" id="bval">&mdash;</span>
        <span class="sig-sub" id="bsub">Loading&hellip;</span>
      </div>
    </div>
  </div>

  <!-- Quadrant + ETF side by side -->
  <div class="bottom-grid section">
    <div class="card">
      <p class="clabel" style="margin-bottom:8px">Regime quadrant</p>
      <div class="quad-grid">
        <div></div>
        <div class="ax">Inflation &uarr;</div>
        <div class="ax">Inflation &darr;</div>
        <div class="ax vert">Growth &uarr;</div>
        <div class="quad q-boom" id="q-boom">Inflationary<br>boom</div>
        <div class="quad q-gold" id="q-gold">Goldilocks</div>
        <div class="ax vert">Growth &darr;</div>
        <div class="quad q-stag" id="q-stag">Stagflation</div>
        <div class="quad q-bust" id="q-bust">Bust /<br>deflation</div>
      </div>
      <p class="qnote">Yield curve vs 0% &middot; breakevens vs 2.5%</p>
    </div>

    <div class="card">
      <p class="etf-header" id="etfHeader">ETF positioning &mdash; loading&hellip;</p>
      <div class="etf-panel">
        <div>
          <p class="etf-block-label long">Favour / long</p>
          <div class="etf-tags" id="etfLong"></div>
        </div>
        <div>
          <p class="etf-block-label short">Avoid / underweight</p>
          <div class="etf-tags" id="etfShort"></div>
        </div>
      </div>
      <p class="etf-desc" id="etfDesc"></p>
    </div>
  </div>

</div>
<script>
// ── ETF regime map ────────────────────────────────────────────────────────────
const ETF_MAP = {
  goldilocks: {
    label: 'Goldilocks',
    long:  ['QQQ','VGT','XLK','XLY','IWM','SPY','VUG','HYG','JNK','VNQ','ARKK','XLC','SOXX'],
    short: ['GLD','TIP','PDBC','XLE','XLB','TLT','SHY'],
    desc:  'Risk-on. Equities — especially growth and small-cap — outperform. Credit spreads tight. Real assets and long-duration bonds lag.'
  },
  boom: {
    label: 'Inflationary boom',
    long:  ['XLE','XLB','GLD','SLV','DJP','PDBC','XME','FCG','VDE','MOO','XLF','IYZ','TIP'],
    short: ['TLT','IEF','LQD','XLK','ARKK','VNQ'],
    desc:  'Cyclicals and real assets lead. Energy, materials, financials outperform. Long-duration bonds and rate-sensitive growth stocks lag.'
  },
  stagflation: {
    label: 'Stagflation',
    long:  ['GLD','SLV','TIP','PDBC','XLE','XLU','VPU','USMV','NOBL','MINT'],
    short: ['SPY','QQQ','IWM','HYG','JNK','XLY','LQD','XLB'],
    desc:  'Hardest regime for equities and credit. Real assets, defensives and short-duration inflation-linkers are the primary shelter.'
  },
  bust: {
    label: 'Bust / deflation',
    long:  ['TLT','IEF','SHY','GLD','XLU','VPU','USMV','NOBL','SPHD','BIL'],
    short: ['XLE','XLB','HYG','JNK','IWM','XLY','PDBC','SLV'],
    desc:  'Flight to safety. Long-duration Treasuries and defensive equities outperform. Risk assets and commodities under pressure.'
  }
};

const REGIME_PILL = { goldilocks:'pill-gold', boom:'pill-boom', stagflation:'pill-stag', bust:'pill-bust' };
const REGIME_LABEL = { goldilocks:'Goldilocks', boom:'Inflationary boom', stagflation:'Stagflation', bust:'Bust / deflation' };

let RAW_CURVE=[], RAW_BEI=[], win=20, cInst=null, bInst=null;

function onWin(v){ win=parseInt(v); document.getElementById('wout').textContent=v+' days'; render(); }

function sma(data,w){
  return data.map((_,i)=>{
    if(i<w-1) return null;
    const sl=data.slice(i-w+1,i+1);
    return sl.reduce((s,x)=>s+x.value,0)/w;
  });
}

function classifyRegime(c,b){ return c>0 ? (b>2.5?'boom':'goldilocks') : (b>2.5?'stagflation':'bust'); }

function isDark(){ return matchMedia('(prefers-color-scheme:dark)').matches; }

function makeChart(id,labels,smoothed,raw,hexL,hexD){
  const dark=isDark(), hex=dark?hexD:hexL;
  const gridC=dark?'rgba(255,255,255,0.07)':'rgba(0,0,0,0.06)';
  const rawC=dark?'rgba(255,255,255,0.08)':'rgba(0,0,0,0.07)';
  const ctx=document.getElementById(id).getContext('2d');
  return new Chart(ctx,{
    type:'line',
    data:{labels,datasets:[
      {label:'Raw',data:raw,borderColor:rawC,borderWidth:1,pointRadius:0,tension:0,spanGaps:false},
      {label:'SMA',data:smoothed,borderColor:hex,borderWidth:2.5,pointRadius:0,tension:0.15,spanGaps:false}
    ]},
    options:{
      responsive:true,maintainAspectRatio:false,animation:false,
      plugins:{legend:{display:false},tooltip:{mode:'index',intersect:false,callbacks:{label:c=>{
        const v=c.parsed.y; if(v===null) return null;
        return c.dataset.label+': '+v.toFixed(2)+'%';
      }}}},
      scales:{
        x:{ticks:{color:'#6b6a65',font:{size:11},maxTicksLimit:6,callback:function(val,i){const l=labels[i];return l?l.slice(0,7):'';} },grid:{color:gridC}},
        y:{ticks:{color:'#6b6a65',font:{size:11},maxTicksLimit:5,callback:v=>v.toFixed(1)},grid:{color:gridC}}
      }
    }
  });
}

function render(){
  if(!RAW_CURVE.length||!RAW_BEI.length) return;
  const bDates=new Set(RAW_BEI.map(d=>d.date));
  const cA=RAW_CURVE.filter(d=>bDates.has(d.date));
  const cDates=new Set(cA.map(d=>d.date));
  const bA=RAW_BEI.filter(d=>cDates.has(d.date));
  const labels=cA.map(d=>d.date);
  const cSmooth=sma(cA,win), bSmooth=sma(bA,win);

  document.getElementById('clabel').textContent='Yield curve (10Y\u22122Y) \u2014 SMA '+win+'d';
  document.getElementById('blabel').textContent='5Y breakeven inflation \u2014 SMA '+win+'d';

  if(cInst){cInst.destroy();cInst=null;}
  if(bInst){bInst.destroy();bInst=null;}
  cInst=makeChart('cChart',labels,cSmooth,cA.map(d=>d.value),'#185FA5','#85B7EB');
  bInst=makeChart('bChart',labels,bSmooth,bA.map(d=>d.value),'#993C1D','#F0997B');

  const lastC=[...cSmooth].reverse().find(v=>v!==null&&v!==undefined);
  const lastB=[...bSmooth].reverse().find(v=>v!==null&&v!==undefined);
  if(lastC===undefined||lastB===undefined) return;

  // Signal strips under charts
  document.getElementById('cval').textContent=lastC.toFixed(2)+'%';
  document.getElementById('bval').textContent=lastB.toFixed(2)+'%';
  document.getElementById('csub').textContent=lastC>0?'Curve positive \u2192 expansionary growth signal':'Curve inverted \u2192 contraction signal';
  document.getElementById('bsub').textContent=lastB>2.5?'Above 2.5% \u2192 elevated inflation expectations':'At or below 2.5% \u2192 relatively contained';

  // Current regime
  const nowRegime=classifyRegime(lastC,lastB);
  ['q-boom','q-gold','q-stag','q-bust'].forEach(id=>document.getElementById(id).classList.remove('lit'));
  const qMap={boom:'q-boom',goldilocks:'q-gold',stagflation:'q-stag',bust:'q-bust'};
  document.getElementById(qMap[nowRegime]).classList.add('lit');

  // 30d ago regime
  const valid=cSmooth.map((v,i)=>v!==null?i:-1).filter(i=>i>=0);
  const ago30i=valid[Math.max(0,valid.length-31)];
  const agoRegime=(cSmooth[ago30i]!==null&&bSmooth[ago30i]!==null)?classifyRegime(cSmooth[ago30i],bSmooth[ago30i]):nowRegime;

  const pill30=document.getElementById('pill30d');
  const pillNow=document.getElementById('pillNow');
  const badge=document.getElementById('changeBadge');
  pill30.textContent=REGIME_LABEL[agoRegime];   pill30.className='regime-pill '+REGIME_PILL[agoRegime];
  pillNow.textContent=REGIME_LABEL[nowRegime];  pillNow.className='regime-pill '+REGIME_PILL[nowRegime];
  document.getElementById('regimeRow').style.display='flex';
  nowRegime!==agoRegime ? badge.classList.remove('hidden') : badge.classList.add('hidden');

  // ETFs
  const r=ETF_MAP[nowRegime];
  document.getElementById('etfHeader').textContent='ETF positioning \u2014 '+REGIME_LABEL[nowRegime];
  document.getElementById('etfLong').innerHTML=r.long.map(t=>`<span class="etf-tag long">${t}</span>`).join('');
  document.getElementById('etfShort').innerHTML=r.short.map(t=>`<span class="etf-tag short">${t}</span>`).join('');
  document.getElementById('etfDesc').textContent=r.desc;
}

// ── Data load ─────────────────────────────────────────────────────────────────
fetch('/api/data')
  .then(r=>r.json())
  .then(d=>{
    if(d.error){setStatus(d.error,'err');return;}
    RAW_CURVE=d.curve; RAW_BEI=d.bei;
    document.getElementById('fetchedAt').textContent=
      'Yield curve (T10Y2Y) + 5Y breakeven inflation (T5YIE) \u00b7 Data as of '+d.fetched_at;
    setStatus('','');
    render();
  })
  .catch(e=>setStatus('Could not reach server: '+e.message,'err'));

// ── Commentary load (with retry button) ───────────────────────────────────────
function loadCommentary(forceRetry){
  const el=document.getElementById('commentary-text');
  const btn=document.getElementById('retryBtn');
  el.className='loading'; el.textContent='Loading commentary\u2026'; btn.style.display='none';

  const url=forceRetry?'/api/commentary?bust='+Date.now():'/api/commentary';
  fetch(url)
    .then(r=>r.json())
    .then(d=>{
      el.className='';
      if(d.error||!d.commentary){
        el.className='err';
        el.textContent=d.error||'Commentary unavailable (add ANTHROPIC_API_KEY to enable).';
        if(d.error&&d.error.includes('overloaded')) btn.style.display='inline-block';
      } else {
        el.textContent=d.commentary;
      }
    })
    .catch(()=>{
      el.className='err';
      el.textContent='Commentary unavailable.';
      btn.style.display='inline-block';
    });
}

loadCommentary(false);

function setStatus(msg,cls){
  const el=document.getElementById('status'); el.textContent=msg; el.className=cls;
}
</script>
</body>
</html>"""

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return HTML, 200, {"Content-Type": "text/html; charset=utf-8"}

@app.route("/api/data")
def api_data():
    try:
        return jsonify(get_data())
    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    except urllib.error.HTTPError as e:
        return jsonify({"error": f"FRED returned HTTP {e.code}."}), 502
    except Exception as e:
        return jsonify({"error": f"Failed to fetch data: {e}"}), 502

@app.route("/api/commentary")
def api_commentary():
    # bust= param is ignored but forces a fresh request past browser cache
    try:
        text = get_commentary()
        if text is None:
            return jsonify({"commentary": None,
                            "error": "Add ANTHROPIC_API_KEY env var to enable commentary."})
        return jsonify({"commentary": text})
    except RuntimeError as e:
        msg = str(e)
        return jsonify({"commentary": None,
                        "error": msg + (" API is overloaded" if "529" in msg or "overloaded" in msg else "")}), 500
    except Exception as e:
        return jsonify({"commentary": None, "error": str(e)}), 500

@app.route("/api/refresh")
def api_refresh():
    _cache["data"] = None
    _cache["fetched_at"] = 0
    _commentary_cache["text"] = None
    _commentary_cache["fetched_at"] = 0
    try:
        get_data()
        return jsonify({"status": "ok", "fetched_at": _cache["data"]["fetched_at"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 502

if __name__ == "__main__":
    app.run(debug=True)
