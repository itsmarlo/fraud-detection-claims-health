"""WanderPlan: a dependency-free local travel planning web app."""

from __future__ import annotations

import json
import threading
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


HOST = "127.0.0.1"
PORT = 8000
DATA_FILE = Path(__file__).with_name("trips.json")

DESTINATIONS = [
    {"city": "Barcelona", "country": "Spain", "daily_cost": 145, "tags": ["Beach", "Food", "Architecture"], "tip": "Book Sagrada Família tickets before you travel.", "emoji": "🌊"},
    {"city": "Berlin", "country": "Germany", "daily_cost": 125, "tags": ["History", "Nightlife", "Museums"], "tip": "A day transit pass is useful when visiting several districts.", "emoji": "🏛️"},
    {"city": "Kyoto", "country": "Japan", "daily_cost": 135, "tags": ["Temples", "Gardens", "Culture"], "tip": "Visit popular temples early for a quieter experience.", "emoji": "⛩️"},
    {"city": "Lisbon", "country": "Portugal", "daily_cost": 105, "tags": ["Views", "Food", "Coast"], "tip": "Wear comfortable shoes—the historic streets are steep.", "emoji": "🚋"},
    {"city": "New York", "country": "United States", "daily_cost": 245, "tags": ["Theatre", "Food", "City life"], "tip": "Group nearby sights together to save travel time.", "emoji": "🗽"},
    {"city": "Reykjavík", "country": "Iceland", "daily_cost": 225, "tags": ["Nature", "Hot springs", "Adventure"], "tip": "Pack waterproof layers even during summer.", "emoji": "♨️"},
]

PAGE = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>WanderPlan</title>
  <style>
    :root{--ink:#173f3a;--muted:#60736f;--brand:#0f766e;--pale:#e8f3f1;--bg:#f5f7f6;--card:#fff;--line:#dce5e2}
    *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,sans-serif}
    header{padding:42px max(5vw,24px) 28px;background:linear-gradient(135deg,#d8eee9,#f3eadb)}
    header h1{font-size:clamp(32px,5vw,52px);margin:0;letter-spacing:-2px} header p{color:var(--muted);font-size:17px;margin:5px 0 0}
    nav{display:flex;gap:8px;padding:14px max(5vw,24px);background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:3}
    nav button{border:0;background:transparent;padding:10px 16px;border-radius:99px;font-weight:700;color:var(--muted);cursor:pointer}
    nav button.active{background:var(--pale);color:var(--brand)} main{max-width:1150px;margin:30px auto;padding:0 24px 50px}
    .view{display:none}.view.active{display:block}.search{display:flex;gap:10px;margin-bottom:20px}.search input{flex:1}
    input,select,textarea{width:100%;padding:12px 13px;border:1px solid var(--line);border-radius:10px;background:white;font:inherit;color:var(--ink)}
    button.primary{border:0;border-radius:10px;background:var(--brand);color:white;padding:12px 18px;font-weight:750;cursor:pointer} button.primary:hover{background:#115e59}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:0 4px 20px #173f3a0a}
    .hero-icon{font-size:35px}.card h3{font-size:20px;margin:8px 0 4px}.muted{color:var(--muted)}.tags{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}
    .tag{background:var(--pale);color:var(--brand);padding:4px 9px;border-radius:99px;font-size:12px;font-weight:700}.cost{font-weight:800;margin:12px 0}.tip{min-height:45px;font-size:13px;color:var(--muted)}
    .planner{max-width:720px;margin:auto}.planner h2,.saved-head h2{margin-top:0}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:15px}.field.full{grid-column:1/-1}.field label{display:block;font-weight:700;margin-bottom:5px}
    .estimate{background:var(--pale);padding:18px;border-radius:12px;margin:18px 0;display:flex;justify-content:space-between;align-items:center}.estimate strong{font-size:25px}
    .saved-head{display:flex;justify-content:space-between;align-items:center}.trip{display:grid;grid-template-columns:1.5fr 1.3fr .6fr .8fr auto;gap:15px;align-items:center}.trip+.trip{margin-top:10px}.trip strong{display:block}
    .delete{border:1px solid #e7c7c7;background:#fff4f4;color:#9c3232;padding:8px 11px;border-radius:9px;cursor:pointer}.empty{text-align:center;padding:55px 20px;color:var(--muted)}
    #toast{position:fixed;right:24px;bottom:24px;background:var(--ink);color:white;padding:12px 18px;border-radius:10px;opacity:0;transform:translateY(10px);transition:.2s;pointer-events:none}#toast.show{opacity:1;transform:none}
    @media(max-width:700px){.form-grid{grid-template-columns:1fr}.field.full{grid-column:auto}.trip{grid-template-columns:1fr 1fr}.trip .delete{grid-column:1/-1}.saved-head{align-items:flex-start;flex-direction:column}}
  </style>
</head>
<body>
<header><h1>WanderPlan</h1><p>Discover a destination and turn it into a trip.</p></header>
<nav><button class="active" data-view="explore">Explore</button><button data-view="planner">Plan a trip</button><button data-view="saved">Saved trips</button></nav>
<main>
  <section id="explore" class="view active"><div class="search"><input id="search" placeholder="Search by city, country, or interest"><button class="primary" onclick="renderDestinations()">Search</button></div><div id="destinations" class="grid"></div></section>
  <section id="planner" class="view"><form id="trip-form" class="card planner"><h2>Create your itinerary</h2><div class="form-grid">
    <div class="field full"><label for="destination">Destination</label><select id="destination" required></select></div>
    <div class="field"><label for="start">Start date</label><input id="start" type="date" required></div>
    <div class="field"><label for="end">End date</label><input id="end" type="date" required></div>
    <div class="field"><label for="travelers">Travelers</label><input id="travelers" type="number" min="1" max="20" value="1" required></div>
    <div class="field full"><label for="notes">Notes</label><textarea id="notes" rows="5" placeholder="Ideas, reservations, places to visit..."></textarea></div>
  </div><div class="estimate"><span>Estimated local budget</span><strong id="estimate">€0</strong></div><button class="primary" type="submit">Save trip</button></form></section>
  <section id="saved" class="view"><div class="saved-head"><h2>Your saved trips</h2><p class="muted">Stored on this computer</p></div><div id="trips"></div></section>
</main><div id="toast"></div>
<script>
let destinations=[];
const euro=new Intl.NumberFormat('en',{style:'currency',currency:'EUR',maximumFractionDigits:0});
const el=id=>document.getElementById(id);
function showView(id){document.querySelectorAll('.view').forEach(x=>x.classList.toggle('active',x.id===id));document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('active',x.dataset.view===id));if(id==='saved')loadTrips()}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>showView(b.dataset.view));
function toast(message){el('toast').textContent=message;el('toast').classList.add('show');setTimeout(()=>el('toast').classList.remove('show'),2200)}
async function init(){destinations=await fetch('/api/destinations').then(r=>r.json());el('destination').innerHTML=destinations.map((d,i)=>`<option value="${i}">${d.city}, ${d.country}</option>`).join('');const today=new Date().toISOString().slice(0,10);el('start').value=today;el('end').value=today;renderDestinations();updateEstimate()}
function renderDestinations(){const q=el('search').value.trim().toLowerCase();const found=destinations.filter(d=>JSON.stringify(d).toLowerCase().includes(q));el('destinations').innerHTML=found.length?found.map(d=>{const i=destinations.indexOf(d);return `<article class="card"><div class="hero-icon">${d.emoji}</div><h3>${d.city}, ${d.country}</h3><div class="tags">${d.tags.map(t=>`<span class="tag">${t}</span>`).join('')}</div><div class="cost">About ${euro.format(d.daily_cost)} / day / traveler</div><p class="tip">Tip: ${d.tip}</p><button class="primary" onclick="plan(${i})">Plan this trip</button></article>`}).join(''):'<div class="card empty">No destinations found. Try another search.</div>'}
function plan(i){el('destination').value=i;updateEstimate();showView('planner')}
function updateEstimate(){const start=new Date(el('start').value+'T00:00:00');const end=new Date(el('end').value+'T00:00:00');const people=Number(el('travelers').value)||0;const days=Math.max(1,Math.round((end-start)/86400000));const d=destinations[Number(el('destination').value)];el('estimate').textContent=d&&days>0?euro.format(days*people*d.daily_cost):'—'}
['destination','start','end','travelers'].forEach(id=>el(id).addEventListener('input',updateEstimate));el('search').addEventListener('keydown',e=>{if(e.key==='Enter')renderDestinations()});
el('trip-form').onsubmit=async e=>{e.preventDefault();const body={destination_index:Number(el('destination').value),start_date:el('start').value,end_date:el('end').value,travelers:Number(el('travelers').value),notes:el('notes').value};const response=await fetch('/api/trips',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await response.json();if(!response.ok){toast(result.error);return}el('notes').value='';toast('Trip saved');showView('saved')};
async function loadTrips(){const trips=await fetch('/api/trips').then(r=>r.json());el('trips').innerHTML=trips.length?trips.map(t=>`<article class="card trip"><div><strong>${t.destination}</strong><span class="muted">${t.notes||'No notes yet'}</span></div><div><strong>${t.start_date} → ${t.end_date}</strong><span class="muted">Travel dates</span></div><div><strong>${t.travelers}</strong><span class="muted">Travelers</span></div><div><strong>${euro.format(t.estimated_budget)}</strong><span class="muted">Estimate</span></div><button class="delete" onclick="deleteTrip('${t.id}')">Delete</button></article>`).join(''):'<div class="card empty">No saved trips yet. Explore a destination to get started.</div>'}
async function deleteTrip(id){if(!confirm('Delete this trip?'))return;await fetch('/api/trips/'+id,{method:'DELETE'});toast('Trip deleted');loadTrips()}
init();
</script></body></html>'''


def load_trips() -> list[dict]:
    """Load trips from disk, returning an empty list for missing or invalid data."""
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def save_trips(trips: list[dict]) -> None:
    DATA_FILE.write_text(json.dumps(trips, indent=2, ensure_ascii=False), encoding="utf-8")


def create_trip(data: dict) -> dict:
    """Validate request data and create a serializable trip."""
    try:
        destination = DESTINATIONS[int(data["destination_index"])]
        start = datetime.strptime(data["start_date"], "%Y-%m-%d")
        end = datetime.strptime(data["end_date"], "%Y-%m-%d")
        travelers = int(data["travelers"])
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise ValueError("Please enter valid trip details.") from error
    if end < start:
        raise ValueError("The end date must be on or after the start date.")
    if not 1 <= travelers <= 20:
        raise ValueError("Travelers must be between 1 and 20.")
    days = max(1, (end - start).days)
    return {
        "id": f"{datetime.now().timestamp():.6f}".replace(".", ""),
        "destination": f"{destination['city']}, {destination['country']}",
        "start_date": data["start_date"],
        "end_date": data["end_date"],
        "travelers": travelers,
        "estimated_budget": days * travelers * destination["daily_cost"],
        "notes": str(data.get("notes", "")).strip()[:1000],
    }


class TravelHandler(BaseHTTPRequestHandler):
    def send_json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/destinations":
            self.send_json(DESTINATIONS)
        elif path == "/api/trips":
            self.send_json(load_trips())
        else:
            self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/trips":
            self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 20_000:
                raise ValueError("Request is too large.")
            data = json.loads(self.rfile.read(length))
            trip = create_trip(data)
            trips = load_trips()
            trips.append(trip)
            save_trips(trips)
            self.send_json(trip, HTTPStatus.CREATED)
        except (json.JSONDecodeError, ValueError) as error:
            self.send_json({"error": str(error) or "Invalid request."}, HTTPStatus.BAD_REQUEST)

    def do_DELETE(self) -> None:  # noqa: N802
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) != 3 or parts[:2] != ["api", "trips"]:
            self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        trips = load_trips()
        updated = [trip for trip in trips if trip.get("id") != parts[2]]
        if len(updated) == len(trips):
            self.send_json({"error": "Trip not found"}, HTTPStatus.NOT_FOUND)
            return
        save_trips(updated)
        self.send_json({"deleted": True})

    def log_message(self, format: str, *args: object) -> None:
        return


def run(open_browser: bool = True) -> None:
    server = ThreadingHTTPServer((HOST, PORT), TravelHandler)
    url = f"http://{HOST}:{PORT}"
    print(f"WanderPlan is running at {url}")
    print("Press Ctrl+C to stop it.")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWanderPlan stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
