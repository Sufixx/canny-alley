# AGENTS.md — reproducing Canny Alley

Guidelines for an AI coding agent (or a person) who wants to recreate the band, make a new album in the same
style, or rebuild the videos. Read [`README.md`](README.md) first for the overview; this file holds the rules,
the exact parameters and the mistakes not to repeat.

## 0. Hard rules

1. **One heavy GPU job per machine at a time.** ACE-Step, Z-Image, LTX, Real-ESRGAN and whisper each take
   10–15 GB. Two at once on a 24 GB Mac hung and rebooted it. Run long batches detached (`nohup … &`) and make
   every queue wait for the previous GPU process (`pgrep`) before starting.
2. **The four members never change.** Copy their look and voice blocks from `band/band.json` word for word into
   every prompt and caption. Do not paraphrase, do not add a fifth person, keep "in their twenties".
3. **Backgrounds show members in the scene's everyday clothes, never stage clothes, never instruments** (unless
   the scene is a concert). They blend into the scene or just stand there.
4. **Natural vocals.** Every caption ends with "natural vocals, no autotune, in tune, clear Polish diction".
5. **Nothing is published by the pipeline.** Finished MP3/MP4 go to a review folder; a human decides what is
   uploaded where. Every upload carries the platform's AI-content label.

## 1. Band look (images)

- Model: **Z-Image Turbo 1.0** (Draw Things CLI `draw-things-cli generate --model z_image_turbo_1.0_q6p.ckpt`,
  or mflux `mflux-generate-z-image-turbo`). Recommended settings: 8 steps, CFG 1, shift 3.
- Size: multiples of 64; **≤1536 px** on the long side for best detail (1536×832 for 16:9 backgrounds,
  1024×1024 for square). 2048×1152 works but faces get mushy.
- Prompt = scene + member blocks + style block. Style used for the photo look:
  `Grainy amateur 35mm film photograph, point-and-shoot camera, realistic skin texture, … violet and blue neon …`
  (see `prompts/channel-concepts.json` and `prompts/band-photos-winter-live.json`).
- **Face pass** for group shots (`scripts/detect_faces.py` + `scripts/facefix.py`): detect faces with Apple
  Vision, label each face with a member letter (`prompts/face_labels.json`), re-render a 1024² crop of each face
  with img2img at strength 0.5 (<75 px faces) / 0.45 (<110 px) / 0.4 (larger) using that member's description,
  then match colour and grain and feather it back. More steps at the same seed does **not** fix faces.
- Channel banner: YouTube shows only the centre strip on desktop (2560×423 of 2560×1440) and a 1546×423 box on
  every device. Put all faces inside that box (shift/zoom the photo, fill the edges with a blurred, darkened edge
  extension — not a mirror, which duplicates people).

## 2. Songs (ACE-Step 1.5)

- Best quality: **`acestep-v15-xl-turbo` + `acestep-5Hz-lm-4B`** with CPU offload (12 GB VRAM + 64 GB RAM is
  enough; ~2 min per 3.5 min song). On a 24 GB Apple Silicon Mac the XL pair runs out of memory; use
  `acestep-v15-turbo` + `acestep-5Hz-lm-1.7B` on MLX (`scripts/generate.py`, ~3–6 min per song).
- Parameters: `inference_steps 8`, `shift 3.0`, fixed `bpm` and `keyscale` per song, `thinking` on,
  `seed 1000+N`, `duration = ceil(d)+1` then trim to `d` with a 2 s fade-out
  (`ffmpeg -t d -af afade=t=out:st=d-2:d=2`). The exact jobs are in `albums/wynajete-zycie/song-jobs/`.
- Caption = `base` + per-song `style` + the voice blocks actually used + `quality`
  (`albums/wynajete-zycie/album.json`; `scripts/album_wz.py: caption()`).
- Album rules the owner set: Polish cold wave with rock and electronic elements; every key and tempo
  different; no piano (name synths, organ and guitars instead); solos on guitar or synth; bridges, drops,
  slowdowns and climaxes; random lengths between 144 and 251 s.
- Lyrics: about 0.12 sung lines per second of song (≈18 lines for 2:24, ≈30 for 4:11), fewer when there is a
  solo. Section tags name the singer and the dynamics:
  `[Verse 2 - deep low female vocal]`, `[Bridge - high airy female vocal, half-time, sparse]`,
  `[Guitar solo - noisy, chorus-drenched]`, `[Breakdown - sudden drop, bass and voice only]`.
- Voices: at most two in normal sections; the high soprano only in bridges/climaxes or one feature song; the
  keyboardist's hum in ~3 songs per album, always "far in the background".
- `generate.py --ref-audio <song.mp3> --ref-strength 0.25` passes a reference track for timbre continuity
  (ACE-Step "reference audio"); it was added but not evaluated.

## 3. Song backgrounds and loops

1. **Background:** Z-Image 1536×832, prompt from `albums/wynajete-zycie/backgrounds.json` (`cover` with
   `{R}/{M}/{B}/{D}` replaced by the member blocks, plus `style`). Avoid readable text: write "no posters, no
   writing anywhere" — fake posters come out as gibberish. Prefer evenly lit scenes; very dark covers fade.
2. **Sharpen:** Real-ESRGAN `realesrgan-x4plus -s 4`, then scale/crop to exactly **1920×1088** (LTX input) and
   1920×1080 (static fallback).
3. **LTX-2.3** image-to-video (`albums/wynajete-zycie/ltx-hd-jobs/`): two-stage distilled pipeline, base
   960×544 → output 1920×1088, **65 frames**, 24 fps, seed 7 (retry seed 9), **image anchored at frame 0
   only, strength 1.0**, no audio. On 12 GB VRAM: bf16 weights with `fp8-cast` and CPU offload; Windows needed
   a page file of 16–68 GB (or a 64 GB initial size) to load 46 GB of weights plus Gemma 3.
   - Do **not** anchor the last frame: at 1.0 the clip is frozen, even 0.4 cuts motion 16×.
   - Motion prompt: describe people (breathe, blink, turn heads) and objects (steam, dust, snow, curtain) moving,
     end with "The lighting stays the same, no light turns off, no fade to black". Never ask light to flicker,
     shimmer, twinkle or pulse — that is what makes LTX fade to black. Standing crowds hold; walking crowds fade.
4. **Loop:** measure mean brightness per frame (ffmpeg `signalstats`), keep the frames within 8 % of frame 0
   (need ≥36), crop to 1920×1080, play forward then backward (ping-pong) — seamless.
   `scripts/album_wz.py hdloops`.
5. **Video:** loop under the song; the last 6 s fade the loop to black (0.8 s), a band photo fades in (1.2 s),
   holds and fades out (1.5 s) as the song ends (`scripts/album_wz.py videos`; photo per song in
   `endcards.json`). Songs whose clip is unusable use the sharpened still.

## 4. Two-machine split (optional)

A Mac and a Windows/NVIDIA PC shared one NAS folder (`$CA_SHARE`): `_render/jobs/*.json` → the PC renders
`_render/out/<slug>/<slug>.flac + .log + DONE`; LTX inputs in `_render/ltx-hd/in/`, jobs in
`_render/ltx-hd/jobs/`, clips in `_render/ltx-hd/out/<slug>/`. When both machines render LTX, each creates
`claims/<slug>.mac|.pc` before starting a song and skips songs the other has claimed. The PC was about 2× faster
at LTX and ~10× faster at Real-ESRGAN than the M4 Mac.

## 5. Scripts

The scripts in `scripts/` are copies of the working pipeline. They expect the original working layout:

```
<work>/generate.py            ACE-Step wrapper (MLX on Apple Silicon)
<work>/songs/album-wz.json    (= albums/wynajete-zycie/album.json)  + songs/<slug>.txt lyrics
<work>/songs/album_wz.py      stages: songs | import | covers | share | loops | hdloops | videos
<work>/covers/wynajete-zycie.json and covers/wynajete-zycie/{,hd/}   backgrounds
<work>/covers/channel/        run_concepts.py, gallery.py, facefix.py, detect_faces.py, concepts/
<work>/ACE-Step-1.5/          upstream ACE-Step clone with its own venv and checkpoints/
<work>/tools/realesrgan/      realesrgan-ncnn-vulkan + models
```

Environment variables: `CA_SHARE` (shared folder, default `./share`), `DRAWTHINGS_MODELS_DIR`,
`HF_HUB_CACHE`, `LTX_MLX_BIN` (the `ltx-2-mlx` CLI). Python 3.11+; the image scripts need numpy + OpenCV,
`detect_faces.py` needs pyobjc (macOS Vision).

## 6. Before calling an album done

- Listen to every song once; check the singers match the section tags and nothing is cut off at the trim.
- Look at three frames of every loop (start, middle, end): same brightness, visible motion, no warped faces.
- Check that every background shows the members, in scene clothes, without readable fake text.
- Upload metadata: title "Canny Alley – <title>", description = album line + lyrics + the AI note ending with
  "A tak naprawdę to nie istniejemy.", language Polish, AI label "yes", not made for kids, album playlist.
