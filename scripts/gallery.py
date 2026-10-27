#!/usr/bin/env python3
"""Write concepts/gallery.html from concepts/manifest.json (self-contained, works over file://)."""
import json, subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent / "concepts"
manifest = json.loads((OUT / "manifest.json").read_text())

# refined versions from facefix.py: concepts/fixed/<id>.png, thumbnail in thumbs/fixed/
(OUT / "thumbs" / "fixed").mkdir(parents=True, exist_ok=True)
for m in manifest:
    png, jpg = OUT / "fixed" / f"{m['id']}.png", OUT / "thumbs" / "fixed" / f"{m['id']}.jpg"
    m["fixed"] = png.exists()
    if m["fixed"] and (not jpg.exists() or jpg.stat().st_mtime < png.stat().st_mtime):
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "82", "-Z", "1024",
                        str(png), "--out", str(jpg)], capture_output=True)

HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Canny Alley Concepts</title>
<style>
:root{--bg:#0e0c14;--panel:#1a1724;--line:#2d2840;--text:#e8e4f2;--dim:#9a93b0;--acc:#a77bff;--acc2:#4fa3ff;--star:#ffd84a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 -apple-system,system-ui,sans-serif}
header{position:sticky;top:0;z-index:5;background:rgba(14,12,20,.93);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:12px 16px}
h1{margin:0 0 4px;font-size:20px;letter-spacing:.02em}
h1 span{color:var(--acc)}
.note{color:var(--dim);font-size:13px;margin:0 0 10px;max-width:1100px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.bar .grp{display:flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
button,select{background:var(--panel);color:var(--text);border:0;padding:6px 11px;font:inherit;font-size:13px;cursor:pointer}
.grp button+button{border-left:1px solid var(--line)}
button.on{background:var(--acc);color:#140c26;font-weight:600}
select{border:1px solid var(--line);border-radius:8px}
#count{color:var(--dim);font-size:13px;margin-left:auto}
main{padding:16px}
h2{font-size:15px;color:var(--acc2);margin:22px 0 8px;font-weight:600}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(min(100%,var(--min,420px)),1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.card.fav{border-color:var(--star);box-shadow:0 0 0 1px var(--star)}
.frame{position:relative;display:block;overflow:hidden;background:#000}
.frame img{display:block;width:100%;height:100%;object-fit:cover;object-position:center}
.banner .frame{aspect-ratio:var(--ar,16/9)}
.avatar .frame{aspect-ratio:1}
.circle .avatar .frame img{clip-path:circle(50% at 50% 50%)}
.guide{position:absolute;pointer-events:none;border:2px dashed;display:none}
.guides .guide{display:block}
.g-desk{left:0;right:0;top:35.3%;height:29.4%;border-color:rgba(79,163,255,.9)}
.g-safe{left:19.8%;width:60.4%;top:35.3%;height:29.4%;border-color:rgba(255,216,74,.95)}
.meta{display:flex;align-items:center;gap:8px;padding:7px 10px;font-size:12.5px;color:var(--dim)}
.meta b{color:var(--text);font-weight:600}
.badge{position:absolute;left:8px;top:8px;background:rgba(14,12,20,.8);color:var(--acc);font-size:11.5px;font-weight:600;padding:2px 7px;border-radius:6px;letter-spacing:.03em}
.meta .ba{margin-left:auto;border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:12px}
.meta .ba+.star{margin-left:0}
.meta .star{margin-left:auto;background:none;font-size:20px;padding:0 4px;color:var(--dim)}
.card.fav .star{color:var(--star)}
details{padding:0 10px 8px;font-size:12px;color:var(--dim)}
summary{cursor:pointer}
.legend{font-size:12px;color:var(--dim)}
.legend i{display:inline-block;width:18px;border-top:2px dashed;vertical-align:middle;margin:0 4px 0 10px}
@media (max-width:600px){#count{margin-left:0;width:100%}}
</style></head><body>
<header>
<h1><span>Canny Alley</span> · channel art concepts</h1>
<p class="note">Z-Image Turbo (Draw Things, local), generated overnight 26→27 Oct 2026. <b>Banners</b> are 2048×1152 (16:9), so each one is also a video-thumbnail candidate ("miniatura"); for the channel banner, check the desktop crop. <b>Avatars</b> are 1024×1024 square profile pictures, shown as YouTube's circle. <b>Winter &amp; live</b> (27 Oct) are 2048×1152 photos of the same band in a snowy park and on a real concert stage. <b>✦ Refined</b> (27 Oct): your 21 picks after a face pass (eyes, teeth, braces re-rendered per band member); "before" on a card shows the original. Click an image for the full PNG; ★ marks picks (saved in this browser), "Copy picks" copies their IDs.</p>
<div class="bar">
 <div class="grp" id="kind"><button data-v="banner" class="on">Banners</button><button data-v="avatar">Avatars</button><button data-v="photo">Winter &amp; live</button><button data-v="fav">★ Picks</button><button data-v="fixed">✦ Refined</button></div>
 <div class="grp" id="view"><button data-v="full" class="on">Full 16:9 / TV</button><button data-v="desk">Desktop crop</button><button data-v="mob">Mobile crop</button><button data-v="guides">Guides</button></div>
 <div class="grp" id="circ"><button data-v="1" class="on">Circle</button><button data-v="0">Square</button></div>
 <select id="concept"><option value="">All concepts</option></select>
 <select id="sort"><option value="concept">Group by concept</option><option value="time">Newest first</option></select>
 <div class="grp" id="size"><button data-v="300">S</button><button data-v="420" class="on">M</button><button data-v="640">L</button></div>
 <button id="copy" style="border:1px solid var(--line);border-radius:8px">Copy picks</button>
 <span id="count"></span>
</div>
<div class="legend" id="legend" hidden><i style="border-color:#4fa3ff"></i>desktop strip (2560×423) <i style="border-color:#ffd84a"></i>safe area on all devices (1546×423)</div>
</header>
<main id="main"></main>
<script>
const DATA = __DATA__;
const st = {kind:"banner", view:"full", circle:true, concept:"", sort:"concept"};
let favs = new Set();
try { favs = new Set(JSON.parse(localStorage.getItem("ca-favs") || "[]")); } catch (e) {}
const saveFavs = () => { try { localStorage.setItem("ca-favs", JSON.stringify([...favs])); } catch (e) {} };
const AR = {full:"16/9", desk:"2560/423", mob:"1855/423", guides:"16/9"};

function seg(id, key, fn) {
  document.querySelectorAll(`#${id} button`).forEach(b => b.onclick = () => {
    document.querySelectorAll(`#${id} button`).forEach(x => x.classList.toggle("on", x === b));
    fn(b.dataset.v); render();
  });
}
seg("kind", "kind", v => st.kind = v);
seg("view", "view", v => st.view = v);
seg("circ", "circle", v => st.circle = v === "1");
seg("size", "size", v => document.documentElement.style.setProperty("--min", v + "px"));
document.getElementById("concept").onchange = e => { st.concept = e.target.value; render(); };
document.getElementById("sort").onchange = e => { st.sort = e.target.value; render(); };
document.getElementById("copy").onclick = () => {
  const t = [...favs].sort().join("\n") || "(no picks yet)";
  navigator.clipboard?.writeText(t).then(() => flash("Copied " + favs.size), () => prompt("Picks:", t));
};
function flash(t){ const c=document.getElementById("count"); const o=c.textContent; c.textContent=t; setTimeout(()=>c.textContent=o,1500); }

const concepts = [...new Set(DATA.map(d => d.concept))].sort();
const sel = document.getElementById("concept");
concepts.forEach(c => sel.add(new Option(c, c)));

function card(d) {
  const el = document.createElement("div");
  el.className = "card" + (favs.has(d.id) ? " fav" : "");
  const ref = d.fixed;
  el.innerHTML = `<a class="frame" href="${ref ? "fixed/" : ""}${d.id}.png" target="_blank"><img loading="lazy" src="thumbs/${ref ? "fixed/" : ""}${d.id}.jpg" alt="${d.id}">
    ${ref ? '<span class="badge">refined</span>' : ""}
    <div class="guide g-desk"></div><div class="guide g-safe"></div></a>
    <div class="meta"><b>${d.concept}</b> seed ${d.seed} · ${Math.round(d.seconds)} s · ${d.at}${ref ? '<button class="ba" title="toggle before/after">before</button>' : ""}<button class="star" title="pick">★</button></div>
    <details><summary>prompt</summary>${d.prompt.replace(/</g,"&lt;")}</details>`;
  const ba = el.querySelector(".ba");
  if (ba) ba.onclick = () => {
    const after = ba.textContent === "before";
    el.querySelector("img").src = `thumbs/${after ? "" : "fixed/"}${d.id}.jpg`;
    el.querySelector(".frame").href = `${after ? "" : "fixed/"}${d.id}.png`;
    el.querySelector(".badge").textContent = after ? "original" : "refined";
    ba.textContent = after ? "after" : "before";
  };
  el.querySelector(".star").onclick = () => {
    favs.has(d.id) ? favs.delete(d.id) : favs.add(d.id); saveFavs();
    el.classList.toggle("fav", favs.has(d.id)); if (st.kind === "fav") render(); updateCount();
  };
  return el;
}
function updateCount(){ document.getElementById("count").textContent =
  `${DATA.filter(d=>d.kind==="banner").length} banners · ${DATA.filter(d=>d.kind==="avatar").length} avatars · ${DATA.filter(d=>d.kind==="photo").length} winter & live · ${DATA.filter(d=>d.fixed).length} refined · ${favs.size} picked`; }

function render() {
  const main = document.getElementById("main");
  main.className = (st.circle ? "circle " : "") + (st.view === "guides" ? "guides" : "");
  document.documentElement.style.setProperty("--ar", AR[st.view]);
  document.getElementById("legend").hidden = st.view !== "guides";
  let items = DATA.filter(d => st.kind === "fav" ? favs.has(d.id) : st.kind === "fixed" ? d.fixed : d.kind === st.kind)
                  .filter(d => !st.concept || d.concept === st.concept);
  main.innerHTML = "";
  const groups = new Map();
  if (st.sort === "time") groups.set("", [...items].reverse());
  else items.forEach(d => { const k = d.concept; groups.has(k) || groups.set(k, []); groups.get(k).push(d); });
  [...groups.keys()].sort().forEach(k => {
    if (k) { const h = document.createElement("h2"); h.textContent = `${k} (${groups.get(k).length})`; main.append(h); }
    const sec = document.createElement("div");
    sec.className = "grid";
    groups.get(k).forEach(d => { const w = document.createElement("div"); w.className = d.kind === "avatar" ? "avatar" : "banner"; w.append(card(d)); sec.append(w); });
    main.append(sec);
  });
  if (!items.length) main.innerHTML = '<p class="note">Nothing here yet.</p>';
  updateCount();
}
render();
</script></body></html>
"""

(OUT / "gallery.html").write_text(HTML.replace("__DATA__", json.dumps(manifest, ensure_ascii=False)))
