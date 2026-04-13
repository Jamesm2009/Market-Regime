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

    # Build a 45-day summary for the prompt
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
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read())

    text = result["content"][0]["text"].strip()
    _commentary_cache["text"] = text
    _commentary_cache["fetched_at"] = now
    return text

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
.sub { font-size:13px; color:var(--muted); margin-bottom:1.5rem; }
.card { background:var(--surface); border:.5px solid var(--border); border-radius:var(--r); padding:1rem 1.25rem; }
.section { margin-bottom:12px; }
.controls { display:flex; align-items:center; gap:20px; flex-wrap:wrap; margin:1.25rem 0; }
.ctrl-group label { font-size:12px; color:var(--muted); display:block; margin-bottom:5px; }
.slider-row { display:flex; align-items:center; gap:8px; }
input[type=range] { -webkit-appearance:none; width:110px; height:4px; background:var(--border-med); border-radius:2px; outline:none; border:none; }
input[type=range]::-webkit-slider-thumb { -webkit-appearance:none; width:16px; height:16px; border-radius:50%; background:var(--blue); cursor:pointer; }
.charts-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:12px; }
.clabel { font-size:12px; color:var(--muted); margin-bottom:10px; }
.chart-wrap { position:relative; width:100%; height:200px; }
.bottom-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:12px; }
.quad-grid { display:grid; grid-template-columns:20px 1fr 1fr; grid-template-rows:20px 1fr 1fr; gap:5px; height:185px; }
.ax { font-size:10px; color:var(--faint); display:flex; align-items:center; justify-content:center; text-align:center; line-height:1.3; }
.ax.vert { writing-mode:vertical-rl; transform:rotate(180deg); }
.quad { display:flex; align-items:center; justify-content:center; text-align:center; border-radius:var(--rs); font-size:12px; font-weight:500; padding:8px 4px; line-height:1.35; opacity:.2; transition:opacity .35s, box-shadow .35s; }
.quad.lit { opacity:1; box-shadow:0 0 0 2px currentColor; }
.q-boom { background:#FAEEDA; color:#633806; }
.q-gold { background:#EAF3DE; color:#27500A; }
.q-stag { background:#FCEBEB; color:#501313; }
.q-bust { background:#E6F1FB; color:#042C53; }
.mcard { background:var(--surface2); border-radius:var(--rs); padding:.875rem 1rem; margin-bottom:10px; }
.mcard:last-child { margin-bottom:0; }
.mlabel { font-size:12px; color:var(--muted); margin-bottom:4px; }
.mval { font-size:24px; font-weight:500; line-height:1; margin-bottom:4px; }
.msub { font-size:12px; color:var(--muted); line-height:1.4; }
.qnote { font-size:11px; color:var(--faint); margin-top:8px; }
#status { font-size:13px; color:var(--muted); margin-bottom:1rem; min-height:18px; }
#status.err { color:#a32d2d; }

/* Regime change banner */
.regime-row { display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:12px; }
.regime-pill { display:inline-flex; align-items:center; gap:6px; padding:5px 12px; border-radius:20px; font-size:12px; font-weight:500; }
.pill-gold  { background:#EAF3DE; color:#27500A; }
.pill-boom  { background:#FAEEDA; color:#633806; }
.pill-stag  { background:#FCEBEB; color:#501313; }
.pill-bust  { background:#E6F1FB; color:#042C53; }
.pill-neutral { background:var(--surface2); color:var(--muted); }
.change-badge { display:inline-flex; align-items:center; gap:5px; padding:4px 10px; border-radius:20px; font-size:11px; font-weight:500; background:#FAEEDA; color:#633806; }
.change-badge.hidden { display:none; }
.arrow { font-size:14px; color:var(--faint); }
.regime-label { font-size:12px; color:var(--muted); }

/* Commentary */
.commentary-card { margin-bottom:12px; }
#commentary-text { font-size:14px; color:var(--text); line-height:1.7; }
#commentary-text.loading { color:var(--muted); font-style:italic; }

/* ETF table */
.etf-section { margin-bottom:12px; }
.etf-header { font-size:13px; font-weight:500; margin-bottom:10px; color:var(--text); }
.etf-cols { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.etf-col-label { font-size:11px; font-weight:500; letter-spacing:.04em; text-transform:uppercase; margin-bottom:8px; }
.etf-col-label.long  { color:#27500A; }
.etf-col-label.short { color:#501313; }
.etf-tags { display:flex; flex-wrap:wrap; gap:5px; }
.etf-tag { font-size:12px; padding:3px 9px; border-radius:4px; font-weight:500; }
.etf-tag.long  { background:#EAF3DE; color:#27500A; }
.etf-tag.short { background:#FCEBEB; color:#501313; }
.etf-desc { font-size:11px; color:var(--faint); margin-top:6px; line-height:1.5; }

@media (max-width:640px) { .charts-grid,.bottom-grid,.etf-cols { grid-template-columns:1fr; } }
</style>
</head>
<body>
<div class="page">

  <h1>US Macro Regime Dashboard</h1>
  <p class="sub" id="fetchedAt">Yield curve (T10Y2Y) + 5Y breakeven inflation (T5YIE) &middot; Loading&hellip;</p>

  <!-- Regime change row -->
  <div class="regime-row" id="regimeRow" style="display:none">
    <span class="regime-label">30d ago:</span>
    <span class="regime-pill pill-neutral" id="pill30d">&hellip;</span>
    <span class="arrow">&rarr;</span>
    <span class="regime-label">Now:</span>
    <span class="regime-pill pill-neutral" id="pillNow">&hellip;</span>
    <span class="change-badge hidden" id="changeBadge">&#9651; Regime change</span>
  </div>

  <p id="status">Fetching data&hellip;</p>

  <!-- Window control -->
  <div class="controls">
    <div class="ctrl-group">
      <label>SMA window: <span id="wout" style="font-weight:500;color:var(--text)">20 days</span></label>
      <div class="slider-row">
        <span style="font-size:12px;color:var(--faint)">5</span>
        <input type="range" id="wslider" min="5" max="90" value="20" step="1" oninput="onWin(this.value)"/>
        <span style="font-size:12px;color:var(--faint)">90</span>
      </div>
    </div>
  </div>

  <!-- Charts -->
  <div class="charts-grid section">
    <div class="card">
      <p class="clabel" id="clabel">Yield curve (10Y&minus;2Y) &mdash; SMA 20d</p>
      <div class="chart-wrap"><canvas id="cChart" role="img" aria-label="Smoothed yield curve signal over time"></canvas></div>
    </div>
    <div class="card">
      <p class="clabel" id="blabel">5Y breakeven inflation &mdash; SMA 20d</p>
      <div class="chart-wrap"><canvas id="bChart" role="img" aria-label="Smoothed 5-year breakeven inflation rate over time"></canvas></div>
    </div>
  </div>

  <!-- Quadrant + signals -->
  <div class="bottom-grid section">
    <div class="card">
      <p class="clabel" style="margin-bottom:8px">Regime quadrant</p>
      <div class="quad-grid">
        <div></div>
        <div class="ax">inflation &uarr;</div>
        <div class="ax">inflation &darr;</div>
        <div class="ax vert">growth &uarr;</div>
        <div class="quad q-boom" id="q-boom">Inflationary<br>boom</div>
        <div class="quad q-gold" id="q-gold">Goldilocks</div>
        <div class="ax vert">growth &darr;</div>
        <div class="quad q-stag" id="q-stag">Stagflation</div>
        <div class="quad q-bust" id="q-bust">Bust /<br>deflation</div>
      </div>
      <p class="qnote" id="qnote">Yield curve vs 0% &middot; breakevens vs 2.5%</p>
    </div>
    <div>
      <div class="mcard">
        <p class="mlabel">Yield curve (10Y&minus;2Y)</p>
        <p class="mval" id="cval">&mdash;</p>
        <p class="msub" id="csub">Loading&hellip;</p>
      </div>
      <div class="mcard">
        <p class="mlabel">5Y breakeven inflation</p>
        <p class="mval" id="bval">&mdash;</p>
        <p class="msub" id="bsub">Loading&hellip;</p>
      </div>
    </div>
  </div>

  <!-- Commentary -->
  <div class="card commentary-card section">
    <p class="clabel" style="margin-bottom:8px">Market conditions (last 30&ndash;45 days)</p>
    <p id="commentary-text" class="loading">Generating commentary&hellip;</p>
  </div>

  <!-- ETF recommendations -->
  <div class="card etf-section section">
    <p class="etf-header" id="etfHeader">ETF positioning &mdash; loading regime&hellip;</p>
    <div class="etf-cols">
      <div>
        <p class="etf-col-label long">Favour (long)</p>
        <div class="etf-tags" id="etfLong"></div>
      </div>
      <div>
        <p class="etf-col-label short">Avoid / underweight (short)</p>
        <div class="etf-tags" id="etfShort"></div>
      </div>
    </div>
    <p class="etf-desc" id="etfDesc"></p>
  </div>

</div>
<script>
// ── ETF regime map ────────────────────────────────────────────────────────────
// Customise these lists with your own 70 ETFs as needed.
const ETF_MAP = {
  goldilocks: {
    label: 'Goldilocks (growth up, inflation down)',
    long:  ['QQQ','VGT','XLK','XLY','IWM','SPY','VUG','HYG','JNK','VNQ','ARKK','XLC','SOXX'],
    short: ['GLD','TIP','PDBC','XLE','XLB','TLT','SHY'],
    desc:  'Risk-on. Equities — especially growth and small-cap — outperform. Credit spreads tight. Real assets and long-duration bonds lag.'
  },
  boom: {
    label: 'Inflationary boom (growth up, inflation up)',
    long:  ['XLE','XLB','GLD','SLV','DJP','PDBC','XME','FCG','VDE','MOO','XLF','IYZ','TIP'],
    short: ['TLT','IEF','LQD','XLK','ARKK','VNQ'],
    desc:  'Cyclicals and real assets lead. Energy, materials and financials outperform. Long-duration bonds and rate-sensitive growth stocks lag.'
  },
  stagflation: {
    label: 'Stagflation (growth down, inflation up)',
    long:  ['GLD','SLV','TIP','PDBC','XLE','XLU','VPU','USMV','NOBL','MINT'],
    short: ['SPY','QQQ','IWM','HYG','JNK','XLY','LQD','XLB'],
    desc:  'Hardest regime for equities and credit. Real assets, defensives and short-duration inflation-linkers are the primary shelter.'
  },
  bust: {
    label: 'Bust / deflation (growth down, inflation down)',
    long:  ['TLT','IEF','SHY','GLD','XLU','VPU','USMV','NOBL','SPHD','BIL'],
    short: ['XLE','XLB','HYG','JNK','IWM','XLY','PDBC','SLV'],
    desc:  'Flight to safety. Long-duration Treasuries and defensive equities outperform. Risk assets and commodities under pressure.'
  }
};

// ── State ─────────────────────────────────────────────────────────────────────
let RAW_CURVE=[], RAW_BEI=[], win=20, cInst=null, bInst=null;

function onWin(v){
  win=parseInt(v);
  document.getElementById('wout').textContent=v+' days';
  render();
}

// ── Smoothing (SMA only) ──────────────────────────────────────────────────────
function sma(data,w){
  return data.map((_,i)=>{
    if(i<w-1) return null;
    const sl=data.slice(i-w+1,i+1);
    return sl.reduce((s,x)=>s+x.value,0)/w;
  });
}

// ── Regime classification ─────────────────────────────────────────────────────
function classifyRegime(curveVal, beiVal){
  const growthUp = curveVal > 0;
  const inflUp   = beiVal   > 2.5;
  if (growthUp  && inflUp)  return 'boom';
  if (growthUp  && !inflUp) return 'goldilocks';
  if (!growthUp && inflUp)  return 'stagflation';
  return 'bust';
}

const REGIME_PILL_CLASS = {
  goldilocks:  'pill-gold',
  boom:        'pill-boom',
  stagflation: 'pill-stag',
  bust:        'pill-bust'
};
const REGIME_LABEL = {
  goldilocks:  'Goldilocks',
  boom:        'Inflationary boom',
  stagflation: 'Stagflation',
  bust:        'Bust / deflation'
};

// ── Chart helper ──────────────────────────────────────────────────────────────
function isDark(){ return matchMedia('(prefers-color-scheme:dark)').matches; }

function makeChart(id,labels,smoothed,raw,hexL,hexD){
  const dark=isDark(), hex=dark?hexD:hexL;
  const gridC=dark?'rgba(255,255,255,0.07)':'rgba(0,0,0,0.06)';
  const tickC='#6b6a65';
  const rawC=dark?'rgba(255,255,255,0.08)':'rgba(0,0,0,0.07)';
  const ctx=document.getElementById(id).getContext('2d');
  return new Chart(ctx,{
    type:'line',
    data:{labels,datasets:[
      {label:'Raw',     data:raw,     borderColor:rawC, borderWidth:1,   pointRadius:0, tension:0,    spanGaps:false},
      {label:'SMA',     data:smoothed,borderColor:hex,  borderWidth:2.5, pointRadius:0, tension:0.15, spanGaps:false}
    ]},
    options:{
      responsive:true, maintainAspectRatio:false, animation:false,
      plugins:{
        legend:{display:false},
        tooltip:{mode:'index',intersect:false,callbacks:{label:c=>{
          const v=c.parsed.y;
          if(v===null) return null;
          return c.dataset.label+': '+v.toFixed(2)+'%';
        }}}
      },
      scales:{
        x:{ticks:{color:tickC,font:{size:11},maxTicksLimit:6,
             callback:function(val,i){const l=labels[i];return l?l.slice(0,7):'';} },
           grid:{color:gridC}},
        y:{ticks:{color:tickC,font:{size:11},maxTicksLimit:5,callback:v=>v.toFixed(1)},
           grid:{color:gridC}}
      }
    }
  });
}

// ── ETF panel ─────────────────────────────────────────────────────────────────
function updateETFs(regime){
  const r = ETF_MAP[regime];
  if(!r) return;
  document.getElementById('etfHeader').textContent = 'ETF positioning \u2014 ' + REGIME_LABEL[regime];
  const longEl  = document.getElementById('etfLong');
  const shortEl = document.getElementById('etfShort');
  longEl.innerHTML  = r.long.map(t=>`<span class="etf-tag long">${t}</span>`).join('');
  shortEl.innerHTML = r.short.map(t=>`<span class="etf-tag short">${t}</span>`).join('');
  document.getElementById('etfDesc').textContent = r.desc;
}

// ── Main render ───────────────────────────────────────────────────────────────
function render(){
  if(!RAW_CURVE.length||!RAW_BEI.length) return;

  // Align dates
  const bDates=new Set(RAW_BEI.map(d=>d.date));
  const cA=RAW_CURVE.filter(d=>bDates.has(d.date));
  const cDates=new Set(cA.map(d=>d.date));
  const bA=RAW_BEI.filter(d=>cDates.has(d.date));

  const labels   = cA.map(d=>d.date);
  const cSmooth  = sma(cA, win);
  const bSmooth  = sma(bA, win);
  const cRaw     = cA.map(d=>d.value);
  const bRaw     = bA.map(d=>d.value);

  // Update chart labels
  document.getElementById('clabel').textContent = 'Yield curve (10Y\u22122Y) \u2014 SMA '+win+'d';
  document.getElementById('blabel').textContent = '5Y breakeven inflation \u2014 SMA '+win+'d';

  // Rebuild charts
  if(cInst){cInst.destroy();cInst=null;}
  if(bInst){bInst.destroy();bInst=null;}
  cInst = makeChart('cChart',labels,cSmooth,cRaw,'#185FA5','#85B7EB');
  bInst = makeChart('bChart',labels,bSmooth,bRaw,'#993C1D','#F0997B');

  // Current smoothed values
  const lastC = [...cSmooth].reverse().find(v=>v!==null&&v!==undefined);
  const lastB = [...bSmooth].reverse().find(v=>v!==null&&v!==undefined);
  if(lastC===undefined||lastB===undefined) return;

  // Signal cards
  document.getElementById('cval').textContent = lastC.toFixed(2)+'%';
  document.getElementById('bval').textContent = lastB.toFixed(2)+'%';
  document.getElementById('csub').textContent = lastC>0
    ? 'Curve positive \u2192 expansionary growth signal'
    : 'Curve inverted \u2192 contraction signal';
  document.getElementById('bsub').textContent = lastB>2.5
    ? 'Above 2.5% \u2192 elevated inflation expectations'
    : 'At or below 2.5% \u2192 relatively contained';

  // Current regime
  const nowRegime = classifyRegime(lastC, lastB);
  ['q-boom','q-gold','q-stag','q-bust'].forEach(id=>document.getElementById(id).classList.remove('lit'));
  const qMap = {boom:'q-boom',goldilocks:'q-gold',stagflation:'q-stag',bust:'q-bust'};
  document.getElementById(qMap[nowRegime]).classList.add('lit');

  // 30-day-ago regime — look back ~30 data points in smoothed array
  const validIdx = cSmooth.map((v,i)=>v!==null?i:-1).filter(i=>i>=0);
  const nowIdx   = validIdx[validIdx.length-1];
  const ago30Idx = validIdx[Math.max(0, validIdx.length-31)]; // 30 steps back
  const c30 = cSmooth[ago30Idx];
  const b30 = bSmooth[ago30Idx];
  const agoRegime = (c30!==null&&b30!==null) ? classifyRegime(c30,b30) : nowRegime;

  // Update regime row
  const pill30 = document.getElementById('pill30d');
  const pillNow = document.getElementById('pillNow');
  const badge   = document.getElementById('changeBadge');
  pill30.textContent  = REGIME_LABEL[agoRegime];
  pillNow.textContent = REGIME_LABEL[nowRegime];
  pill30.className  = 'regime-pill ' + REGIME_PILL_CLASS[agoRegime];
  pillNow.className = 'regime-pill ' + REGIME_PILL_CLASS[nowRegime];
  document.getElementById('regimeRow').style.display = 'flex';

  if(nowRegime !== agoRegime){
    badge.classList.remove('hidden');
  } else {
    badge.classList.add('hidden');
  }

  // ETF panel
  updateETFs(nowRegime);
}

// ── Load data ─────────────────────────────────────────────────────────────────
fetch('/api/data')
  .then(r=>r.json())
  .then(d=>{
    if(d.error){setStatus(d.error,'err');return;}
    RAW_CURVE = d.curve;
    RAW_BEI   = d.bei;
    document.getElementById('fetchedAt').textContent =
      'Yield curve (T10Y2Y) + 5Y breakeven inflation (T5YIE) \u00b7 Data as of '+d.fetched_at;
    setStatus('','');
    render();
  })
  .catch(e=>setStatus('Could not reach server: '+e.message,'err'));

// ── Load commentary ───────────────────────────────────────────────────────────
fetch('/api/commentary')
  .then(r=>r.json())
  .then(d=>{
    const el = document.getElementById('commentary-text');
    el.classList.remove('loading');
    if(d.error||!d.commentary){
      el.textContent = d.error||'Commentary unavailable (add ANTHROPIC_API_KEY to enable).';
      el.style.color = 'var(--faint)';
    } else {
      el.textContent = d.commentary;
    }
  })
  .catch(()=>{
    const el = document.getElementById('commentary-text');
    el.classList.remove('loading');
    el.textContent = 'Commentary unavailable.';
    el.style.color = 'var(--faint)';
  });

function setStatus(msg,cls){
  const el=document.getElementById('status');
  el.textContent=msg; el.className=cls;
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
        return jsonify({"error": f"FRED returned HTTP {e.code}. Check your API key."}), 502
    except Exception as e:
        return jsonify({"error": f"Failed to fetch data: {e}"}), 502

@app.route("/api/commentary")
def api_commentary():
    try:
        text = get_commentary()
        if text is None:
            return jsonify({"commentary": None,
                            "error": "Add ANTHROPIC_API_KEY env var to enable commentary."})
        return jsonify({"commentary": text})
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
