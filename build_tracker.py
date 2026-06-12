import os
import re
import json
import base64
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ── Config from environment ──────────────────────────────────────────────────
JIRA_EMAIL    = os.environ["JIRA_EMAIL"]
JIRA_TOKEN    = os.environ["JIRA_TOKEN"]
JIRA_BASE_URL = os.environ["JIRA_BASE_URL"].rstrip("/")
EPIC_KEY      = "CLIC-455"
CLOUD_ID      = "081bfc9f-afc4-477c-88b0-a27e8f59130d"

credentials = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_TOKEN}".encode()).decode()
HEADERS = {
    "Authorization": f"Basic {credentials}",
    "Accept": "application/json",
}

def jira_get(path):
    url = f"https://api.atlassian.com/ex/jira/{CLOUD_ID}/rest/api/3{path}"
    print(f"  Calling: {url}")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def fetch_tickets():
    jql = f'cf[10008] = {EPIC_KEY} ORDER BY created ASC'
    fields = "summary,status,issuetype,updated,assignee,comment"
    path = f"/search?jql={urllib.request.quote(jql)}&fields={fields}&maxResults=100"
    data = jira_get(path)
    return data.get("issues", [])

# ── Comment text extraction ───────────────────────────────────────────────────
def extract_adf(node):
    if not isinstance(node, dict):
        return ""
    t = node.get("type", "")
    if t == "text":
        return node.get("text", "")
    if t == "mention":
        return "@" + node.get("attrs", {}).get("text", "").lstrip("@") + " "
    if t in ("emoji", "inlineCard", "blockCard", "mediaSingle", "media", "hardBreak"):
        return " "
    return "".join(extract_adf(c) for c in node.get("content", []))

def clean_comment(body):
    if isinstance(body, dict):
        text = extract_adf(body)
    else:
        text = str(body or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 130:
        text = text[:130].rsplit(" ", 1)[0] + "…"
    return text

# ── Delivery category ─────────────────────────────────────────────────────────
def get_delivery(status):
    s = status.lower()
    if s == "po review":                                               return "green"
    if s in ("qa", "qa in progress"):                                  return "yellow"
    if s in ("qa failed", "externally blocked", "internally blocked"): return "red"
    if s == "eng review":                                              return "blue"
    return "gray"

DELIVERY_LABEL = {
    "green":  "On track",
    "yellow": "In progress",
    "red":    "At risk",
    "blue":   "Eng Review",
    "gray":   "Not started",
}

# ── Build ticket list ─────────────────────────────────────────────────────────
def build_tickets(issues):
    tickets = []
    for issue in issues:
        f = issue["fields"]
        status   = f["status"]["name"]
        itype    = f["issuetype"]["name"]
        assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
        updated  = f.get("updated", "")

        comments = (f.get("comment") or {}).get("comments", [])
        if comments:
            last     = comments[-1]
            c_author = last.get("author", {}).get("displayName", "")
            c_date   = last.get("created", "")[:10]
            c_text   = clean_comment(last.get("body", ""))
        else:
            c_author = c_date = c_text = ""

        tickets.append({
            "key":      issue["key"],
            "type":     itype,
            "status":   status,
            "updated":  updated,
            "assignee": assignee,
            "summary":  f["summary"],
            "comment":  {"author": c_author, "date": c_date, "text": c_text},
        })
    return tickets

# ── HTML template ─────────────────────────────────────────────────────────────
def render_html(tickets, generated_at):
    tickets_js = json.dumps(tickets, ensure_ascii=False, indent=2)
    count = len(tickets)

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CLIC-455 — Patient DTP v7 Tracker</title>
<style>
  :root {
    --bg: #f7f6f2; --surface: #ffffff; --border: #e5e2d9; --border-mid: #d0cdc4;
    --text-primary: #1a1917; --text-secondary: #5a574f; --text-muted: #908c83;
    --green-bg: #e8f5e9; --green-text: #2e6e35; --green-dot: #3a8c42;
    --yellow-bg: #fff8e1; --yellow-text: #8a6800; --yellow-dot: #c49a00;
    --red-bg: #fdecea; --red-text: #b32318; --red-dot: #c9302c;
    --gray-bg: #f1efea; --gray-text: #6b685f; --gray-dot: #9c9890;
    --blue-bg: #e8f0fb; --blue-text: #1a4fa0; --blue-dot: #2563c7;
    --purple-bg: #f0ecfc; --purple-text: #5b3ea6;
    --coral-bg: #fef0ec; --coral-text: #a83718;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text-primary); min-height: 100vh; padding: 0 0 3rem; }
  .page-header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 1.5rem 2rem 1.25rem; }
  .header-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .epic-badge { display: inline-flex; align-items: center; gap: 6px; background: var(--purple-bg); color: var(--purple-text); font-size: 11px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; padding: 3px 10px; border-radius: 4px; margin-bottom: 6px; }
  .page-title { font-size: 22px; font-weight: 600; letter-spacing: -.02em; line-height: 1.25; }
  .page-meta { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
  .page-meta a { color: var(--blue-text); text-decoration: none; }
  .page-meta a:hover { text-decoration: underline; }
  .legend { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; font-size: 12px; color: var(--text-secondary); }
  .legend-title { font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); margin-right: 4px; }
  .legend-item { display: flex; align-items: center; gap: 6px; }
  .legend-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
  .summary-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; padding: 1.25rem 2rem; background: var(--bg); border-bottom: 1px solid var(--border); }
  .stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; }
  .stat-label { font-size: 11px; font-weight: 500; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); margin-bottom: 6px; }
  .stat-val { font-size: 22px; font-weight: 600; letter-spacing: -.02em; }
  .stat-sub { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
  .controls { display: flex; align-items: center; gap: 10px; padding: 1rem 2rem; flex-wrap: wrap; }
  .filter-label { font-size: 12px; color: var(--text-muted); font-weight: 500; }
  .filter-btn { font-size: 12px; font-weight: 500; padding: 4px 12px; border-radius: 20px; border: 1px solid var(--border-mid); background: var(--surface); color: var(--text-secondary); cursor: pointer; transition: all .12s; }
  .filter-btn:hover { border-color: #aaa; color: var(--text-primary); }
  .filter-btn.active { background: var(--text-primary); color: #fff; border-color: var(--text-primary); }
  .search-input { margin-left: auto; font-size: 13px; padding: 5px 12px; border: 1px solid var(--border-mid); border-radius: 6px; background: var(--surface); color: var(--text-primary); width: 220px; outline: none; }
  .table-wrap { padding: 0 2rem; overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; font-size: 13px; }
  thead th { text-align: left; padding: 10px 14px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); background: var(--bg); border-bottom: 1px solid var(--border); white-space: nowrap; cursor: pointer; user-select: none; }
  thead th:hover { color: var(--text-primary); }
  thead th .sort-arrow { margin-left: 4px; opacity: .4; }
  thead th.sorted .sort-arrow { opacity: 1; }
  tbody tr { border-bottom: 1px solid var(--border); transition: background .1s; }
  tbody tr:last-child { border-bottom: none; }
  tbody tr:hover { background: #faf9f6; }
  td { padding: 10px 14px; vertical-align: middle; }
  .ticket-id-link { font-weight: 600; color: var(--blue-text); text-decoration: none; white-space: nowrap; }
  .ticket-id-link:hover { text-decoration: underline; }
  .summary-cell { max-width: 280px; line-height: 1.45; }
  .badge { display: inline-block; font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 4px; white-space: nowrap; }
  .badge-story { background: var(--purple-bg); color: var(--purple-text); }
  .badge-bug   { background: var(--coral-bg);  color: var(--coral-text); }
  .status-badge { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 500; padding: 3px 9px; border-radius: 20px; white-space: nowrap; }
  .status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
  .s-green  { background: var(--green-bg);  color: var(--green-text); }
  .s-yellow { background: var(--yellow-bg); color: var(--yellow-text); }
  .s-red    { background: var(--red-bg);    color: var(--red-text); }
  .s-gray   { background: var(--gray-bg);   color: var(--gray-text); }
  .s-blue   { background: var(--blue-bg);   color: var(--blue-text); }
  .dot-green  { background: var(--green-dot); }
  .dot-yellow { background: var(--yellow-dot); }
  .dot-red    { background: var(--red-dot); }
  .dot-gray   { background: var(--gray-dot); }
  .dot-blue   { background: var(--blue-dot); }
  .assignee-cell { white-space: nowrap; color: var(--text-secondary); font-size: 12px; }
  .updated-cell  { white-space: nowrap; color: var(--text-muted); font-size: 12px; }
  .delivery-cell { white-space: nowrap; font-size: 11px; font-weight: 600; }
  .dv-green  { color: var(--green-text); }
  .dv-yellow { color: var(--yellow-text); }
  .dv-red    { color: var(--red-text); }
  .dv-gray   { color: var(--gray-text); }
  .dv-blue   { color: var(--blue-text); }
  .comment-cell { max-width: 260px; font-size: 12px; }
  .comment-text { display: block; color: var(--text-secondary); line-height: 1.45; margin-bottom: 3px; }
  .comment-meta { display: block; font-size: 11px; color: var(--text-muted); white-space: nowrap; }
  .comment-none { color: var(--text-muted); }
  .no-results { text-align: center; color: var(--text-muted); padding: 2.5rem; font-size: 14px; }
  .page-footer { text-align: center; font-size: 11px; color: var(--text-muted); padding: 2rem 2rem 0; }
  .page-footer a { color: var(--blue-text); text-decoration: none; }
</style>
</head>
<body>
<div class="page-header">
  <div class="header-top">
    <div>
      <div class="epic-badge">⬡ Epic · CLIC-455</div>
      <div class="page-title">Patient DTP v7 Requirements Updates</div>
      <div class="page-meta">
        <a href="https://akesoteam.atlassian.net/browse/CLIC-455" target="_blank">View in Jira ↗</a>
        &nbsp;·&nbsp; """ + str(count) + """ tickets &nbsp;·&nbsp; Assignee: Wes Benzon &nbsp;·&nbsp;
        Updated: """ + generated_at + """
      </div>
    </div>
    <div class="legend">
      <span class="legend-title">Legend</span>
      <span class="legend-item"><span class="legend-dot" style="background:var(--green-dot)"></span>On track</span>
      <span class="legend-item"><span class="legend-dot" style="background:var(--yellow-dot)"></span>In progress</span>
      <span class="legend-item"><span class="legend-dot" style="background:var(--red-dot)"></span>At risk</span>
      <span class="legend-item"><span class="legend-dot" style="background:var(--blue-dot)"></span>Eng Review</span>
      <span class="legend-item"><span class="legend-dot" style="background:var(--gray-dot)"></span>Not started</span>
    </div>
  </div>
</div>
<div class="summary-row" id="summary-row"></div>
<div class="controls">
  <span class="filter-label">Filter:</span>
  <button class="filter-btn active" data-filter="all">All</button>
  <button class="filter-btn" data-filter="green">On track</button>
  <button class="filter-btn" data-filter="yellow">In progress</button>
  <button class="filter-btn" data-filter="red">At risk</button>
  <button class="filter-btn" data-filter="blue">Eng Review</button>
  <button class="filter-btn" data-filter="gray">Not started</button>
  <button class="filter-btn" data-filter="story">Stories</button>
  <button class="filter-btn" data-filter="bug">Bugs</button>
  <input class="search-input" id="search" placeholder="Search tickets…" type="text">
</div>
<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th data-col="key">Ticket <span class="sort-arrow">↕</span></th>
        <th data-col="type">Type <span class="sort-arrow">↕</span></th>
        <th data-col="summary">Summary <span class="sort-arrow">↕</span></th>
        <th data-col="status">Status <span class="sort-arrow">↕</span></th>
        <th data-col="delivery">Delivery <span class="sort-arrow">↕</span></th>
        <th data-col="assignee">Assignee <span class="sort-arrow">↕</span></th>
        <th data-col="updated">Last updated <span class="sort-arrow">↕</span></th>
        <th data-col="comment">Latest comment <span class="sort-arrow">↕</span></th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
  <div class="no-results" id="no-results" style="display:none">No tickets match your filter.</div>
</div>
<div class="page-footer">
  Data pulled from <a href="https://akesoteam.atlassian.net/browse/CLIC-455" target="_blank">Jira · CLIC-455</a>.
  Auto-updated daily at 8am CST via GitHub Actions.
</div>
<script>
const tickets = """ + tickets_js + """;
function getDelivery(s) {
  s = s.toLowerCase();
  if (s === "po review") return "green";
  if (["qa","qa in progress"].includes(s)) return "yellow";
  if (["qa failed","externally blocked","internally blocked"].includes(s)) return "red";
  if (s === "eng review") return "blue";
  return "gray";
}
const dLabel = {green:"On track",yellow:"In progress",red:"At risk",blue:"Eng Review",gray:"Not started"};
const dDot   = {green:"dot-green",yellow:"dot-yellow",red:"dot-red",blue:"dot-blue",gray:"dot-gray"};
const dSt    = {green:"s-green",yellow:"s-yellow",red:"s-red",blue:"s-blue",gray:"s-gray"};
const dDv    = {green:"dv-green",yellow:"dv-yellow",red:"dv-red",blue:"dv-blue",gray:"dv-gray"};
function fmtShort(iso) {
  const d = new Date(iso), now = new Date(), h = (now-d)/3600000;
  if (h<1) return 'Just now';
  if (h<24) return Math.floor(h)+'h ago';
  const days = Math.floor(h/24);
  if (days===1) return 'Yesterday';
  if (days<7) return days+'d ago';
  return d.toLocaleDateString('en-US',{month:'short',day:'numeric'});
}
function fmtFull(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})
    +' '+d.toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit',hour12:true});
}
function renderSummary() {
  const c = {green:0,yellow:0,red:0,blue:0,gray:0};
  tickets.forEach(t => c[getDelivery(t.status)]++);
  document.getElementById('summary-row').innerHTML = [
    {label:'Total tickets',val:tickets.length,sub:'in epic'},
    {label:'On track',val:c.green,sub:'PO review',col:'var(--green-text)'},
    {label:'In progress',val:c.yellow,sub:'QA / rework',col:'var(--yellow-text)'},
    {label:'At risk',val:c.red,sub:'blocked',col:'var(--red-text)'},
    {label:'Eng Review',val:c.blue,sub:'eng review',col:'var(--blue-text)'},
    {label:'Not started',val:c.gray,sub:'todo',col:'var(--gray-text)'},
  ].map(x=>`<div class="stat-card"><div class="stat-label">${x.label}</div><div class="stat-val" ${x.col?`style="color:${x.col}"`:''}>${x.val}</div><div class="stat-sub">${x.sub}</div></div>`).join('');
}
let cur=[...tickets], activeF='all', q='';
function renderRows(data) {
  document.getElementById('tbody').innerHTML = data.map(t => {
    const dv=getDelivery(t.status), c=t.comment||{};
    return `<tr>
      <td><a class="ticket-id-link" href="https://akesoteam.atlassian.net/browse/${t.key}" target="_blank">${t.key}</a></td>
      <td><span class="badge badge-${t.type.toLowerCase()}">${t.type}</span></td>
      <td class="summary-cell">${t.summary}</td>
      <td><span class="status-badge ${dSt[dv]}"><span class="status-dot ${dDot[dv]}"></span>${t.status}</span></td>
      <td class="delivery-cell ${dDv[dv]}">${dLabel[dv]}</td>
      <td class="assignee-cell">${t.assignee}</td>
      <td class="updated-cell" title="${fmtFull(t.updated)}">${fmtShort(t.updated)}</td>
      <td class="comment-cell">${c.text?`<span class="comment-text">${c.text}</span><span class="comment-meta">${c.author} · ${c.date}</span>`:'<span class="comment-none">—</span>'}</td>
    </tr>`;
  }).join('');
  document.getElementById('no-results').style.display=data.length===0?'block':'none';
}
function applyFilters() {
  let data=tickets;
  if (activeF!=='all') {
    if (['green','yellow','red','blue','gray'].includes(activeF)) data=data.filter(t=>getDelivery(t.status)===activeF);
    else data=data.filter(t=>t.type.toLowerCase()===activeF);
  }
  if (q) { const lq=q.toLowerCase(); data=data.filter(t=>t.key.toLowerCase().includes(lq)||t.summary.toLowerCase().includes(lq)||t.status.toLowerCase().includes(lq)||t.assignee.toLowerCase().includes(lq)||(t.comment?.text||'').toLowerCase().includes(lq)); }
  cur=data; renderRows(data);
}
document.querySelectorAll('.filter-btn').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('.filter-btn').forEach(x=>x.classList.remove('active'));
  b.classList.add('active'); activeF=b.dataset.filter; applyFilters();
}));
document.getElementById('search').addEventListener('input',e=>{q=e.target.value;applyFilters();});
let sCol=null,sDir=1;
document.querySelectorAll('thead th[data-col]').forEach(th=>th.addEventListener('click',()=>{
  const col=th.dataset.col;
  if(sCol===col) sDir*=-1; else {sCol=col;sDir=1;}
  document.querySelectorAll('thead th').forEach(t=>t.classList.remove('sorted'));
  th.classList.add('sorted');
  th.querySelector('.sort-arrow').textContent=sDir===1?'↑':'↓';
  cur.sort((a,b)=>{
    let va,vb;
    if(col==='key'){va=a.key;vb=b.key;}
    else if(col==='type'){va=a.type;vb=b.type;}
    else if(col==='summary'){va=a.summary;vb=b.summary;}
    else if(col==='status'){va=a.status;vb=b.status;}
    else if(col==='delivery'){va=getDelivery(a.status);vb=getDelivery(b.status);}
    else if(col==='assignee'){va=a.assignee;vb=b.assignee;}
    else if(col==='updated'){va=a.updated;vb=b.updated;}
    else if(col==='comment'){va=a.comment?.date||'';vb=b.comment?.date||'';}
    return va<vb?-sDir:va>vb?sDir:0;
  });
  renderRows(cur);
}));
renderSummary();
renderRows(tickets);
</script>
</body>
</html>"""

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Fetching tickets from Jira...")
    issues  = fetch_tickets()
    tickets = build_tickets(issues)
    print(f"  {len(tickets)} tickets fetched")
    generated_at = datetime.now(timezone.utc).strftime("%-d %b %Y, %-I:%M %p UTC")
    html = render_html(tickets, generated_at)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("index.html written successfully")
