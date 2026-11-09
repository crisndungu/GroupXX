"""Smart Plant Monitor dashboard: zones, urgency sorting, plant detail, and a managed event log.

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].
Open http://localhost:8080 while run_live.py is running. JSON endpoints: /state, /events.
No external libraries or network requests: charts are drawn in SVG by the page itself.
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Deque, Dict, List, Optional, Tuple, Type

STALE_AFTER_S = 15.0      # no reading for this long -> no recent data
ALERT_WINDOW_S = 10.0     # a rejected message within this window raises a plant alert
HISTORY_LEN = 144         # readings kept per device (24 simulated hours at 10-minute steps)
EVENT_LEN = 300           # events kept in memory
EVENTS_SHOWN = 100        # events returned to the page
SECURITY_BURST_S = 5.0    # rejected messages this close together are grouped into one event
WATER_COOLDOWN_S = 60.0   # at most one watering event per plant per minute
WATER_JUMP = 8.0          # a rise of at least this many points counts as watering
DEFAULT_DRY_AT = 30.0     # used only if a message omits dry_at


def plant_status(
    reading: Optional[Dict[str, Any]],
    last_seen: float,
    now: float,
    recent_rejections: int,
) -> str:
    """Return one of: healthy, dry, stale, alert. Pure function so it can be tested."""
    if recent_rejections > 0:
        return "alert"
    if reading is None or now - last_seen > STALE_AFTER_S:
        return "stale"
    dry_at = float(reading.get("dry_at", DEFAULT_DRY_AT))
    if reading["moisture"] < dry_at:
        return "dry"
    return "healthy"


class Monitor:
    """Thread-safe store for readings, history, counters, alerts, and a de-duplicated event log."""

    def __init__(self, meta: Optional[Dict[str, Any]] = None) -> None:
        self._lock = threading.Lock()
        self._latest: Dict[str, Tuple[Dict[str, Any], float]] = {}
        self._history: Dict[str, Deque[Tuple[float, float, float]]] = {}
        self._status: Dict[str, str] = {}
        self._accepted: Dict[str, int] = {}
        self._rejected: Dict[str, int] = {}
        self._alerts: Deque[Tuple[str, float]] = deque()
        self._events: Deque[Dict[str, Any]] = deque(maxlen=EVENT_LEN)
        self._last_water: Dict[str, float] = {}
        self._security_event: Optional[Dict[str, Any]] = None
        self._started_logged = False
        self._next_id = 1
        self.meta: Dict[str, Any] = meta or {}
        self.started = time.time()

    # ---- event log ------------------------------------------------------
    def _log(self, device: str, kind: str, message: str, level: str) -> Dict[str, Any]:
        now = time.time()
        event = {
            "id": self._next_id, "time": now, "last_time": now, "device": device,
            "kind": kind, "message": message, "level": level, "count": 1,
        }
        self._next_id += 1
        self._events.appendleft(event)
        return event

    def _transition(self, device: str, status: str, moisture: Optional[float]) -> None:
        previous = self._status.get(device)
        if previous == status:
            return
        self._status[device] = status
        # Only plant-level changes that a farmer acts on are logged.
        # Alerts are logged once per burst as a security event instead.
        if previous is None or status == "alert" or previous == "alert":
            return
        if status == "dry":
            text = f"needs water ({moisture:.1f}%)" if moisture is not None else "needs water"
            self._log(device, "status", text, "warn")
        elif status == "healthy":
            text = f"back above threshold ({moisture:.1f}%)" if moisture is not None else "back above threshold"
            self._log(device, "status", text, "ok")
        elif status == "stale":
            self._log(device, "status", "no readings received", "muted")

    # ---- ingestion ------------------------------------------------------
    def record_accept(self, device: str, reading: Dict[str, Any]) -> None:
        now = time.time()
        with self._lock:
            if not self._started_logged:
                self._started_logged = True
                self._log("site", "system", "gateway started receiving verified readings", "info")
            self._latest[device] = (reading, now)
            self._accepted[device] = self._accepted.get(device, 0) + 1
            hist = self._history.setdefault(device, deque(maxlen=HISTORY_LEN))
            moisture = float(reading["moisture"])
            temp = float(reading.get("temp_c", 0.0))
            if hist and moisture - hist[-1][1] >= WATER_JUMP:
                if now - self._last_water.get(device, 0.0) >= WATER_COOLDOWN_S:
                    self._last_water[device] = now
                    rise = moisture - hist[-1][1]
                    self._log(device, "water", f"watered or rained (+{rise:.1f} points)", "info")
            hist.append((now, moisture, temp))
            self._transition(device, plant_status(reading, now, now, 0), moisture)

    def record_reject(self, device: str) -> None:
        now = time.time()
        with self._lock:
            self._rejected[device] = self._rejected.get(device, 0) + 1
            self._alerts.append((device, now))
            ev = self._security_event
            if ev is not None and now - ev["last_time"] <= SECURITY_BURST_S:
                ev["count"] += 1
                ev["last_time"] = now
                devices = ev.setdefault("_devices", set())
                devices.add(device)
                ev["message"] = (f"{ev['count']} replayed or tampered messages rejected "
                                 f"from {len(devices)} plant{'s' if len(devices) != 1 else ''}")
            else:
                self._security_event = self._log(
                    "site", "security", "replayed or tampered message rejected", "bad")
                self._security_event["_devices"] = {device}

    # ---- views ----------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            while self._alerts and now - self._alerts[0][1] > ALERT_WINDOW_S:
                self._alerts.popleft()
            devices: Dict[str, Dict[str, Any]] = {}
            for dev in sorted(set(self._latest) | set(self._rejected)):
                reading, seen = self._latest.get(dev, (None, 0.0))
                recent = sum(1 for d, _ in self._alerts if d == dev)
                status = plant_status(reading, seen, now, recent)
                self._transition(dev, status, reading["moisture"] if reading else None)
                hist = list(self._history.get(dev, []))
                moisture = [m for _, m, _ in hist]
                dry_at = float(reading.get("dry_at", DEFAULT_DRY_AT)) if reading else DEFAULT_DRY_AT
                devices[dev] = {
                    "id": dev,
                    "species": reading.get("species", dev) if reading else dev,
                    "zone": reading.get("zone", "Unassigned") if reading else "Unassigned",
                    "dry_at": dry_at,
                    "status": status,
                    "moisture": reading["moisture"] if reading else None,
                    "temp_c": reading["temp_c"] if reading else None,
                    "margin": round(reading["moisture"] - dry_at, 1) if reading else None,
                    "seconds_since_reading": round(now - seen, 1) if reading else None,
                    "history": [round(m, 1) for m in moisture],
                    "temp_history": [round(t, 1) for _, _, t in hist],
                    "min": round(min(moisture), 1) if moisture else None,
                    "max": round(max(moisture), 1) if moisture else None,
                    "mean": round(sum(moisture) / len(moisture), 1) if moisture else None,
                    "accepted_total": self._accepted.get(dev, 0),
                    "rejected_total": self._rejected.get(dev, 0),
                }
            zones: Dict[str, List[str]] = {}
            for dev, d in devices.items():
                zones.setdefault(d["zone"], []).append(dev)
            totals = {
                "plants": len(devices),
                "accepted": sum(self._accepted.values()),
                "rejected": sum(self._rejected.values()),
                "needs_water": sum(1 for d in devices.values() if d["status"] == "dry"),
                "alerts": sum(1 for d in devices.values() if d["status"] == "alert"),
            }
            return {
                "devices": devices,
                "zones": zones,
                "totals": totals,
                "meta": dict(self.meta, uptime_s=round(now - self.started), server_time=now),
            }

    def events(self, limit: int = EVENTS_SHOWN) -> List[Dict[str, Any]]:
        with self._lock:
            out = []
            for ev in list(self._events)[:limit]:
                out.append({k: v for k, v in ev.items() if not k.startswith("_")})
            return out


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Smart Plant Monitor</title>
<style>
:root{
  --bg:#f2f5f1; --panel:#ffffff; --ink:#18241b; --muted:#6a766c; --line:#e0e7de; --soft:#f7faf6;
  --healthy:#2f7d3a; --dry:#b7791f; --stale:#7b8680; --alert:#b83232; --info:#2b6cb0;
  --shadow:0 1px 2px rgba(16,24,20,.06),0 4px 14px rgba(16,24,20,.06); color-scheme:light;
}
:root[data-theme="dark"]{
  --bg:#0f1511; --panel:#17201a; --ink:#e7efe6; --muted:#97a398; --line:#263229; --soft:#1c2620;
  --healthy:#5fbf6e; --dry:#e0a84a; --stale:#8a958d; --alert:#ef6b6b; --info:#74a9e6;
  --shadow:none; color-scheme:dark;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#0f1511; --panel:#17201a; --ink:#e7efe6; --muted:#97a398; --line:#263229; --soft:#1c2620;
    --healthy:#5fbf6e; --dry:#e0a84a; --stale:#8a958d; --alert:#ef6b6b; --info:#74a9e6;
    --shadow:none; color-scheme:dark;
  }
}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;font-size:14px}
header{position:sticky;top:0;z-index:5;background:var(--panel);border-bottom:1px solid var(--line);
  padding:12px 24px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.brand{margin-right:auto}
.brand h1{font-size:18px;margin:0}
.brand .sub{color:var(--muted);font-size:12px;margin-top:2px}
.pill{border:1px solid var(--line);border-radius:999px;padding:5px 11px;font-size:12px;color:var(--muted);
  background:var(--soft);white-space:nowrap}
.pill b{color:var(--ink);font-weight:600}
.dot{width:8px;height:8px;border-radius:50%;background:var(--healthy);display:inline-block;margin-right:6px}
.dot.off{background:var(--stale)} .dot.pulse{animation:pulse 2s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(95,191,110,.6)}70%{box-shadow:0 0 0 8px rgba(95,191,110,0)}100%{box-shadow:0 0 0 0 rgba(95,191,110,0)}}
button,select{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line);
  border-radius:8px;padding:6px 10px;cursor:pointer}
button:hover,select:hover{border-color:var(--healthy)}
.tab.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
main{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:20px;padding:20px 24px 40px;align-items:start}
.content{min-width:0;display:flex;flex-direction:column;gap:18px}
@media (max-width:1180px){main{grid-template-columns:1fr} .panel{position:static !important;height:auto !important}}
.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}
@media (max-width:900px){.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;box-shadow:var(--shadow)}
.kpi .v{font-size:24px;font-weight:700;letter-spacing:-.3px}
.kpi .l{color:var(--muted);font-size:12px;margin-top:2px}
.kpi.warn .v{color:var(--dry)} .kpi.bad .v{color:var(--alert)} .kpi.ok .v{color:var(--healthy)}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.chip{border-radius:999px;padding:5px 12px;font-size:12.5px;border:1px solid var(--line);background:var(--panel);cursor:pointer}
.chip.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.spacer{flex:1}
.attention{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--dry);border-radius:12px;
  padding:12px 14px;box-shadow:var(--shadow)}
.attention h2{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.8px;color:var(--muted)}
.attention .list{display:flex;gap:8px;flex-wrap:wrap}
.att{border:1px solid var(--line);border-radius:999px;padding:5px 10px;font-size:12.5px;background:var(--soft);cursor:pointer}
.att.alert{border-color:var(--alert);color:var(--alert)} .att.dry{border-color:var(--dry);color:var(--dry)}
.att.none{color:var(--muted);cursor:default;border-style:dashed}
.zone h2{font-size:12px;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin:4px 2px 10px;
  display:flex;justify-content:space-between}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px 16px;box-shadow:var(--shadow);
  cursor:pointer;position:relative;overflow:hidden;transition:transform .12s ease,border-color .12s ease;display:flex;flex-direction:column}
.card:hover{transform:translateY(-2px);border-color:var(--healthy)}
.card::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--stale)}
.card.healthy::before{background:var(--healthy)} .card.dry::before{background:var(--dry)}
.card.alert::before{background:var(--alert)} .card.stale::before{background:var(--stale)}
.row{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.species{font-weight:650;font-size:15px}
.meta{color:var(--muted);font-size:11.5px;margin-top:2px}
.status{font-size:11.5px;font-weight:600;padding:3px 9px;border-radius:999px;color:#fff;white-space:nowrap}
.status.healthy{background:var(--healthy)} .status.dry{background:var(--dry)}
.status.alert{background:var(--alert)} .status.stale{background:var(--stale)}
.gauge{height:8px;border-radius:6px;background:var(--line);margin:14px 0 6px;position:relative}
.gauge span{display:block;height:100%;border-radius:6px;background:var(--healthy)}
.card.dry .gauge span{background:var(--dry)} .card.alert .gauge span{background:var(--alert)} .card.stale .gauge span{background:var(--stale)}
.gauge i{position:absolute;top:-4px;width:2px;height:16px;background:var(--ink);opacity:.45}
.nums{display:flex;justify-content:space-between;align-items:baseline}
.nums .m{font-size:20px;font-weight:700}
.nums .t{color:var(--muted);font-size:13px}
svg.spark{width:100%;height:40px;display:block;margin-top:8px}
.foot{display:flex;justify-content:space-between;color:var(--muted);font-size:11px;margin-top:auto;padding-top:6px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);
  position:sticky;top:76px;height:calc(100vh - 96px);display:flex;flex-direction:column;min-height:0}
.panel-hd{padding:12px 14px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:8px}
.panel-hd h3{margin:0;font-size:14px}
.panel-hd .small{font-size:12px;padding:4px 8px}
.filters{display:flex;gap:6px;padding:10px 14px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.filters .chip{padding:3px 10px;font-size:12px}
.events{flex:1;min-height:0;overflow:auto;padding:4px 0}
.ev{display:grid;grid-template-columns:10px 1fr auto;gap:10px;padding:9px 14px;border-bottom:1px solid var(--line);align-items:start}
.ev:last-child{border-bottom:none}
.ev .d{width:8px;height:8px;border-radius:50%;margin-top:6px;background:var(--muted)}
.ev.warn .d{background:var(--dry)} .ev.bad .d{background:var(--alert)}
.ev.ok .d{background:var(--healthy)} .ev.info .d{background:var(--info)}
.ev .who{font-weight:600;font-size:12.5px}
.ev .who button.link{all:unset;cursor:pointer;color:var(--info)}
.ev .msg{color:var(--muted);font-size:12px;margin-top:1px}
.ev .when{color:var(--muted);font-size:11px;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.ev .cnt{display:inline-block;margin-left:6px;background:var(--alert);color:#fff;border-radius:999px;padding:0 6px;font-size:10.5px}
.ev.old{opacity:.5}
.empty{color:var(--muted);padding:22px;text-align:center}
.modal{position:fixed;inset:0;background:rgba(10,15,12,.55);display:none;align-items:center;justify-content:center;z-index:20;padding:20px}
.modal.open{display:flex}
.sheet{background:var(--panel);border:1px solid var(--line);border-radius:16px;max-width:980px;width:100%;max-height:92vh;
  overflow:auto;padding:22px 24px;box-shadow:0 20px 60px rgba(0,0,0,.35)}
.sheet .hd{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.sheet h2{margin:0;font-size:20px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:16px 0}
.stat{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.stat .v{font-size:18px;font-weight:700} .stat .l{color:var(--muted);font-size:11.5px}
.chart{margin-top:12px}
.chart h4{margin:0 0 4px;font-size:12px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.6px}
svg.big{width:100%;height:220px;display:block}
svg.big .grid-l{stroke:var(--line);stroke-width:1} svg.big .ax{fill:var(--muted);font-size:11px}
svg.big .thr{stroke:var(--dry);stroke-dasharray:5 5;stroke-width:1.5}
svg.big .ln{fill:none;stroke:var(--healthy);stroke-width:2.2;stroke-linejoin:round}
svg.big .area{fill:var(--healthy);opacity:.12}
svg.big .tln{fill:none;stroke:var(--info);stroke-width:2}
footer{padding:0 24px 24px;color:var(--muted);font-size:12px}
</style>
</head>
<body>
<header>
  <div class="brand">
    <h1>Smart Plant Monitor</h1>
    <div class="sub" id="site">Site overview</div>
  </div>
  <span class="pill"><span class="dot pulse" id="livedot"></span><span id="livetext">Connecting</span></span>
  <span class="pill">Cipher <b id="cipher">n/a</b></span>
  <span class="pill">Replay protection <b id="replay">n/a</b></span>
  <span class="pill">Uptime <b id="uptime">0 s</b></span>
  <button id="theme" title="Toggle colour theme">Theme</button>
</header>

<main>
  <div class="content">
    <section class="kpis" id="kpis"></section>
    <section class="attention" id="attention"></section>
    <div class="bar">
      <span class="chip on" data-zone="all">All zones</span>
      <span id="zonechips" style="display:contents"></span>
      <span class="spacer"></span>
      <select id="sort" aria-label="Sort plants">
        <option value="urgent">Most urgent first</option>
        <option value="name">Name</option>
        <option value="moisture">Moisture, low to high</option>
      </select>
      <select id="statusfilter" aria-label="Filter by status">
        <option value="all">All statuses</option>
        <option value="dry">Needs water</option>
        <option value="alert">Alerts</option>
        <option value="stale">No recent data</option>
        <option value="healthy">Healthy</option>
      </select>
    </div>
    <div id="zones" style="display:flex;flex-direction:column;gap:20px"></div>
  </div>

  <aside class="panel" aria-label="Event log">
    <div class="panel-hd">
      <h3>Event log</h3>
      <button class="small" id="clearlog" title="Hide events received so far">Clear</button>
    </div>
    <div class="filters" id="evfilters"></div>
    <div class="events" id="events"><div class="empty">Waiting for events...</div></div>
  </aside>
</main>

<footer>
  The dashed line on each chart marks the dry threshold. Rejected messages are grouped into one security event per burst.
  Events older than ten minutes are faded.
</footer>

<div class="modal" id="modal" role="dialog" aria-modal="true" aria-labelledby="mtitle">
  <div class="sheet" id="sheet"></div>
</div>

<script>
const ICON = {healthy:"\u{1F331}", dry:"\u{1F940}", stale:"\u23F3", alert:"\u{1F6A8}"};
const LABEL = {healthy:"Healthy", dry:"Needs water", stale:"No recent data", alert:"Alert"};
const EV_KINDS = [["all","All"],["security","Security"],["water","Watering"],["status","Status"]];
const S = {data:null, events:[], zone:"all", status:"all", sort:"urgent", online:false, lastOk:0,
           open:null, evKind:"all", clearedBefore:0};
const esc = v => String(v).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pct = v => v==null ? "n/a" : v.toFixed(1)+"%";
const nowS = () => Date.now()/1000;

function ago(t){
  const s = Math.max(0, Math.round(nowS()-t));
  if(s<60) return s+" s ago";
  if(s<3600) return Math.round(s/60)+" min ago";
  return Math.round(s/3600)+" h ago";
}
function clock(t){ return new Date(t*1000).toLocaleTimeString([], {hour:"2-digit", minute:"2-digit", second:"2-digit"}); }

function spark(values, dry){
  if(!values || values.length<2) return "";
  const w=300,h=40,n=values.length;
  const x=i=>(i/(n-1))*w, y=v=>h-(Math.min(100,Math.max(0,v))/100)*h;
  const pts=values.map((v,i)=>x(i).toFixed(1)+","+y(v).toFixed(1)).join(" ");
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
    <line x1="0" x2="${w}" y1="${y(dry)}" y2="${y(dry)}" stroke="var(--dry)" stroke-dasharray="3 3" stroke-width="1"/>
    <polyline fill="none" stroke="var(--healthy)" stroke-width="1.6" points="${pts}"/></svg>`;
}

function bigChart(values, opts){
  const W=860,H=220,pl=44,pr=14,pt=12,pb=26;
  const cw=W-pl-pr, ch=H-pt-pb, min=opts.min, max=opts.max, n=values.length;
  if(n<2) return `<div class="empty">Collecting readings...</div>`;
  const x=i=>pl+(i/(n-1))*cw, y=v=>pt+ch-((v-min)/(max-min))*ch;
  const pts=values.map((v,i)=>x(i).toFixed(1)+","+y(v).toFixed(1)).join(" ");
  const area=`${x(0).toFixed(1)},${pt+ch} ${pts} ${x(n-1).toFixed(1)},${pt+ch}`;
  let grid="", labels="";
  for(let k=0;k<=4;k++){
    const v=min+(k/4)*(max-min), yy=y(v);
    grid+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${yy}" y2="${yy}"/>`;
    labels+=`<text class="ax" x="${pl-8}" y="${yy+4}" text-anchor="end">${v.toFixed(0)}${opts.unit}</text>`;
  }
  (opts.xlabels||[]).forEach((t,i,arr)=>{
    const idx=Math.round(i*(n-1)/Math.max(1,arr.length-1));
    labels+=`<text class="ax" x="${x(idx)}" y="${H-6}" text-anchor="middle">${t}</text>`;
  });
  const thr = opts.threshold!=null ? `<line class="thr" x1="${pl}" x2="${W-pr}" y1="${y(opts.threshold)}" y2="${y(opts.threshold)}"/>` : "";
  return `<svg class="big" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${esc(opts.label)}">
    ${grid}${thr}${opts.fill?`<polygon class="area" points="${area}"/>`:""}
    <polyline class="${opts.cls||'ln'}" points="${pts}"/>${labels}</svg>`;
}

function urgencyKey(d){
  const order = {alert:0, dry:1, stale:2, healthy:3};
  return [order[d.status], d.margin==null ? 1e9 : d.margin];
}
function sortDevices(list){
  const mode = S.sort;
  return list.slice().sort((a,b)=>{
    if(mode==="name") return a.species.localeCompare(b.species);
    if(mode==="moisture") return (a.moisture??1e9)-(b.moisture??1e9);
    const [sa,ma]=urgencyKey(a), [sb,mb]=urgencyKey(b);
    return sa-sb || ma-mb || a.species.localeCompare(b.species);
  });
}

function renderCard(d){
  const w = d.moisture==null ? 0 : Math.min(100, Math.max(0, d.moisture));
  const age = d.seconds_since_reading==null ? "never" : Math.round(d.seconds_since_reading)+" s ago";
  const margin = d.margin==null ? "" : (d.margin>=0 ? "+"+d.margin.toFixed(1) : d.margin.toFixed(1))+" pts vs dry";
  return `<article class="card ${d.status}" data-id="${esc(d.id)}" tabindex="0" role="button" aria-label="Open ${esc(d.species)}">
    <div class="row">
      <div><div class="species">${esc(d.species)}</div><div class="meta">${esc(d.id)} | dry at ${d.dry_at}%</div></div>
      <span class="status ${d.status}">${ICON[d.status]} ${LABEL[d.status]}</span>
    </div>
    <div class="gauge"><span style="width:${w}%"></span><i style="left:calc(${d.dry_at}% - 1px)"></i></div>
    <div class="nums"><span class="m">${pct(d.moisture)}</span><span class="t">${d.temp_c==null?"n/a":d.temp_c.toFixed(1)+" C"}</span></div>
    <div class="meta">${margin}</div>
    ${spark(d.history, d.dry_at)}
    <div class="foot"><span>${age}</span><span>${d.rejected_total ? d.rejected_total+" rejected" : "verified"}</span></div>
  </article>`;
}

function renderAttention(){
  const el=document.getElementById("attention"); const d=S.data;
  if(!d){ el.innerHTML=""; return; }
  const urgent = Object.values(d.devices)
    .filter(x=>x.status==="dry"||x.status==="alert")
    .sort((a,b)=>urgencyKey(a)[0]-urgencyKey(b)[0] || urgencyKey(a)[1]-urgencyKey(b)[1]).slice(0,6);
  const chips = urgent.length
    ? urgent.map(x=>`<button class="att ${x.status}" data-id="${esc(x.id)}">${ICON[x.status]} ${esc(x.species)} ${pct(x.moisture)}</button>`).join("")
    : `<span class="att none">${ICON.healthy} Every plant is above its dry threshold</span>`;
  el.innerHTML = `<h2>Needs attention (${urgent.length})</h2><div class="list">${chips}</div>`;
}

function renderZones(){
  const d=S.data; if(!d) return;
  const zones = Object.keys(d.zones).sort();
  const html = zones.filter(z => S.zone==="all" || S.zone===z).map(z=>{
    const plants = sortDevices(d.zones[z].map(id=>d.devices[id]))
      .filter(x => S.status==="all" || x.status===S.status);
    if(!plants.length) return "";
    return `<section class="zone"><h2><span>${esc(z)}</span><span>${plants.length} plant${plants.length===1?"":"s"}</span></h2>
      <div class="grid">${plants.map(renderCard).join("")}</div></section>`;
  }).join("");
  document.getElementById("zones").innerHTML = html || `<div class="empty">No plants match these filters.</div>`;
}

function renderChips(){
  const d=S.data; if(!d) return;
  const zones = Object.keys(d.zones).sort();
  document.getElementById("zonechips").innerHTML = zones.map(z=>
    `<span class="chip ${S.zone===z?"on":""}" data-zone="${esc(z)}">${esc(z)}</span>`).join("");
  document.querySelector(".bar .chip[data-zone='all']").classList.toggle("on", S.zone==="all");
}

function renderKpis(){
  const d=S.data; if(!d) return;
  const t=d.totals;
  const vals=Object.values(d.devices).map(x=>x.moisture).filter(x=>x!=null);
  const avg = vals.length ? vals.reduce((a,b)=>a+b,0)/vals.length : null;
  const k=[
    ["Plants monitored", t.plants, ""],
    ["Need water", t.needs_water, t.needs_water? "warn":"ok"],
    ["Average moisture", pct(avg), ""],
    ["Messages verified", t.accepted.toLocaleString(), "ok"],
    ["Replays blocked", t.rejected, t.rejected? "bad":""],
  ];
  document.getElementById("kpis").innerHTML = k.map(([l,v,c])=>
    `<div class="kpi ${c}"><div class="v">${esc(v)}</div><div class="l">${esc(l)}</div></div>`).join("");
}

function renderEvents(){
  const filters=document.getElementById("evfilters");
  filters.innerHTML = EV_KINDS.map(([k,l])=>`<span class="chip ${S.evKind===k?"on":""}" data-kind="${k}">${l}</span>`).join("");
  const el=document.getElementById("events");
  const list = S.events.filter(e => e.time > S.clearedBefore && (S.evKind==="all" || e.kind===S.evKind));
  if(!list.length){ el.innerHTML=`<div class="empty">${S.events.length? "Nothing to show for this filter." : "No events yet."}</div>`; return; }
  el.innerHTML = list.map(e=>{
    const old = (nowS()-e.last_time) > 600 ? " old" : "";
    const who = e.device==="site" ? esc(e.kind==="security" ? "Security" : "Site")
              : `<button class="link" data-id="${esc(e.device)}">${esc(e.device)}</button>`;
    const cnt = e.count>1 ? `<span class="cnt">x${e.count}</span>` : "";
    return `<div class="ev ${e.level}${old}">
      <span class="d"></span>
      <div><div class="who">${who}${cnt}</div><div class="msg">${esc(e.message)}</div></div>
      <div class="when" title="${clock(e.last_time)}">${ago(e.last_time)}</div>
    </div>`;
  }).join("");
}

function renderHeader(){
  const d=S.data;
  const dot=document.getElementById("livedot"), txt=document.getElementById("livetext");
  if(S.online){ dot.className="dot pulse"; txt.textContent="Live"; }
  else { dot.className="dot off";
         txt.textContent = S.lastOk ? "Offline, last update "+Math.round((Date.now()-S.lastOk)/1000)+" s ago" : "Gateway not reachable"; }
  if(!d) return;
  document.getElementById("site").textContent = d.totals.plants+" plants across "+Object.keys(d.zones).length+" zones";
  document.getElementById("cipher").textContent = d.meta.mode||"n/a";
  document.getElementById("replay").textContent = d.meta.replay_protection===false?"off":"on";
  document.getElementById("uptime").textContent = d.meta.uptime_s+" s";
}

function render(){ renderHeader(); renderChips(); renderKpis(); renderAttention(); renderZones(); renderEvents(); renderModal(); }

function openDevice(id){ if(!S.data || !S.data.devices[id]) return; S.open=id; renderModal();
  document.getElementById("modal").classList.add("open"); }
function closeDevice(){ S.open=null; document.getElementById("modal").classList.remove("open"); }

function renderModal(){
  if(!S.open || !S.data) return;
  const d=S.data.devices[S.open]; if(!d) return;
  const n=d.history.length;
  const labels=[]; for(let i=0;i<5;i++) labels.push(stepLabel(n,i));
  const mine=S.events.filter(e=>e.device===d.id).slice(0,10);
  const tmin=Math.floor(Math.min(...d.temp_history,10)-2), tmax=Math.ceil(Math.max(...d.temp_history,25)+2);
  document.getElementById("sheet").innerHTML = `
    <div class="hd">
      <div><h2 id="mtitle">${esc(d.species)}</h2>
        <div class="meta">${esc(d.id)} | ${esc(d.zone)} | dry threshold ${d.dry_at}% | ${LABEL[d.status]}</div></div>
      <button onclick="closeDevice()" aria-label="Close">Close</button>
    </div>
    <div class="stats">
      <div class="stat"><div class="v">${pct(d.moisture)}</div><div class="l">Current moisture</div></div>
      <div class="stat"><div class="v">${pct(d.min)}</div><div class="l">Lowest (last 24 h)</div></div>
      <div class="stat"><div class="v">${pct(d.max)}</div><div class="l">Highest (last 24 h)</div></div>
      <div class="stat"><div class="v">${pct(d.mean)}</div><div class="l">Mean (last 24 h)</div></div>
      <div class="stat"><div class="v">${d.accepted_total}</div><div class="l">Verified messages</div></div>
      <div class="stat"><div class="v">${d.rejected_total}</div><div class="l">Rejected messages</div></div>
    </div>
    <div class="chart"><h4>Soil moisture</h4>
      ${bigChart(d.history,{min:0,max:100,unit:"%",threshold:d.dry_at,fill:true,label:"Soil moisture history",xlabels:labels})}</div>
    <div class="chart"><h4>Air temperature</h4>
      ${bigChart(d.temp_history,{min:tmin,max:tmax,unit:"C",cls:"tln",label:"Air temperature history",xlabels:labels})}</div>
    <div class="chart"><h4>Recent events for this plant</h4>
      ${mine.length ? mine.map(e=>`<div class="ev ${e.level}" style="padding:7px 0"><span class="d"></span>
        <div><div class="who">${esc(e.message)}${e.count>1?` <span class="cnt">x${e.count}</span>`:""}</div></div>
        <div class="when">${ago(e.last_time)}</div></div>`).join("")
        : '<div class="empty">No events for this plant yet.</div>'}
    </div>`;
}

function stepLabel(n,i){
  const mins=Math.round(n*10*(1-i/4)), h=Math.floor(mins/60), m=mins%60;
  return i===4 ? "now" : "-"+h+"h"+(m?" "+m+"m":"");
}

async function poll(){
  try{
    const [sr, er] = await Promise.all([fetch('/state',{cache:'no-store'}), fetch('/events',{cache:'no-store'})]);
    if(!sr.ok || !er.ok) throw new Error("bad status");
    S.data = await sr.json();
    S.events = await er.json();
    S.online = true; S.lastOk = Date.now();
  }catch(e){ S.online = false; }
  render();
}

document.addEventListener("click", e=>{
  const kind=e.target.closest("[data-kind]");
  if(kind){ S.evKind=kind.dataset.kind; renderEvents(); return; }
  const chip=e.target.closest(".bar .chip[data-zone]");
  if(chip){ S.zone=chip.dataset.zone; render(); return; }
  const link=e.target.closest("button.link[data-id], button.att[data-id]");
  if(link){ openDevice(link.dataset.id); return; }
  const card=e.target.closest(".card[data-id]");
  if(card){ openDevice(card.dataset.id); return; }
  if(e.target.id==="modal"){ closeDevice(); }
});
document.addEventListener("keydown", e=>{
  if(e.key==="Escape") closeDevice();
  if(e.key==="Enter" && e.target.classList && e.target.classList.contains("card")) openDevice(e.target.dataset.id);
});
document.getElementById("statusfilter").addEventListener("change", e=>{ S.status=e.target.value; render(); });
document.getElementById("sort").addEventListener("change", e=>{ S.sort=e.target.value; render(); });
document.getElementById("clearlog").addEventListener("click", ()=>{ S.clearedBefore = nowS(); renderEvents(); });
document.getElementById("theme").addEventListener("click", ()=>{
  const root=document.documentElement;
  const dark = root.getAttribute("data-theme")==="dark" || (!root.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
  root.setAttribute("data-theme", dark ? "light" : "dark");
});

poll(); setInterval(poll, 2000);
setInterval(()=>{ renderHeader(); renderEvents(); }, 1000);
</script>
</body>
</html>
"""


def make_handler(monitor: Monitor) -> Type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.startswith("/state"):
                body = json.dumps(monitor.snapshot()).encode()
                ctype = "application/json"
            elif self.path.startswith("/events"):
                body = json.dumps(monitor.events()).encode()
                ctype = "application/json"
            else:
                body = PAGE.encode("utf-8")
                ctype = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            pass  # keep the console quiet

    return Handler


def serve(monitor: Monitor, port: int = 8080) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", port), make_handler(monitor))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server