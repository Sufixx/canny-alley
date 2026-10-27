#!/usr/bin/env python3
"""Overnight Canny Alley channel-art batch (Draw Things CLI, Z-Image Turbo).

Round-robin over concepts.json (pass 1 = every concept once, pass 2 = new seeds, ...),
one image at a time, until the deadline. Skips a job when its estimated time would run
past the deadline. Rebuilds concepts/gallery.html after every image, opens it at the end.

Run detached:  nohup caffeinate -ims python3 run_concepts.py [HH:MM] [concepts.json] < /dev/null > concepts/run.log 2>&1 &
A config with "shots" (concepts-live.json) yields 16:9 "photo" jobs: scene + cast block + style.
"""
import datetime as dt, json, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "concepts"
MODEL = "z_image_turbo_1.0_q6p.ckpt"
SIZES = {"banner": (2048, 1152), "avatar": (1024, 1024), "photo": (2048, 1152)}
EST = {"banner": 380.0, "avatar": 250.0, "photo": 380.0}   # seconds, replaced by measured averages
PASSES = 8
OTHER_GPU = r"mflux|acestep|generate\.py|ltx-2|whisper-cli|draw-things-cli|align_lyrics|realesrgan"

os.environ.setdefault("DRAWTHINGS_MODELS_DIR", str(Path.home() / "Library/Containers/com.liuliu.draw-things/Data/Documents/Models"))


def deadline(hhmm):
    h, m = map(int, hhmm.split(":"))
    now = dt.datetime.now()
    d = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return d if d > now else d + dt.timedelta(days=1)


def jobs(c):
    if "shots" in c:
        casts = {"winter": c["faces"] + " " + c["winter"], "stage": c["stage"], "none": ""}
        for p in range(1, PASSES + 1):
            for i, (key, s) in enumerate(c["shots"].items()):
                style = c["style_winter"] if s["cast"] == "winter" else c["style_stage"]
                prompt = " ".join(x for x in (s["scene"], casts[s["cast"]], style) if x)
                yield dict(id=f"{key}-s{p}", kind="photo", concept=key, seed=1000 * p + 17 * i + 3, prompt=prompt)
        return
    for p in range(1, PASSES + 1):
        for kind, group, comp in (("banner", "banners", "banner_comp"), ("avatar", "avatars", "avatar_comp")):
            for i, (key, scene) in enumerate(c[group].items()):
                band = kind == "banner" or key in c["avatars_with_band"]
                prompt = " ".join(x for x in (scene, c["band"] if band else "", c[comp]) if x)
                yield dict(id=f"{key}-s{p}", kind=kind, concept=key, seed=1000 * p + 17 * i + 3,
                           prompt=prompt, pass_=p)


def gpu_busy():
    r = subprocess.run(["pgrep", "-fl", OTHER_GPU], capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if str(os.getpid()) not in l and "pgrep" not in l]


def main():
    end = deadline(sys.argv[1] if len(sys.argv) > 1 else "07:45")
    c = json.loads((HERE / (sys.argv[2] if len(sys.argv) > 2 else "concepts.json")).read_text())
    man_path = OUT / "manifest.json"
    manifest = json.loads(man_path.read_text()) if man_path.exists() else []
    done = {m["id"] for m in manifest}
    times = {k: [] for k in SIZES}
    for m in manifest:
        if m.get("seconds") and m["kind"] in times:
            times[m["kind"]].append(m["seconds"])
    print(f"deadline {end:%Y-%m-%d %H:%M}", flush=True)
    for j in jobs(c):
        if j["id"] in done:
            continue
        while busy := gpu_busy():
            print(f"{dt.datetime.now():%T} waiting, GPU busy: {busy[0][:80]}", flush=True)
            time.sleep(30)
        est = sum(times[j["kind"]][-5:]) / len(times[j["kind"]][-5:]) if times[j["kind"]] else EST[j["kind"]]
        if dt.datetime.now() + dt.timedelta(seconds=est * 1.1) > end:
            print(f"{dt.datetime.now():%T} skip {j['id']} (est {est:.0f}s past deadline)", flush=True)
            continue
        w, h = SIZES[j["kind"]]
        png = OUT / f"{j['id']}.png"
        (OUT / f"{j['id']}.prompt.txt").write_text(j["prompt"] + "\n")
        t0 = time.time()
        r = subprocess.run(["draw-things-cli", "generate", "--local", "--offline", "--disable-preview",
                            "--model", MODEL, "--prompt-file", str(OUT / f"{j['id']}.prompt.txt"),
                            "--width", str(w), "--height", str(h), "--seed", str(j["seed"]),
                            "--output", str(png)], stdin=subprocess.DEVNULL, capture_output=True, text=True)
        secs = round(time.time() - t0, 1)
        if r.returncode or not png.exists():
            print(f"{dt.datetime.now():%T} FAIL {j['id']} rc={r.returncode} {r.stderr[-300:]}", flush=True)
            continue
        times[j["kind"]].append(secs)
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "82", "-Z", "1024",
                        str(png), "--out", str(OUT / "thumbs" / f"{j['id']}.jpg")], capture_output=True)
        manifest.append(dict(id=j["id"], kind=j["kind"], concept=j["concept"], seed=j["seed"],
                             w=w, h=h, seconds=secs, prompt=j["prompt"],
                             at=dt.datetime.now().strftime("%H:%M")))
        man_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
        subprocess.run([sys.executable, str(HERE / "gallery.py")])
        print(f"{dt.datetime.now():%T} done {j['id']} {secs:.0f}s (total {len(manifest)})", flush=True)
    print(f"{dt.datetime.now():%T} ALL DONE, {len(manifest)} images", flush=True)
    subprocess.run(["open", str(OUT / "gallery.html")])


if __name__ == "__main__":
    (OUT / "thumbs").mkdir(parents=True, exist_ok=True)
    main()
