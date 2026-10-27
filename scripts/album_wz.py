#!/usr/bin/env python3
"""Album 'Wynajęte życie' (Canny Alley) pipeline on the Mac, one heavy GPU job at a time.

  python3 songs/album_wz.py songs  [N ...]   ACE-Step -> output/<slug>/ -> trimmed final.mp3 -> tagged/<slug>.mp3
  python3 songs/album_wz.py import [N ...]   songs rendered on the PC (NAS _render/out) -> trimmed final.mp3 -> tagged -> drop
  python3 songs/album_wz.py covers [N ...]   Z-Image (Draw Things) -> covers/wynajete-zycie/<slug>.png
  python3 songs/album_wz.py loops  [N ...]   LTX-2.3 (MLX) clip -> ESRGAN -> 1080p ping-pong loop anim/wz/<slug>-loop.mp4
  python3 songs/album_wz.py videos [N ...]   loop + song -> review/<NN - Title>.mp4 (CPU) and copy to the shared review folder

Config: songs/album-wz.json (captions), covers/wynajete-zycie.json (cover + motion prompts).
Nothing is published: tagged MP3s and videos only go to $CA_SHARE/<album>/ for review ($CA_SHARE = a folder both render machines can reach, e.g. a NAS share; default ./share).
Each stage skips finished items, so the script can be re-run after a crash. Run detached:
  nohup caffeinate -ims python3 songs/album_wz.py songs < /dev/null >> logs/album-wz.log 2>&1 &
Options: --ref <mp3> (+ --ref-strength) passes a reference track to ACE-Step for voice/timbre continuity;
         --suffix <s> writes output/<slug><s>/ so an A/B take doesn't replace the main one.
"""
import json, math, os, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CFG = json.loads((HERE / os.environ.get("ALBUM_CFG", "songs/album-wz.json")).read_text())   # album-rl.json = English fork
SONGS = {s["n"]: s for s in CFG["songs"]}
COVERS = HERE / "covers/wynajete-zycie"
ANIM = HERE / "anim/wz"
SHARE = Path(os.environ.get("CA_SHARE", HERE / "share"))   # shared folder (NAS) used by both render machines
DROP = SHARE / CFG["album"]
GPU = r"draw-things-cli|mflux-generate|ltx-2-mlx|realesrgan|whisper-cli|demucs|acestep|generate\.py --caption"
LTX = Path(os.environ.get("LTX_MLX_BIN", "ltx-2-mlx"))   # dgrauet/ltx-2-mlx CLI
HUB = Path(os.environ.get("HF_HUB_CACHE", Path.home() / ".cache/huggingface/hub"))
ESR = HERE / "tools/realesrgan"


def vis(s):
    """Slug whose cover/loop/end photo a song uses (the English fork reuses the Polish visuals)."""
    return s.get("visual", s["slug"])


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def wait_gpu():
    while True:
        r = subprocess.run(["pgrep", "-fl", GPU], capture_output=True, text=True)
        busy = [l for l in r.stdout.splitlines() if "album_wz" not in l and "pgrep" not in l]
        if not busy:
            return
        log("waiting, GPU busy:", busy[0][:90])
        time.sleep(30)


def run(cmd, **kw):
    log("$", " ".join(str(c) for c in cmd)[:220])
    return subprocess.run([str(c) for c in cmd], stdin=subprocess.DEVNULL, **kw).returncode


def caption(s):
    v = "; ".join(CFG["voices"][c] for c in s["voices"])
    return f'{CFG["base"]}, {s["style"]}. Vocals: {v}. {CFG["quality"]}'


def stage_songs(ns, ref=None, ref_strength=0.25, suffix=""):
    for n in ns:
        s = SONGS[n]
        out = HERE / "output" / (s["slug"] + suffix)
        if not any(out.glob("*.mp3")):
            wait_gpu()
            cmd = [HERE / "ACE-Step-1.5/.venv/bin/python", HERE / "generate.py", "--shift", "3",
                   "--caption", caption(s), "--lyrics", HERE / f"songs/{s['slug']}.txt", "--language", "pl",
                   "--bpm", s["bpm"], "--key", s["key"], "--duration", math.ceil(s["d"]) + 1, "--out", out]
            if ref:
                cmd += ["--ref-audio", ref, "--ref-strength", ref_strength]
            t = time.time()
            rc = run(cmd)
            log(f"GEN {n} {s['slug']}{suffix} rc={rc} {time.time() - t:.0f}s")
            if rc:
                continue
        src = sorted(p for p in out.glob("*.mp3") if p.name != "final.mp3")[0]
        final = out / "final.mp3"
        d = s["d"]
        run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", src, "-t", d,
             "-af", f"afade=t=out:st={d - 2}:d=2", "-c:a", "libmp3lame", "-b:a", "192k", final])
        if suffix:
            continue
        tag(s, final)
        DROP.mkdir(parents=True, exist_ok=True)
        shutil.copy(HERE / f"tagged/{s['slug']}.mp3", DROP / f"{n:02d} - {s['title']}.mp3")
        log(f"SONG {n} ready: {DROP / f'{n:02d} - {s['title']}.mp3'}")


RENDER = SHARE / "_render/out"


def stage_import(ns):
    """Songs rendered on the PC (Windows PC, ACE-Step XL turbo + LM 4B): NAS FLAC -> trimmed MP3 -> tag -> review drop."""
    for n in ns:
        s = SONGS[n]
        src = RENDER / s["slug"] / f"{s['slug']}.flac"
        out = HERE / "output" / s["slug"]
        if not (RENDER / s["slug"] / "DONE").exists() or (DROP / f"{n:02d} - {s['title']}.mp3").exists():
            continue   # done = the review copy exists (a failed SMB copy is retried next pass)
        out.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, out / src.name)
        for extra in ("log",):
            p = src.with_suffix(f".{extra}")
            if p.exists():
                shutil.copy(p, out / p.name)
        d = s["d"]
        run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", out / src.name, "-t", d,
             "-af", f"afade=t=out:st={d - 2}:d=2", "-c:a", "libmp3lame", "-b:a", "256k", out / "final.mp3"])
        tag(s, out / "final.mp3", COVERS / f"{vis(s)}.png" if (COVERS / f"{vis(s)}.png").exists() else None)
        DROP.mkdir(parents=True, exist_ok=True)
        shutil.copy(HERE / f"tagged/{s['slug']}.mp3", DROP / f"{n:02d} - {s['title']}.mp3")
        log(f"IMPORT {n} ready: {DROP / f'{n:02d} - {s['title']}.mp3'}")


def tag(s, src, cover=None):
    dst = HERE / f"tagged/{s['slug']}.mp3"
    tmp = dst.with_suffix(".tmp.mp3")
    lyrics = (HERE / f"songs/{s['slug']}.txt").read_text()
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", src]
    if cover:
        cmd += ["-i", cover, "-map", "0:a", "-map", "1", "-c:v", "mjpeg", "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",
                "-metadata:s:v", "title=Album cover", "-metadata:s:v", "comment=Cover (front)"]
    cmd += ["-map_metadata", "-1", "-c:a", "copy", "-id3v2_version", "3",
            "-metadata", f"title={s['title']}", "-metadata", f"artist={CFG['artist']}",
            "-metadata", "album_artist=AI Music", "-metadata", f"album={CFG['album']}",
            "-metadata", f"genre={CFG['genre']}", "-metadata", f"date={time.strftime('%Y')}",
            "-metadata", f"language={'eng' if CFG.get('language') == 'en' else 'pol'}", "-metadata", f"lyrics={lyrics}",
            "-metadata", f"track={s['n']}/{len(SONGS)}",
            "-metadata", f"comment=ACE-Step 1.5 XL turbo + LM 4B (PC), {time.strftime('%F')}", tmp]
    if run(cmd) == 0:
        tmp.replace(dst)


def stage_covers(ns):
    prompts = json.loads((HERE / "covers/wynajete-zycie.json").read_text())
    COVERS.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    for n in ns:
        s = SONGS[n]
        png = COVERS / f"{vis(s)}.png"
        if png.exists():
            continue
        p = prompts["songs"][s["slug"]]["cover"].format(**prompts["members"]) + " " + prompts["style"]
        (COVERS / f"{s['slug']}.prompt.txt").write_text(p + "\n")
        wait_gpu()
        t = time.time()
        rc = run(["draw-things-cli", "generate", "--local", "--offline", "--disable-preview",
                  "--model", "z_image_turbo_1.0_q6p.ckpt", "--prompt-file", COVERS / f"{s['slug']}.prompt.txt",
                  "--width", 1536, "--height", 832, "--seed", 100 + n, "--output", png], env=env)
        log(f"COVER {n} rc={rc} {time.time() - t:.0f}s")
    share_ltx_inputs(ns)


LTX_SHARE = SHARE / "_render/ltx"


def ltx_input(s, dst):
    run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", COVERS / f"{vis(s)}.png",
         "-vf", "scale=896:-2:flags=lanczos,crop=896:448", dst])


def share_ltx_inputs(ns):
    """Put each cover's LTX input on the NAS so the Windows PC can render loops too."""
    (LTX_SHARE / "in").mkdir(parents=True, exist_ok=True)
    for n in ns:
        s = SONGS[n]
        dst = LTX_SHARE / "in" / f"{s['slug']}.png"
        if (COVERS / f"{vis(s)}.png").exists() and not dst.exists():
            ltx_input(s, dst)


def snapshot(repo):
    return next((HUB / f"models--{repo.replace('/', '--')}" / "snapshots").iterdir())


def stage_loops_all(ns):
    """Repeat the clip + assemble stages until every song has a loop (clips/upscales may come from the PC)."""
    for _ in range(300):
        stage_clips(ns)
        stage_assemble(ns)
        if all((ANIM / f"{SONGS[n]['slug']}-loop.mp4").exists() for n in ns):
            return
        time.sleep(60)


def stage_clips(ns):
    """LTX-2.3 clip per song on the Mac (unless the PC claimed/rendered it), shared to ltx/clips/ for upscaling."""
    prompts = json.loads((HERE / "covers/wynajete-zycie.json").read_text())
    env = dict(os.environ, HF_HUB_OFFLINE="1")
    (LTX_SHARE / "clips").mkdir(parents=True, exist_ok=True)
    claims = LTX_SHARE / "claims"
    claims.mkdir(parents=True, exist_ok=True)
    for n in ns:
        s = SONGS[n]
        d = ANIM / s["slug"]
        clip = d / "ltx.mp4"
        shared = LTX_SHARE / "clips" / f"{s['slug']}.mp4"
        pc = LTX_SHARE / "out" / s["slug"]
        if (ANIM / f"{vis(s)}-loop.mp4").exists() or not (COVERS / f"{vis(s)}.png").exists():
            continue
        if not clip.exists() and (pc / "DONE").exists():
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy(pc / f"{s['slug']}.mp4", clip)
            log(f"LTX {n} taken from the PC")
        if not clip.exists():
            if (claims / f"{s['slug']}.pc").exists():
                continue
            (claims / f"{s['slug']}.mac").touch()
            d.mkdir(parents=True, exist_ok=True)
            inp = d / "in.png"
            ltx_input(s, inp)
            wait_gpu()
            t = time.time()
            rc = run([LTX, "generate", "--model", snapshot("dgrauet/ltx-2.3-mlx-q4"),
                      "--gemma", snapshot("mlx-community/gemma-3-12b-it-4bit"), "--distilled", "--low-ram",
                      "--image", inp, "0", "1.0", "--image", inp, "96", "1.0",   # both ends = the cover: no drift/fade, loops
                      "-W", 896, "-H", 448, "-f", 97, "--frame-rate", 24,
                      "--seed", 7, "-p", prompts["songs"][s["slug"]]["motion"] + " " + prompts["motion_style"],
                      "-o", clip], env=env)
            log(f"LTX {n} rc={rc} {time.time() - t:.0f}s")
            if rc or not clip.exists():
                continue
        if not shared.exists():
            shutil.copy(clip, shared)
            log(f"CLIP {n} shared for upscaling: {shared}")


def stage_assemble(ns):
    """Upscaled clip from the PC (ltx/up/<slug>.mp4, 1920x960) -> seamless ping-pong 1080p loop."""
    for n in ns:
        s = SONGS[n]
        loop = ANIM / f"{vis(s)}-loop.mp4"
        up = LTX_SHARE / "up" / s["slug"]
        if loop.exists() or not (up / "DONE").exists():
            continue
        src = up / f"{s['slug']}.mp4"
        k = int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                                "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", src],
                               capture_output=True, text=True).stdout.strip() or 97)
        # forward + reverse without repeating the end frames = seamless ping-pong loop
        run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", src,
             "-filter_complex", "[0]scale=2160:1080:flags=lanczos,crop=1920:1080,"
             "split[a][b];[b]reverse,trim=start_frame=1,setpts=PTS-STARTPTS[r];[a][r]concat=n=2:v=1[v];"
             f"[v]trim=end_frame={2 * k - 2}[o]",
             "-map", "[o]", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", 18, "-pix_fmt", "yuv420p", loop])
        log(f"LOOP {n} ready: {loop}")


ENDCARD_PICKS = ["00-test", "a07-cassette-s1", "b01-garage-flash-s6", "b02-couch-press-photo-s3",
                 "b03-alley-neon-sign-s6", "b04-basement-gig-s1", "b05-vhs-crt-s2", "b08-after-show-s3",
                 "b09-motion-ghosts-s3", "b10-spray-painted-door-s1", "c01-from-the-crowd-s1",
                 "c02-singer-scream-s1", "c04-drummer-hit-s1", "w01-snowy-bench-s1", "w03-snowball-fight-s1",
                 "w07-playground-night-s1"]   # owner's pick of band photos (covers/channel/concepts)
ENDCARD_SECONDS = 6.0


def endcards():
    """Random band photo per song (no repeats), kept in covers/wynajete-zycie-endcards.json once drawn."""
    f = HERE / "covers/wynajete-zycie-endcards.json"
    if f.exists():
        return json.loads(f.read_text())
    import random
    picks = random.sample(ENDCARD_PICKS, len(SONGS))
    m = {vis(SONGS[n]): picks[i] for i, n in enumerate(sorted(SONGS))}
    f.write_text(json.dumps(m, indent=1))
    return m


def endcard_image(pid):
    ch = HERE / "covers/channel/concepts"
    return ch / "fixed" / f"{pid}.png" if (ch / "fixed" / f"{pid}.png").exists() else ch / f"{pid}.png"


LTX_HD = SHARE / "_render/ltx-hd"   # v2: native 1080p LTX from the PC, single anchor


def usable_frames(src, tol=0.08):
    """Frames from the start whose mean brightness stays within tol of frame 0 (LTX clips sometimes fade to black)."""
    out = subprocess.run(["ffprobe", "-v", "error", "-f", "lavfi", "-i",
                          f"movie={str(src).replace(':', chr(92) + ':')},signalstats",
                          "-show_entries", "frame_tags=lavfi.signalstats.YAVG", "-of", "csv=p=0"],
                         capture_output=True, text=True).stdout.split()
    y = [float(v.strip(",")) for v in out if v.strip(",")]
    if not y:
        return 0
    for i, v in enumerate(y):
        if abs(v - y[0]) > tol * max(y[0], 1):
            return i
    return len(y)


def stage_hdloops(ns):
    """PC's 1920x1088 LTX clip -> 1920x1080 seamless ping-pong loop anim/wz/<slug>-hdloop.mp4 (CPU)."""
    for n in ns:
        s = SONGS[n]
        src = LTX_HD / "out" / vis(s) / f"{vis(s)}.mp4"
        loop = ANIM / f"{vis(s)}-hdloop.mp4"
        if loop.exists() or not (src.parent / "DONE").exists():
            continue
        k = usable_frames(src)
        if k < 36:
            log(f"HDLOOP {n} skipped: only {k} frames before the brightness drifts (the HD still is used)")
            continue
        run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", src,
             "-filter_complex", f"[0]trim=end_frame={k},setpts=PTS-STARTPTS,crop=1920:1080,split[a][b];[b]reverse,trim=start_frame=1,setpts=PTS-STARTPTS[r];"
             f"[a][r]concat=n=2:v=1[v];[v]trim=end_frame={2 * k - 2}[o]",
             "-map", "[o]", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", 16, "-pix_fmt", "yuv420p", loop])
        log(f"HDLOOP {n} ready: {loop}")


def stage_videos(ns, static=False):
    """Background (1080p LTX loop, or the sharp HD still with static=True / no loop yet) over the song;
    last ENDCARD_SECONDS: fade to black, a band photo fades in and out to black."""
    out = HERE / "youtube" / CFG["album"]
    out.mkdir(parents=True, exist_ok=True)
    cards = endcards()
    for n in ns:
        s = SONGS[n]
        loop, mp3 = ANIM / f"{vis(s)}-hdloop.mp4", HERE / f"tagged/{s['slug']}.mp3"
        still = COVERS / "hd" / f"{vis(s)}.1080p.png"
        mp4 = out / f"{n:02d} - {s['title']}.mp4"
        use_loop = loop.exists() and not static
        if not mp3.exists() or not (use_loop or still.exists()):
            continue
        d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp3],
                                 capture_output=True, text=True).stdout)
        t = ENDCARD_SECONDS
        src = ["-stream_loop", -1, "-i", loop] if use_loop else ["-loop", 1, "-framerate", 24, "-i", still]
        fc = (f"[0:v]trim=duration={d - t:.3f},setpts=PTS-STARTPTS,fps=24,format=yuv420p,"
              f"fade=t=out:st={d - t - 0.8:.3f}:d=0.8[a];"
              f"[1:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=24,format=yuv420p,"
              f"trim=duration={t},setpts=PTS-STARTPTS,fade=t=in:st=0:d=1.2,fade=t=out:st={t - 1.5}:d=1.5[b];"
              "[a][b]concat=n=2:v=1:a=0[v]")
        rc = run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *src,
                  "-loop", 1, "-i", endcard_image(cards[vis(s)]), "-i", mp3,
                  "-filter_complex", fc, "-map", "[v]", "-map", "2:a",
                  "-c:v", "libx264", "-preset", "medium", "-crf", 18, "-c:a", "aac", "-b:a", "256k",
                  "-t", f"{d:.3f}", "-movflags", "+faststart", mp4])
        if rc:
            log(f"VIDEO {n} failed rc={rc}")
            continue
        DROP.mkdir(parents=True, exist_ok=True)
        shutil.copy(mp4, DROP / mp4.name)
        log(f"VIDEO {n} ready ({'1080p loop' if use_loop else 'HD still'}): {DROP / mp4.name} (end photo {cards[vis(s)]})")


def main():
    args = sys.argv[1:]
    opts = {}
    args = [a for a in args if a != "--static"]
    for k in ("--ref", "--ref-strength", "--suffix"):
        if k in args:
            i = args.index(k); opts[k] = args[i + 1]; del args[i:i + 2]
    stage, ns = args[0], [int(x) for x in args[1:]] or sorted(SONGS)
    if stage == "songs":
        stage_songs(ns, opts.get("--ref"), float(opts.get("--ref-strength", 0.25)), opts.get("--suffix", ""))
    elif stage == "import":
        stage_import(ns)
    elif stage == "share":
        share_ltx_inputs(ns)
    elif stage == "covers":
        stage_covers(ns)
    elif stage == "loops":
        stage_loops_all(ns)
    elif stage == "hdloops":
        stage_hdloops(ns)
    elif stage == "videos":
        stage_videos(ns, static="--static" in sys.argv)
    log(f"STAGE {stage} DONE")


if __name__ == "__main__":
    main()
