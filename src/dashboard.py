"""Live plant dashboard: status cards, moisture history, and security summary.

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].
Open http://localhost:8080 while run_live.py is running. /state returns JSON.
"""
import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer

DRY_THRESHOLD = 30.0      # percent moisture below which a plant is shown as needing water
STALE_AFTER_S = 15.0      # no reading for this long -> no recent data
ALERT_WINDOW_S = 10.0     # a rejection within this window raises an alert
HISTORY_LEN = 120         # readings kept per device for the sparkline


def plant_status(reading, last_seen, now, recent_rejections):
    """Return one of: healthy, dry, stale, alert. Pure function so it can be tested."""
    if recent_rejections > 0:
        return "alert"
    if reading is None or now - last_seen > STALE_AFTER_S:
        return "stale"
    if reading["moisture"] < DRY_THRESHOLD:
        return "dry"
    return "healthy"


class Monitor:
    """Thread-safe store: latest reading, history, and message counters per device."""

    def __init__(self, meta=None):
        self._lock = threading.Lock()
        self._latest = {}                 # device -> (reading, time received)
        self._history = {}                # device -> deque of moisture values
        self._rejected = {}               # device -> rejected count
        self._accepted = {}               # device -> accepted count
        self._alerts = deque()            # (device, time) of recent rejections
        self.meta = meta or {}
        self.started = time.time()

    def record_accept(self, device, reading):
        with self._lock:
            self._latest[device] = (reading, time.time())
            self._accepted[device] = self._accepted.get(device, 0) + 1
            hist = self._history.setdefault(device, deque(maxlen=HISTORY_LEN))
            hist.append(reading["moisture"])

    def record_reject(self, device):
        with self._lock:
            self._rejected[device] = self._rejected.get(device, 0) + 1
            self._alerts.append((device, time.time()))

    def snapshot(self):
        now = time.time()
        with self._lock:
            while self._alerts and now - self._alerts[0][1] > ALERT_WINDOW_S:
                self._alerts.popleft()
            devices = {}
            for dev in sorted(set(self._latest) | set(self._rejected)):
                reading, seen = self._latest.get(dev, (None, 0))
                recent = sum(1 for d, _ in self._alerts if d == dev)
                devices[dev] = {
                    "status": plant_status(reading, seen, now, recent),
                    "moisture": reading["moisture"] if reading else None,
                    "temp_c": reading["temp_c"] if reading else None,
                    "seconds_since_reading": round(now - seen, 1) if reading else None,
                    "history": list(self._history.get(dev, [])),
                    "accepted_total": self._accepted.get(dev, 0),
                    "rejected_total": self._rejected.get(dev, 0),
                }
            totals = {
                "accepted": sum(self._accepted.values()),
                "rejected": sum(self._rejected.values()),
            }
            return {
                "devices": devices,
                "totals": totals,
                "meta": dict(self.meta, uptime_s=round(now - self.started)),
                "thresholds": {"dry": DRY_THRESHOLD, "stale_after_s": STALE_AFTER_S},
            }


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Smart Plant Monitor</title>
<style>
:root{--bg:#f3f6f2;--card:#fff;--ink:#1d2b1f;--muted:#6b766d;--line:#dfe6dc;
--healthy:#2f7d3a;--dry:#b7791f;--stale:#6b766d;--alert:#b83232}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink)}
header{padding:1.5rem 2rem;display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:1rem;
border-bottom:1px solid var(--line);background:#fff}
h1{margin:0;font-size:1.7rem}
.sub{color:var(--muted);font-size:.9rem;margin-top:.2rem}
.pills{display:flex;gap:.5rem;flex-wrap:wrap}
.pill{background:var(--bg);border:1px solid var(--line);border-radius:999px;padding:.3rem .8rem;font-size:.85rem}
main{padding:1.5rem 2rem}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:1rem;margin-bottom:1.5rem}
.stat{background:var(--card);border-radius:12px;padding:1rem 1.2rem;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.stat .n{font-size:1.6rem;font-weight:700}.stat .l{color:var(--muted);font-size:.85rem}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1.2rem}
.card{background:var(--card);border-radius:14px;padding:1.2rem 1.3rem;box-shadow:0 1px 4px rgba(0,0,0,.07);
border-top:5px solid var(--stale)}
.card.healthy{border-top-color:var(--healthy)}.card.dry{border-top-color:var(--dry)}
.card.alert{border-top-color:var(--alert)}.card.stale{border-top-color:var(--stale)}
.top{display:flex;justify-content:space-between;align-items:center}
.icon{font-size:2.6rem;line-height:1}
.name{font-weight:700;font-size:1.1rem}
.badge{display:inline-block;border-radius:999px;padding:.15rem .6rem;font-size:.8rem;color:#fff;margin-top:.3rem}
.badge.healthy{background:var(--healthy)}.badge.dry{background:var(--dry)}
.badge.alert{background:var(--alert)}.badge.stale{background:var(--stale)}
.gauge{height:10px;background:var(--line);border-radius:6px;overflow:hidden;margin:.9rem 0 .3rem}
.gauge span{display:block;height:100%;border-radius:6px;background:var(--healthy)}
.card.dry .gauge span{background:var(--dry)}.card.alert .gauge span{background:var(--alert)}
.readings{display:flex;justify-content:space-between;font-size:.95rem}
.muted{color:var(--muted);font-size:.8rem}
svg.spark{width:100%;height:60px;margin-top:.7rem}
footer{color:var(--muted);font-size:.8rem;padding:0 2rem 2rem}
</style></head>
<body>
<header>
  <div><h1>Smart Plant Monitor</h1><div class="sub" id="sub">Connecting to gateway...</div></div>
  <div class="pills" id="pills"></div>
</header>
<main>
  <div class="summary" id="summary"></div>
  <div class="grid" id="cards"></div>
</main>
<footer>Moisture is shown against the dry threshold (dashed line). Statuses update every 2 seconds.</footer>
<script>
const ICON = {healthy:"\\u{1F331}", dry:"\\u{1F940}", stale:"\\u231B", alert:"\\u{1F6A8}"};
const LABEL = {healthy:"Healthy", dry:"Needs water", stale:"No recent data", alert:"Replay or tamper detected"};
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function spark(hist, dry){
  if(!hist.length) return "";
  const w=240, h=60, n=hist.length;
  const x = i => n<2 ? w : (i/(n-1))*w;
  const y = v => h - (Math.min(100,Math.max(0,v))/100)*h;
  const pts = hist.map((v,i)=>`${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const ty = y(dry).toFixed(1);
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <line x1="0" x2="${w}" y1="${ty}" y2="${ty}" stroke="#b7791f" stroke-dasharray="4 4" stroke-width="1"/>
    <polyline fill="none" stroke="#2f7d3a" stroke-width="2" points="${pts}"/></svg>`;
}

function card(name, d, dry){
  const m = d.moisture==null ? null : d.moisture;
  const t = d.temp_c==null ? "n/a" : d.temp_c.toFixed(1)+" C";
  const age = d.seconds_since_reading==null ? "never" : d.seconds_since_reading.toFixed(0)+" s ago";
  const width = m==null ? 0 : Math.min(100, Math.max(0, m));
  return `<div class="card ${d.status}">
    <div class="top"><div class="icon">${ICON[d.status]}</div>
      <div style="text-align:right"><div class="name">${esc(name)}</div>
      <span class="badge ${d.status}">${LABEL[d.status]}</span></div></div>
    <div class="gauge"><span style="width:${width}%"></span></div>
    <div class="readings"><b>${m==null?"n/a":m.toFixed(1)+"%"}</b><span>${t}</span></div>
    <div class="muted">Last reading ${age} | accepted ${d.accepted_total} | rejected ${d.rejected_total}</div>
    ${spark(d.history, dry)}
  </div>`;
}

async function refresh(){
  try{
    const r = await fetch("/state", {cache:"no-store"});
    const s = await r.json();
    const names = Object.keys(s.devices);
    const dry = s.thresholds.dry;
    document.getElementById("cards").innerHTML =
      names.length ? names.map(n=>card(n, s.devices[n], dry)).join("")
                   : '<div class="muted">Waiting for the first sensor message...</div>';
    const sum = s.totals;
    document.getElementById("summary").innerHTML = [
      [names.length,"Plants monitored"],
      [sum.accepted,"Messages verified"],
      [sum.rejected,"Messages rejected"],
      [s.meta.uptime_s+" s","Gateway uptime"]
    ].map(([n,l])=>`<div class="stat"><div class="n">${esc(n)}</div><div class="l">${esc(l)}</div></div>`).join("");
    document.getElementById("pills").innerHTML =
      `<span class="pill">Cipher: ${esc(s.meta.mode||"n/a")}</span>
       <span class="pill">Replay protection: ${s.meta.replay_protection===false?"off":"on"}</span>`;
    document.getElementById("sub").textContent = "Live from the gateway. Dry threshold " + dry + "%.";
  }catch(e){
    document.getElementById("sub").textContent = "Gateway not reachable. Is run_live.py running?";
  }
}
refresh(); setInterval(refresh, 2000);
</script>
</body></html>
"""


def make_handler(monitor):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/state"):
                body = json.dumps(monitor.snapshot()).encode()
                ctype = "application/json"
            else:
                body = PAGE.encode()
                ctype = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            pass

    return Handler


def serve(monitor, port=8080):
    server = HTTPServer(("127.0.0.1", port), make_handler(monitor))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
