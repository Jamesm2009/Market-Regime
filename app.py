import os
import time
import json
import urllib.request
import urllib.error
from flask import Flask, jsonify

app = Flask(__name__)

# ── Cache (4-hour TTL) ────────────────────────────────────────────────────────
_cache = {"data": None, "fetched_at": 0}
CACHE_TTL    = 4 * 60 * 60
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
START_DATE   = "2019-01-01"

# ── FRED fetch ────────────────────────────────────────────────────────────────

def fetch_series(series_id):
    if not FRED_API_KEY:
        raise ValueError("FRED_API_KEY environment variable is not set.")
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}"
        f"&api_key={FRED_API_KEY}"
        f"&observation_start={START_DATE}"
        "&sort_order=asc"
        "&file_type=json"
    )
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read())
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

# ── HTML (inline — no templates folder needed) ────────────────────────────────

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
.controls { display:flex; align-items:center; gap:20px; flex-wrap:wrap; margin:1.25rem 0; }
.ctrl-group label { font-size:12px; color:var(--muted); display:block; margin-bottom:5px; }
.btn-group { display:flex; gap:4px; }
button { height:36px; padding:0 16px; border:.5px solid var(--border-med); border-radius:var(--rs); background:var(--surface); color:var(--text); font-size:13px; cursor:pointer; transition:background .15s; }
button:hover { background:var(--surface2); }
button:active { transform:scale(.98); }
.tbtn { background:transparent; color:var(--muted); }
.tbtn.on { background:var(--surface); color:var(--text); border-color:var(--border-med); font-weight:500; }
.slider-row { display:flex; align-items:center; gap:8px; }
input[type=range] { -webkit-appearance:none; width:110px; height:4px; background:var(--border-med); border-radius:2px; outline:none; border:none; }
input[type=range]::-webkit-slider-thumb { -webkit-appearance:none; width:16px; height:16px; border-radius:50%; background:var(--blue); cursor:pointer; }
.charts-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:12px; }
.clabel { font-size:12px; color:var(--muted); margin-bottom:10px; }
.chart-wrap { position:relative; width:100%; height:200px; }
.bottom-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
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
@media (max-width:640px) { .charts-grid, .bottom-grid { grid-template-columns:1fr; } }
</style>
</head>
<body>
<div class="page">

  <h1>US Macro Regime Dashboard</h1>
  <p class="sub" id="fetchedAt">Yield curve (T10Y2Y) + 5Y breakeven inflation (T5YIE) &middot; Loading&hellip;</p>

  <div class="controls">
    <div class="ctrl-group">
      <label>Smoothing method</label>
      <div class="btn-group">
        <button class="tbtn on" id="b-sma" onclick="setMethod('sma')">Moving average</button>
        <button class="tbtn" id="b-z" onclick="setMethod('zscore')">Z-score of RoC</button>
      </div>
    </div>
    <div class="ctrl-group">
      <label>Window: <span id="wout" style="font-weight:500;color:var(--text)">20 days</span></label>
      <div class="slider-row">
        <span style="font-size:12px;color:var(--faint)">5</span>
        <input type="range" id="wslider" min="5" max="90" value="20" step="1" oninput="onWin(this.value)"/>
        <span style="font-size:12px;color:var(--faint)">90</span>
      </div>
    </div>
  </div>

  <p id="status">Fetching data&hellip;</p>

  <div class="charts-grid">
    <div class="card">
      <p class="clabel" id="clabel">Yield curve (10Y&minus;2Y) &mdash; Moving average (20d)</p>
      <div class="chart-wrap"><canvas id="cChart" role="img" aria-label="Smoothed yield curve signal over time"></canvas></div>
    </div>
    <div class="card">
      <p class="clabel" id="blabel">5Y breakeven inflation &mdash; Moving average (20d)</p>
      <div class="chart-wrap"><canvas id="bChart" role="img" aria-label="Smoothed 5-year breakeven inflation rate over time"></canvas></div>
    </div>
  </div>

  <div class="bottom-grid">
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
      <p class="qnote" id="qnote">SMA: yield curve vs 0% &middot; breakevens vs 2.5%</p>
    </div>
    <div>
      <div class="mcard">
        <p class="mlabel">Yield curve signal</p>
        <p class="mval" id="cval">&mdash;</p>
        <p class="msub" id="csub">Loading&hellip;</p>
      </div>
      <div class="mcard">
        <p class="mlabel">Breakeven signal</p>
        <p class="mval" id="bval">&mdash;</p>
        <p class="msub" id="bsub">Loading&hellip;</p>
      </div>
    </div>
  </div>

</div>
<script>
let RAW_CURVE=[], RAW_BEI=[], method='sma', win=20, cInst=null, bInst=null;

function setMethod(m){
  method=m;
  document.getElementById('b-sma').classList.toggle('on',m==='sma');
  document.getElementById('b-z').classList.toggle('on',m==='zscore');
  render();
}
function onWin(v){
  win=parseInt(v);
  document.getElementById('wout').textContent=v+' days';
  render();
}
function sma(data,w){
  return data.map((_,i)=>{
    if(i<w-1) return null;
    const sl=data.slice(i-w+1,i+1);
    return sl.reduce((s,x)=>s+x.value,0)/w;
  });
}
function zscoreRoC(data,w){
  const roc=data.map((d,i)=>i===0?null:d.value-data[i-1].value);
  return data.map((_,i)=>{
    if(i<w) return null;
    const sl=roc.slice(i-w+1,i+1).filter(x=>x!==null);
    if(sl.length<3) return null;
    const mean=sl.reduce((s,x)=>s+x,0)/sl.length;
    const std=Math.sqrt(sl.reduce((s,x)=>s+(x-mean)**2,0)/sl.length);
    if(std===0) return 0;
    return (roc[i]-mean)/std;
  });
}
function smooth(data){ return method==='sma'?sma(data,win):zscoreRoC(data,win); }
function isDark(){ return matchMedia('(prefers-color-scheme:dark)').matches; }

function makeChart(id,labels,smoothed,raw,hexL,hexD){
  const dark=isDark(), hex=dark?hexD:hexL;
  const gridC=dark?'rgba(255,255,255,0.07)':'rgba(0,0,0,0.06)';
  const tickC='#6b6a65';
  const rawC=dark?'rgba(255,255,255,0.08)':'rgba(0,0,0,0.07)';
  const zeroC=dark?'rgba(255,255,255,0.22)':'rgba(0,0,0,0.15)';
  const datasets=[
    {label:'Raw',data:raw,borderColor:rawC,borderWidth:1,pointRadius:0,tension:0,spanGaps:false},
    {label:'Smoothed',data:smoothed,borderColor:hex,borderWidth:2.5,pointRadius:0,tension:0.15,spanGaps:false}
  ];
  if(method==='zscore'){
    datasets.splice(1,0,{label:'Zero',data:labels.map(()=>0),borderColor:zeroC,borderWidth:1,borderDash:[4,4],pointRadius:0,spanGaps:true});
  }
  const ctx=document.getElementById(id).getContext('2d');
  return new Chart(ctx,{
    type:'line',data:{labels,datasets},
    options:{
      responsive:true,maintainAspectRatio:false,animation:false,
      plugins:{
        legend:{display:false},
        tooltip:{mode:'index',intersect:false,callbacks:{label:c=>{
          const v=c.parsed.y;
          if(v===null||c.dataset.label==='Zero') return null;
          const suf=method==='sma'?'%':'\u03c3';
          return c.dataset.label+': '+v.toFixed(2)+suf;
        }}}
      },
      scales:{
        x:{ticks:{color:tickC,font:{size:11},maxTicksLimit:6,callback:function(val,i){const l=labels[i];return l?l.slice(0,7):'';} },grid:{color:gridC}},
        y:{ticks:{color:tickC,font:{size:11},maxTicksLimit:5,callback:v=>v.toFixed(1)},grid:{color:gridC}}
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
  const cSmooth=smooth(cA), bSmooth=smooth(bA);
  const cRaw=cA.map(d=>d.value), bRaw=bA.map(d=>d.value);
  const mLbl=method==='sma'?'Moving average ('+win+'d)':'Z-score of RoC ('+win+'d)';
  document.getElementById('clabel').textContent='Yield curve (10Y\u22122Y) \u2014 '+mLbl;
  document.getElementById('blabel').textContent='5Y breakeven inflation \u2014 '+mLbl;
  if(cInst){cInst.destroy();cInst=null;}
  if(bInst){bInst.destroy();bInst=null;}
  cInst=makeChart('cChart',labels,cSmooth,cRaw,'#185FA5','#85B7EB');
  bInst=makeChart('bChart',labels,bSmooth,bRaw,'#993C1D','#F0997B');
  const lastC=[...cSmooth].reverse().find(v=>v!==null&&v!==undefined);
  const lastB=[...bSmooth].reverse().find(v=>v!==null&&v!==undefined);
  if(lastC===undefined||lastB===undefined) return;
  const suf=method==='sma'?'%':'\u03c3';
  document.getElementById('cval').textContent=lastC.toFixed(2)+suf;
  document.getElementById('bval').textContent=lastB.toFixed(2)+suf;
  let growthUp,inflUp;
  if(method==='sma'){
    growthUp=lastC>0; inflUp=lastB>2.5;
    document.getElementById('csub').textContent=lastC>0?'Curve positive \u2192 expansionary growth signal':'Curve inverted \u2192 contraction signal';
    document.getElementById('bsub').textContent=lastB>2.5?'Above 2.5% \u2192 elevated inflation expectations':'At or below 2.5% \u2192 relatively contained';
    document.getElementById('qnote').textContent='SMA thresholds: yield curve vs 0% \u00b7 breakevens vs 2.5%';
  } else {
    growthUp=lastC>0; inflUp=lastB>0;
    document.getElementById('csub').textContent=lastC>0?'Steepening faster than avg \u2192 growth momentum building':'Flattening faster than avg \u2192 growth momentum fading';
    document.getElementById('bsub').textContent=lastB>0?'Rising faster than avg \u2192 inflation reaccelerating':'Falling faster than avg \u2192 inflation decelerating';
    document.getElementById('qnote').textContent='Z-score thresholds: both vs 0 (historical avg rate of change)';
  }
  ['q-boom','q-gold','q-stag','q-bust'].forEach(id=>document.getElementById(id).classList.remove('lit'));
  if(growthUp&&inflUp) document.getElementById('q-boom').classList.add('lit');
  else if(growthUp&&!inflUp) document.getElementById('q-gold').classList.add('lit');
  else if(!growthUp&&inflUp) document.getElementById('q-stag').classList.add('lit');
  else document.getElementById('q-bust').classList.add('lit');
}

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

@app.route("/api/refresh")
def api_refresh():
    """Force-clear cache and re-fetch. Point your cron-job.org job here."""
    _cache["data"] = None
    _cache["fetched_at"] = 0
    try:
        get_data()
        return jsonify({"status": "ok", "fetched_at": _cache["data"]["fetched_at"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 502

if __name__ == "__main__":
    app.run(debug=True)
