#!/usr/bin/env python3
"""Face detail pass ("ADetailer"-style) for finished Z-Image renders of the Canny Alley band.

Small faces in 2048x1152 group shots come out with mushy eyes, teeth and braces. For every
labelled face: crop a square around it, upscale the crop to 1024x1024, re-render it with
Draw Things img2img at low strength using that band member's fixed description (so the same
four people stay recognisable across photos), scale back, match colour and film grain to the
original, and blend it in with a feathered oval.

  1. detect_faces.py (Apple Vision) -> concepts/fixed/faces.json
  2. face_labels.json: one letter per detected face (R/M/B/D, - = skip)
  3. ~/.local/share/uv/tools/mflux/bin/python facefix.py ID [ID ...]   (numpy + OpenCV)
     -> concepts/fixed/ID.png and concepts/fixed/ID.faces.jpg (before|after per face)

GPU job: one Draw Things call per face, about 1 min each. Never alongside another GPU job.
"""
import argparse, json, os, subprocess, tempfile, time
from pathlib import Path
import cv2, numpy as np

HERE = Path(__file__).resolve().parent
SRC, OUT = HERE / "concepts", HERE / "concepts" / "fixed"
MODEL = "z_image_turbo_1.0_q6p.ckpt"
os.environ.setdefault("DRAWTHINGS_MODELS_DIR", str(Path.home() / "Library/Containers/com.liuliu.draw-things/Data/Documents/Models"))

WHO = {
    "R": "a skinny young man in his early twenties with long straight ginger-red hair, pale lightly freckled "
         "skin and slightly yellow-tinted round wire glasses, his eyes clearly visible behind the lenses, natural teeth",
    "M": "a short plump young man in his early twenties with messy black hair, a full round face, dark brown eyes "
         "and a natural, well-groomed waxed moustache, natural teeth",
    "B": "an average-looking young blonde woman in her early twenties with light grey-blue eyes; when she smiles "
         "her teeth show neat metal dental braces, a small square bracket on every tooth joined by a thin wire",
    "D": "an attractive young woman in her early twenties with long wavy brown hair, hazel eyes, dark smoky eye "
         "makeup, a small nose ring and a lip piercing, natural white teeth",
}
STYLE = ("Close-up photograph of {who}. Keep the same expression, pose, hair, headwear, lighting and colours. "
         "Sharp, symmetrical natural eyes with detailed irises and catchlights, both eyes looking the same way, "
         "realistic teeth, realistic skin texture with pores, 35mm film grain.")


def strength_for(w):
    return 0.5 if w < 75 else 0.45 if w < 110 else 0.4


def grain_sigma(img, mask):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hp = (g - cv2.GaussianBlur(g, (0, 0), 1.2))[mask > 0.5]
    return float(np.median(np.abs(hp - np.median(hp))) * 1.4826)   # MAD: grain, not hair/edge detail


def fix_face(img, out, box, who, n, tmp, seed, raw):
    H, W = img.shape[:2]
    x, y, w, h = box[:4]
    side = min(int(max(w, h) * 2.2), W, H)
    cx, cy = x + w // 2, y + h // 2
    x0 = max(0, min(W - side, cx - side // 2)); y0 = max(0, min(H - side, cy - side // 2))
    crop = img[y0:y0 + side, x0:x0 + side]
    cv2.imwrite(str(tmp / f"in{n}.png"), cv2.resize(crop, (1024, 1024), interpolation=cv2.INTER_LANCZOS4))
    (tmp / f"p{n}.txt").write_text(STYLE.format(who=WHO[who]))
    if raw.exists():   # cached re-render: only redo the blend
        new = cv2.imread(str(raw))
    else:
        new = render(tmp, n, w, seed)
        if new is None:
            return None
        cv2.imwrite(str(raw), new)
    return blend(img, out, crop, new, x0, y0, side, seed)


def render(tmp, n, w, seed):
    r = subprocess.run(["draw-things-cli", "generate", "--local", "--offline", "--disable-preview",
                        "--model", MODEL, "--prompt-file", str(tmp / f"p{n}.txt"),
                        "--image", str(tmp / f"in{n}.png"), "--strength", str(strength_for(w)),
                        "--width", "1024", "--height", "1024", "--seed", str(seed),
                        "--output", str(tmp / f"out{n}.png")], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True)
    if r.returncode or not (tmp / f"out{n}.png").exists():
        print(f"  face {n} failed: {r.stderr[-300:]}", flush=True)
        return None
    return cv2.imread(str(tmp / f"out{n}.png"))


def blend(img, out, crop, new, x0, y0, side, seed):
    new = cv2.resize(new, (side, side), interpolation=cv2.INTER_AREA).astype(np.float32)
    m = np.zeros((side, side), np.float32)
    cv2.ellipse(m, (side // 2, side // 2), (int(side * 0.34), int(side * 0.40)), 0, 0, 360, 1, -1)
    m = cv2.GaussianBlur(m, (0, 0), side * 0.06)
    # colour: match per-channel mean/std inside the mask to the original crop
    sel = m > 0.5
    c = crop.astype(np.float32)
    for ch in range(3):
        a, b = c[..., ch][sel], new[..., ch][sel]
        new[..., ch] = (new[..., ch] - b.mean()) * (a.std() / max(b.std(), 1e-3)) + a.mean()
    # grain: add luma noise for whatever the re-render smoothed away
    lost = grain_sigma(crop, m) ** 2 - grain_sigma(np.clip(new, 0, 255).astype(np.uint8), m) ** 2
    if lost > 0:
        rng = np.random.default_rng(seed)
        new += rng.normal(0, np.sqrt(lost), (side, side, 1)).astype(np.float32)
    region = out[y0:y0 + side, x0:x0 + side]
    out[y0:y0 + side, x0:x0 + side] = region * (1 - m[..., None]) + new * m[..., None]
    after = np.clip(out[y0:y0 + side, x0:x0 + side], 0, 255).astype(np.uint8)
    return np.hstack([cv2.resize(crop, (360, 360)), cv2.resize(after, (360, 360))])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="+")
    a = ap.parse_args()
    boxes = json.loads((OUT / "faces.json").read_text())
    labels = json.loads((HERE / "face_labels.json").read_text())
    (OUT / "raw").mkdir(exist_ok=True)
    for id_ in a.ids:
        t0 = time.time()
        img = cv2.imread(str(SRC / f"{id_}.png"))
        out = img.astype(np.float32)
        tmp = Path(tempfile.mkdtemp(prefix="facefix-"))
        pairs = []
        for n, (box, who) in enumerate(zip(boxes.get(id_, []), labels.get(id_, ""))):
            if who in WHO:
                p = fix_face(img, out, box, who, n, tmp, seed=7 + n, raw=OUT / "raw" / f"{id_}.{n}.png")
                if p is not None:
                    pairs.append(p)
        cv2.imwrite(str(OUT / f"{id_}.png"), np.clip(out, 0, 255).astype(np.uint8))
        if pairs:
            cv2.imwrite(str(OUT / f"{id_}.faces.jpg"), np.vstack(pairs), [cv2.IMWRITE_JPEG_QUALITY, 88])
        print(f"{time.strftime('%T')} fixed {id_}: {len(pairs)} faces, {time.time() - t0:.0f}s", flush=True)
    print(f"{time.strftime('%T')} ALL DONE", flush=True)


if __name__ == "__main__":
    main()
