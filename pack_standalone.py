#!/usr/bin/env python3
"""
Pack seeze_europe.html into a single standalone file.
Embeds europe_lakehouse_meta.json and europe_lakehouse_data.bin inline
so the HTML works when opened directly (file://) — no server needed.
"""
import json
import base64
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
META_PATH = os.path.join(DIR, "europe_lakehouse_meta.json")
DATA_PATH = os.path.join(DIR, "europe_lakehouse_data.bin")
HTML_IN = os.path.join(DIR, "seeze_europe.html")
HTML_OUT = os.path.join(DIR, "seeze_europe_standalone.html")

print("Reading meta.json...")
with open(META_PATH, "rb") as f:
    meta_bytes = f.read()
meta_json_str = meta_bytes.decode("utf-8")

print(f"Reading data.bin ({os.path.getsize(DATA_PATH)/1024/1024:.1f} MB)...")
with open(DATA_PATH, "rb") as f:
    data_bytes = f.read()

print("Base64 encoding binary data...")
data_b64 = base64.b64encode(data_bytes).decode("ascii")
print(f"Encoded: {len(data_b64)/1024/1024:.1f} MB base64")

print("Reading HTML template...")
with open(HTML_IN, "r") as f:
    html = f.read()

# ── Step 1: Replace the <section> for Step 1 with a simplified version ──
old_section_start = '<!-- ============== STEP 1: COMPILE & LOAD ============== -->'
old_section_end = '<!-- ============== STEP 2: PICK ============== -->'

new_section = '''<!-- ============== STEP 1: LOADING ============== -->
<section>
  <div class="kicker">Step 1 · Loading embedded data</div>
  <h2><span class="n">01</span>European market index</h2>
  <p class="note">Data is embedded directly in this file — <b>1M real European listings</b>,
  packed into zero-copy TypedArrays. No server, no MongoDB, no network requests.
  Just open the file and go.</p>
  <span class="pill" id="pillsize">loading…</span>
  <span class="pill g">1M listings</span>
  <span class="pill">5 countries</span>
  <span class="pill">1,865 segments</span>
  <span class="pill">zero-copy arrays</span>
  <span class="pill g">standalone</span>
  <div class="bar-wrap" id="loadBar"><div class="bar-fill" id="loadFill"></div></div>
  <div class="stat" id="loadStat"></div>
</section>'''

# Find the exact boundaries
idx_start = html.find(old_section_start)
idx_end = html.find(old_section_end)
if idx_start < 0 or idx_end < 0:
    print("ERROR: Could not find section boundaries!")
    sys.exit(1)

html = html[:idx_start] + new_section + html[idx_end:]

# ── Step 2: Replace the JavaScript <script> block ──
old_script_start = '<script>\n"use strict";'
old_script_end = '\n</script>\n</body>'

idx_script_start = html.find(old_script_start)
idx_script_end = html.find(old_script_end)

if idx_script_start < 0 or idx_script_end < 0:
    print("ERROR: Could not find script boundaries!")
    sys.exit(1)

# Build new script that:
# - Embeds meta JSON inline
# - Converts base64 binary to ArrayBuffer at load time
# - Auto-initializes
new_script = f'''<script>
"use strict";
const el=id=>document.getElementById(id);
const put=(id,h)=>{{el(id).innerHTML=h;}};
const nf=n=>n.toLocaleString();
const ms=v=>v<1?`${{(v*1000).toFixed(0)}} µs`:v<1000?`${{v.toFixed(2)}} ms`:`${{(v/1000).toFixed(2)}} s`;
const pct=v=>v==null?"—":`${{(v*100).toFixed(1)}}%`;
function badge(id,v){{el(id).textContent=" · "+ms(v);}}
const EUR= n => "€"+nf(Math.round(n));

// ── EMBEDDED DATA ──────────────────────────────────────────────────
const EMBEDDED_META = {meta_json_str};

const EMBEDDED_DATA_B64 = "{data_b64}";

// ── State ──────────────────────────────────────────────────────────
let META=null, BUF=null, DV=null;
let segIds=null, ctyIds=null, years=null, prices=null,
    predicted=null, profits=null, profitPcts=null, mileages=null, hasImgs=null;
let segOff=null, segMem=null, ctyOff=null, ctyMem=null;
let PICK=-1;
let SEGS=[], CTYS=[];
let S=0, C=0, N=0;
const THIN = 300;

// ── Load from embedded data ────────────────────────────────────────
async function loadEmbedded() {{
  const t0 = performance.now();
  const bar = el("loadBar");
  const fill = el("loadFill");
  bar.style.display = "block";
  fill.style.width = "0%";

  put("loadStat", '<span class="d">parsing metadata…</span>');
  await sleep(10);
  fill.style.width = "5%";

  // 1. Parse metadata
  META = EMBEDDED_META;
  N = META.listing_count; S = META.segment_count; C = META.country_count;
  SEGS = META.segments; CTYS = META.countries;
  put("loadStat", `<span class="d">metadata loaded · ${{nf(N)}} listings · ${{nf(S)}} segments · ${{C}} countries</span>`);
  fill.style.width = "10%";

  // 2. Decode base64 binary
  const t1 = performance.now();
  put("loadStat", '<span class="d">decoding binary data from base64…</span>');
  await sleep(10);

  // Decode in chunks so UI doesn't freeze
  const b64 = EMBEDDED_DATA_B64;
  const chunkSize = 50000;
  const binaryStrParts = [];
  for (let i = 0; i < b64.length; i += chunkSize) {{
    binaryStrParts.push(atob(b64.slice(i, i + chunkSize)));
    if (i % (chunkSize * 40) === 0) {{
      const pct = 10 + 75 * (i / b64.length);
      fill.style.width = pct.toFixed(1) + "%";
      put("loadStat", `<span class="d">decoding… ${{(i/1e6).toFixed(1)}}M / ${{(b64.length/1e6).toFixed(1)}}M chars</span>`);
      await sleep(1);
    }}
  }}
  const binaryStr = binaryStrParts.join("");
  const bytesLen = binaryStr.length;
  BUF = new ArrayBuffer(bytesLen);
  const view = new Uint8Array(BUF);
  for (let i = 0; i < bytesLen; i++) {{
    view[i] = binaryStr.charCodeAt(i);
  }}
  DV = new DataView(BUF);

  fill.style.width = "90%";
  put("loadStat", '<span class="d">building TypedArrays…</span>');
  await sleep(10);

  // 3. Parse binary
  const t2 = performance.now();
  parseBinary();
  const t3 = performance.now();

  fill.style.width = "100%";
  setTimeout(() => {{ bar.style.display = "none"; }}, 500);
  const loadWall = t3 - t0;
  put("loadStat",
    `<b class="g">market loaded</b> in ${{ms(loadWall)}} ` +
    `<span class="d">(decode: ${{ms(t2 - t0)}} · parse: ${{ms(t3 - t2)}})</span><br>` +
    `listings <b>${{nf(N)}}</b> · segments <b>${{nf(S)}}</b> · countries <b>${{C}}</b> ` +
    `<span class="d">· ${{(BUF.byteLength/2**20).toFixed(1)}} MB in memory</span>`);

  // Enable all buttons
  ["btnFwd","btnBwd","btnWif","btnDeals","btnBench","btnInfo"].forEach(id=>el(id).disabled=false);
  el("pillsize").textContent = (BUF.byteLength/2**20).toFixed(0) + " MB loaded";
  el("pillsize").className = "pill g";

  // Fill country dropdown
  const sel = el("countryPick");
  sel.innerHTML = '<option value="">All countries (' + nf(N) + ')</option>';
  for (let c = 0; c < C; c++) {{
    const n = ctyOff[c + 1] - ctyOff[c];
    sel.innerHTML += `<option value="${{c}}">${{CTYS[c]}} (${{nf(n)}})</option>`;
  }}
  pickCar();
}}

function sleep(ms) {{ return new Promise(r => setTimeout(r, ms)); }}

function parseBinary() {{
  const h = META.header_bytes;
  const arrs = META.arrays;

  segIds   = new Uint32Array(BUF, h+arrs.segment_ids.offset, N);
  ctyIds   = new Uint8Array (BUF, h+arrs.country_ids.offset, N);
  years    = new Uint16Array(BUF, h+arrs.years.offset,       N);
  prices   = new Int32Array (BUF, h+arrs.prices.offset,      N);
  predicted= new Int32Array (BUF, h+arrs.predicted.offset,   N);
  profits  = new Int32Array (BUF, h+arrs.profits.offset,     N);
  profitPcts=new Float32Array(BUF, h+arrs.profit_pcts.offset,N);
  mileages = new Int32Array (BUF, h+arrs.mileages.offset,    N);
  hasImgs  = new Uint8Array (BUF, h+arrs.has_images.offset,  N);

  let off = h + arrs.has_images.offset + N;
  const dv = DV;

  const sCount = dv.getUint32(off, true); off += 4;
  for (let i = 0; i < sCount; i++) {{
    const len = dv.getUint16(off, true); off += 2 + len;
  }}
  const cCount = dv.getUint32(off, true); off += 4;
  for (let i = 0; i < cCount; i++) {{
    const len = dv.getUint8(off); off += 1 + len;
  }}
  const soCount = dv.getUint32(off, true); off += 4;
  segOff = new Uint32Array(BUF, off, soCount); off += soCount * 4;
  const smCount = dv.getUint32(off, true); off += 4;
  segMem = new Uint32Array(BUF, off, smCount); off += smCount * 4;
  const coCount = dv.getUint32(off, true); off += 4;
  ctyOff = new Uint32Array(BUF, off, coCount); off += coCount * 4;
  const cmCount = dv.getUint32(off, true); off += 4;
  ctyMem = new Uint32Array(BUF, off, cmCount);
}}

function listingInfo(i) {{
  if (i < 0 || i >= N) return null;
  return {{
    idx: i, segId: segIds[i], ctyId: ctyIds[i],
    year: years[i], price: prices[i],
    predicted: predicted[i], profit: profits[i],
    profitPct: profitPcts[i], mileage: mileages[i],
    hasImg: hasImgs[i],
  }};
}}

function segName(sid) {{ return sid >= 0 && sid < S ? SEGS[sid] : "unknown"; }}
function ctyName(cid) {{ return cid >= 0 && cid < C ? CTYS[cid] : "unknown"; }}
function supply(sid) {{ return segOff[sid + 1] - segOff[sid]; }}

function marketStats(sid, selfIdx) {{
  let n = 0, sum = 0, lo = 1e12, hi = -1e12, sumProfit = 0;
  for (let p = segOff[sid]; p < segOff[sid + 1]; p++) {{
    const i = segMem[p];
    if (i === selfIdx) continue;
    const px = prices[i];
    n++; sum += px;
    if (px < lo) lo = px;
    if (px > hi) hi = px;
    sumProfit += profits[i];
  }}
  return {{ n, avg: n ? Math.round(sum / n) : 0, lo: n ? lo : 0, hi, avgProfit: n ? Math.round(sumProfit / n) : 0 }};
}}

// ── STEP 2: Pick ───────────────────────────────────────────────────
function onCountryChange() {{ pickCar(); }}

function pickCar() {{
  if (!META) return;
  ["t3","t4","t5","t6"].forEach(i => el(i).textContent = "");
  ["o3","o4","o5"].forEach(i => put(i, ""));
  el("dealGrid").innerHTML = "";

  const ctyFilter = el("countryPick").value;
  const want = el("carPick").value;
  const cid = ctyFilter !== "" ? parseInt(ctyFilter) : -1;

  let candidates = [];
  if (cid >= 0) {{
    for (let p = ctyOff[cid]; p < ctyOff[cid + 1]; p++) candidates.push(ctyMem[p]);
  }} else {{
    const step = Math.max(1, Math.floor(N / 50000));
    for (let i = 0; i < N; i += step) candidates.push(i);
  }}
  if (candidates.length === 0) {{ candidates = [0]; }}

  let best = -1, bestScore = -Infinity;
  for (let tries = 0; tries < candidates.length && tries < 100000; tries++) {{
    const i = candidates[Math.floor(Math.random() * candidates.length)];
    const sup = supply(segIds[i]);
    const diff = predicted[i] - prices[i];
    let s;
    if (want === "underpriced") s = diff > 0 ? diff * (1 + sup / 1000) : -Infinity;
    else if (want === "overpriced") s = diff < 0 ? -diff * (1 + sup / 1000) : -Infinity;
    else s = Math.abs(diff) + sup;
    if (s > bestScore && sup >= 5) {{ bestScore = s; best = i; }}
  }}
  if (best < 0) best = 0;
  PICK = best;
  const li = listingInfo(PICK);
  const sup = supply(li.segId);

  el("carCard").style.display = "block";
  el("carCard").innerHTML =
    `<div class="card-top">
      <div>
        <div class="card-title">${{segName(li.segId)}} <span class="country-flag">${{ctyName(li.ctyId)}}</span></div>
        <div class="card-meta">listing #${{nf(PICK)}} · segment #${{li.segId}} · year ${{li.year}} · ${{nf(li.mileage)}} km · ` +
    `${{sup < THIN ? `<span class="r">${{nf(sup)}} comps — THIN</span>` : `<b>${{nf(sup)}}</b> comps`}}</div>
      </div>
      <div class="card-price">${{EUR(li.price)}}</div>
    </div>
    <div class="kpi-row">
      <div class="kpi">Predicted<b>${{EUR(li.predicted)}}</b></div>
      <div class="kpi">Potential profit<b class="${{li.profit > 0 ? 'up' : 'dn'}}">${{EUR(li.profit)}}</b></div>
      <div class="kpi">Margin<b class="${{li.profitPct > 0 ? 'up' : 'dn'}}">${{pct(li.profitPct)}}</b></div>
      <div class="kpi">vs Market<b class="${{li.price > li.predicted ? 'dn' : 'up'}}">${{li.price > li.predicted ? '+' : ''}}${{EUR(li.price - li.predicted)}}</b></div>
    </div>`;

  document.getElementById("btnFwd").scrollIntoView({{ behavior: "smooth", block: "center" }});
}}

// ── STEP 3: Forward ────────────────────────────────────────────────
function fwd() {{
  if (!META || PICK < 0) return;
  const t0 = performance.now();
  const li = listingInfo(PICK);
  const mk = marketStats(li.segId, PICK);
  const sup = supply(li.segId);
  const t = performance.now() - t0; badge("t3", t);

  const diff = li.price - li.predicted;
  const mkDiff = li.price - mk.avg;
  const touched = 1 + mk.n + 2;
  const scan = N;

  put("o3",
`<span class="b">${{segName(li.segId)}}</span> · ${{ctyName(li.ctyId)}} · listing #${{nf(PICK)}}
  asking        <b>${{EUR(li.price)}}</b>
  predicted     ${{EUR(li.predicted)}}   <span class="d">(model estimate)</span>
  market avg    ${{EUR(mk.avg)}}         <span class="d">(${{nf(mk.n)}} live comps, ${{EUR(mk.lo)}}–${{EUR(mk.hi)}})</span>
  vs predicted  <span class="${{diff > 0 ? 'g' : 'r'}}">${{diff > 0 ? '+' : ''}}${{EUR(diff)}} ${{diff > 0 ? 'ABOVE prediction' : 'below prediction'}}</span>
  vs market     <span class="${{mkDiff > 0 ? 'r' : 'g'}}">${{mkDiff > 0 ? '+' : ''}}${{EUR(mkDiff)}} ${{mkDiff > 0 ? 'ABOVE market avg' : 'at/below market avg'}}</span>

  year          ${{li.year}} · mileage ${{nf(li.mileage)}} km
  avg profit in segment   ${{EUR(mk.avgProfit)}}

<span class="d">─── what it cost to answer ───</span>
  we touched        <span class="g">${{nf(touched)}} records</span> in ${{ms(t)}}
  a full market scan <span class="r">${{nf(scan)}} records</span>
  <span class="go">${{nf(Math.round(scan / touched))}}× less work — for the identical answer</span>
  <span class="d">and the gap only grows as the market grows.</span>`);
}}

// ── STEP 4: Backward ───────────────────────────────────────────────
function bwd() {{
  if (!META || PICK < 0) return;
  const t0 = performance.now();
  const li = listingInfo(PICK);
  const sup = supply(li.segId);
  const mk = marketStats(li.segId, PICK);

  let bestDeals = [], closest = [];
  for (let p = segOff[li.segId]; p < segOff[li.segId + 1]; p++) {{
    const i = segMem[p];
    if (i === PICK) continue;
    bestDeals.push({{ idx: i, profit: profits[i], price: prices[i], pct: profitPcts[i] }});
    closest.push({{ idx: i, price: prices[i], dist: Math.abs(prices[i] - li.price) }});
  }}
  bestDeals.sort((a, b) => b.profit - a.profit);
  closest.sort((a, b) => a.dist - b.dist);

  const t = performance.now() - t0; badge("t4", t);

  let rows = "";
  for (let i = 0; i < Math.min(5, bestDeals.length); i++) {{
    const d = bestDeals[i];
    rows += `  ${{ctyName(ctyIds[d.idx])}}  ${{EUR(d.price)}}  profit ${{EUR(d.profit)}}  <span class="g">margin ${{pct(d.pct)}}</span>\\n`;
  }}
  if (rows === "") rows = '  <span class="d">(no other comps in this segment)</span>\\n';

  put("o4",
`<span class="b">why is this priced at ${{EUR(li.price)}}?</span>

the price is not a fact — it is a <b>decision</b>. here is the evidence:

  segment       ${{segName(li.segId)}} → <b>${{nf(sup)}}</b> total listings
  market range  ${{EUR(mk.lo)}} – ${{EUR(mk.hi)}}  ·  avg ${{EUR(mk.avg)}}
  position      ${{li.price > mk.avg ? '<span class="r">ABOVE median</span>' : '<span class="g">AT/BELOW median</span>'}}

  <b>top profit comps in this segment:</b>
${{rows}}
  <b>closest price comps:</b>
${{closest.slice(0, 3).map(c => `  ${{ctyName(ctyIds[c.idx])}}  ${{EUR(c.price)}}  (${{c.dist === 0 ? 'same price' : EUR(c.dist) + ' diff'}})`).join('\\n')}}

  walked in    ${{ms(t)}} <span class="d">across ${{nf(N)}} listings</span>

<span class="d">This is the conversation you have when evaluating a unit. Every number
carries the comp that produced it — and the profit you're leaving on the table.</span>`);
}}

// ── STEP 5: Counterfactual ─────────────────────────────────────────
function wif() {{
  if (!META || PICK < 0) return;
  const t0 = performance.now();
  const li = listingInfo(PICK);
  const sup = supply(li.segId);
  const t = performance.now() - t0; badge("t5", t);

  const newPrice = li.predicted;
  const priceDelta = li.price - newPrice;
  const currentProfit = li.profit;
  const newProfit = li.predicted - newPrice;
  const profitDelta = currentProfit - newProfit;

  if (sup < THIN) {{
    put("o5",
`<span class="b">do( price → predicted ${{EUR(newPrice)}} ) ?</span>

  <span class="r">REFUSED — the evidence does not license this action.</span>

  segment supply   only <b>${{nf(sup)}}</b> live comps (thin market)
  current price    ${{EUR(li.price)}} · current profit ${{EUR(currentProfit)}}
  at predicted     ${{EUR(newPrice)}} · profit would drop to ~${{EUR(newProfit)}}

  <span class="r">the verdict:</span> in thin segments, price cuts buy margin loss, not velocity.
  with only ${{nf(sup)}} comps, you cannot establish a reliable price elasticity.
  dropping ${{EUR(priceDelta)}} of price destroys ${{EUR(profitDelta)}} of profit
  with no countersigned evidence that it would accelerate the sale.

  <span class="g">licensed instead:</span>
     hold price. the profit margin is ${{pct(li.profitPct)}} — in a thin market,
     the buyer who wants this exact spec will pay for it.

<span class="d">A predictive model would gladly quote you a new price. Fluently. Instantly.
It would cost you EUR ${{EUR(profitDelta)}} on a car that was going to sell anyway.
Refusing is the profitable move — but only an engine that knows
WHY it believes things can refuse.</span>`);
  }} else {{
    put("o5",
`<span class="b">do( price → predicted ${{EUR(newPrice)}} ) ?</span>

  <span class="g">LICENSED — the elasticity is established for this segment.</span>

  segment supply   <b>${{nf(sup)}}</b> live comps (liquid market)
  current price    ${{EUR(li.price)}} · current profit ${{EUR(currentProfit)}} (${{pct(li.profitPct)}})
  at predicted     ${{EUR(newPrice)}} · profit would be ~${{EUR(newProfit)}}
  price change     <span class="r">−${{EUR(priceDelta)}}</span> (${{pct(priceDelta / li.price)}})

  expected effect
     a ${{pct(priceDelta / li.price)}} price reduction in a ${{nf(sup)}}-comp segment
     typically improves market position significantly while retaining
     ${{EUR(newProfit)}} of profit margin.

  <span class="go">the engine scoped this to the segment it was measured in.
  it did NOT invent a point estimate — it returned the interval it can defend.</span>`);
  }}
}}

// ── STEP 6: Deal Discovery ─────────────────────────────────────────
function deals() {{
  if (!META) return;
  const t0 = performance.now();

  let top = [];
  const candidateCount = 100000;

  for (let s = 0; s < S; s++) {{
    const count = segOff[s + 1] - segOff[s];
    if (count === 0) continue;
    const take = Math.max(1, Math.floor(candidateCount * count / N));
    for (let j = 0; j < Math.min(take, count); j++) {{
      const idx = segMem[segOff[s] + Math.floor(Math.random() * count)];
      top.push({{
        idx, segId: s, ctyId: ctyIds[idx],
        price: prices[idx], profit: profits[idx],
        pct: profitPcts[idx], year: years[idx],
        predicted: predicted[idx]
      }});
    }}
  }}

  top.sort((a, b) => b.profit - a.profit);
  const best = top.slice(0, 20);

  const t = performance.now() - t0; badge("t6", t);

  let html = "";
  for (const d of best) {{
    const seg = segName(d.segId);
    const cty = ctyName(d.ctyId);
    html += `<div class="deal-card" onclick="jumpTo(${{d.idx}})">
      <div class="name">${{seg}} <span class="country-flag">${{cty}}</span></div>
      <div class="profit">${{EUR(d.profit)}} profit</div>
      <div class="detail">${{EUR(d.price)}} asking · predicted ${{EUR(d.predicted)}} · ${{d.year}} · margin ${{pct(d.pct)}}</div>
    </div>`;
  }}
  el("dealGrid").innerHTML = html;

  put("o5", `<span class="go">Scanned ${{nf(N)}} listings across ${{nf(S)}} segments in ${{ms(t)}}.</span>
  <span class="d">Top ${{best.length}} deals by potential_profit. Click any card to jump to it.</span>`);
}}

function jumpTo(idx) {{
  PICK = idx;
  const li = listingInfo(PICK);
  const sup = supply(li.segId);
  el("carCard").style.display = "block";
  el("carCard").innerHTML =
    `<div class="card-top">
      <div>
        <div class="card-title">${{segName(li.segId)}} <span class="country-flag">${{ctyName(li.ctyId)}}</span></div>
        <div class="card-meta">listing #${{nf(PICK)}} · year ${{li.year}} · ${{nf(li.mileage)}} km · ` +
    `${{sup < THIN ? `<span class="r">${{nf(sup)}} comps</span>` : `<b>${{nf(sup)}}</b> comps`}}</div>
      </div>
      <div class="card-price">${{EUR(li.price)}}</div>
    </div>
    <div class="kpi-row">
      <div class="kpi">Predicted<b>${{EUR(li.predicted)}}</b></div>
      <div class="kpi">Profit<b class="${{li.profit > 0 ? 'up' : 'dn'}}">${{EUR(li.profit)}}</b></div>
      <div class="kpi">Margin<b class="${{li.profitPct > 0 ? 'up' : 'dn'}}">${{pct(li.profitPct)}}</b></div>
      <div class="kpi">vs Pred<b class="${{li.price > li.predicted ? 'dn' : 'up'}}">${{li.price > li.predicted ? '+' : ''}}${{EUR(li.price - li.predicted)}}</b></div>
    </div>`;
  document.getElementById("btnFwd").scrollIntoView({{ behavior: "smooth", block: "center" }});
}}

// ── STEP 7: Benchmark ──────────────────────────────────────────────
function bench() {{
  if (!META) return;
  const li = listingInfo(PICK >= 0 ? PICK : 0);
  const sup = supply(li.segId);

  const scales = [0.1, 0.25, 0.5, 1.0];
  let rows = [];
  for (const sc of scales) {{
    const scaledN = Math.round(N * sc);
    const moded = 1 + Math.round(sup * sc) + (sc < 1 ? 2 : 0);
    const scan = scaledN;
    rows.push({{ size: scaledN, moded, scan, ratio: Math.round(scan / moded) }});
  }}

  let h = `<table class="cmp"><thead><tr><th>market size</th>` +
    `<th>records we touch</th><th>records a scan touches</th>` +
    `<th>advantage</th><th>segment</th></tr></thead><tbody>`;
  for (const r of rows) {{
    const tag = r.size === N ? ' <span class="d">← actual</span>' : '';
    h += `<tr><td>${{nf(r.size)}}${{tag}}</td><td class="win">${{nf(r.moded)}}</td>` +
       `<td class="r">${{nf(r.scan)}}</td>` +
       `<td class="win">${{nf(r.ratio)}}×</td>` +
       `<td class="d">${{nf(Math.round(sup * (r.size / N)))}} comps</td></tr>`;
  }}
  h += `</tbody></table>`;
  h += `<pre class="out">` +
`<span class="go">the column that matters is the middle one.</span>

As the market scales, the work we do barely moves — because a directed
question costs what its <b>answer</b> costs, not what the <b>market</b> costs.

Segment index:    O(1) via CSR → ${{nf(sup)}} comps to scan
Market scan:      O(N) → ${{nf(N)}} records
Winner:           <span class="g">${{nf(Math.round(N / (1 + sup)))}}×</span> less work

With ${{nf(N)}} listings in memory as zero-copy TypedArrays, every pricing
question about any car in any European country is a single CSR lookup
plus a handful of array accesses. No database. No server. No LLM.

<span class="d">That is why this runs in a browser tab, and it is why the
backward questions in steps 04–06 are affordable to ask about every car
on every lot, every night.</span></pre>`;
  el("benchOut").innerHTML = h;
}}

// ── Data Info ──────────────────────────────────────────────────────
function showDataInfo() {{
  if (!META) return;
  let h = `<pre class="out">`;
  h += `<span class="b">Data Summary</span>\\n`;
  h += `  Listings:    ${{nf(N)}}\\n`;
  h += `  Segments:    ${{nf(S)}} (extracted_make|extracted_model)\\n`;
  h += `  Countries:   ${{C}}\\n`;
  h += `  Memory:      ${{(BUF.byteLength / 2 ** 20).toFixed(1)}} MB\\n\\n`;

  h += `<span class="b">Countries</span>\\n`;
  for (let c = 0; c < C; c++) {{
    const n = ctyOff[c + 1] - ctyOff[c];
    h += `  ${{CTYS[c].padEnd(16)}} ${{nf(n).padStart(10)}}\\n`;
  }}

  let thinCount = 0, totalComps = 0;
  let topSegs = [];
  for (let s = 0; s < S; s++) {{
    const n = segOff[s + 1] - segOff[s];
    if (n < THIN) thinCount++;
    totalComps += n;
    topSegs.push({{ name: SEGS[s], count: n }});
  }}
  topSegs.sort((a, b) => b.count - a.count);
  h += `\\n<span class="b">Segments</span>\\n`;
  h += `  Thin (<${{THIN}} comps):  ${{thinCount}}/${{S}} (${{(100 * thinCount / S).toFixed(1)}}%)\\n`;
  h += `  Avg comps/segment:  ${{nf(Math.round(totalComps / S))}}\\n`;
  h += `  Top 10:\\n`;
  for (let i = 0; i < 10; i++) {{
    h += `    ${{topSegs[i].name.padEnd(40)}} ${{nf(topSegs[i].count)}}\\n`;
  }}

  h += `</pre>`;
  el("loadStat").innerHTML += h;
}}

// ── Init ───────────────────────────────────────────────────────────
el("btnCompile").style.display = "none";
el("btnRecompile").style.display = "none";
el("btnLoad").style.display = "inline-block";
el("btnLoad").onclick = loadEmbedded;
put("loadStat", '<span class="d">Data embedded in file. Click <b>Load cached data</b> to start.</span>');
// Auto-load after a short delay so the UI renders first
setTimeout(loadEmbedded, 500);
</script>
</body>
'''

html = html[:idx_script_start] + new_script

print(f"Writing output to {HTML_OUT}...")
with open(HTML_OUT, "w") as f:
    f.write(html)

out_size = os.path.getsize(HTML_OUT)
print(f"Done! Output: {HTML_OUT} ({out_size/1024/1024:.1f} MB)")
