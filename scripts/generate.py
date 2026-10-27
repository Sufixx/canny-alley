#!/usr/bin/env python3
"""Generate a song locally with ACE-Step 1.5 (MLX on Apple Silicon).

Run with the ACE-Step venv:
    ACE-Step-1.5/.venv/bin/python generate.py --caption "..." --lyrics lyrics.txt --duration 120
"""
import argparse
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ACE = HERE / "ACE-Step-1.5"
sys.path.insert(0, str(ACE))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("ACESTEP_LM_BACKEND", "mlx")


def patch_mlx_conversion(bf16: bool):
    """Make the PyTorch->MLX DiT conversion free each torch tensor as soon as it is copied.

    Upstream keeps the full fp32 torch decoder on MPS *and* an fp32 MLX copy, which is
    two copies of the model in unified memory (XL: about 42 GB, out of memory on 24 GB). The torch
    decoder is only needed for lyric timestamps/scoring, which this script never uses.
    """
    import torch
    import mlx.core as mx
    from acestep.models.mlx import dit_convert

    def convert_and_load(pytorch_model, mlx_decoder):
        dec = pytorch_model.decoder
        weights = []
        tensors = list(dec.named_parameters()) + list(dec.named_buffers())
        for key, t in tensors:
            if "rotary_emb" in key:
                continue
            val = t.detach().cpu().float().numpy()
            new_key = key
            if key.startswith("proj_in.1."):
                new_key = key.replace("proj_in.1.", "proj_in.")
                if new_key.endswith(".weight"):
                    val = val.swapaxes(1, 2)
            elif key.startswith("proj_out.1."):
                new_key = key.replace("proj_out.1.", "proj_out.")
                if new_key.endswith(".weight"):
                    val = val.transpose(1, 2, 0)
            arr = mx.array(val)
            if bf16 and arr.dtype == mx.float32:
                arr = arr.astype(mx.bfloat16)
            mx.eval(arr)
            weights.append((new_key, arr))
            t.data = torch.empty(0, dtype=t.dtype, device=t.device)
            del val
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
        mlx_decoder.load_weights(weights)
        mx.eval(mlx_decoder.parameters())
        del weights
        mx.clear_cache()  # drop the transient conversion buffers MLX keeps cached
        print(f"[generate.py] MLX DiT loaded ({'bf16' if bf16 else 'fp32'}), torch decoder freed", flush=True)

    dit_convert.convert_and_load = convert_and_load


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--caption", required=True, help="style description: genre, instruments, mood, vocal type")
    p.add_argument("--lyrics", help="path to a lyrics file ([Verse]/[Chorus] tags), or '-' for stdin")
    p.add_argument("--instrumental", action="store_true")
    p.add_argument("--language", default="unknown", help="vocal language code, e.g. en, pl")
    p.add_argument("--duration", type=float, default=-1, help="seconds (default: let the LM decide)")
    p.add_argument("--bpm", type=int)
    p.add_argument("--key", default="", help='e.g. "C major", "A minor"')
    p.add_argument("--seed", type=int, default=-1)
    p.add_argument("--count", type=int, default=1, help="number of variants")
    p.add_argument("--steps", type=int, default=8, help="diffusion steps (turbo: 8)")
    p.add_argument("--shift", type=float, default=1.0, help="timestep shift (docs recommend 3.0 for turbo)")
    p.add_argument("--model", default="acestep-v15-turbo")
    p.add_argument("--lm", default="acestep-5Hz-lm-1.7B", help="LM model, or 'none' to skip it")
    p.add_argument("--bf16", action="store_true", help="keep MLX DiT weights in bf16 (default for XL models)")
    p.add_argument("--keep-torch-dit", action="store_true", help="upstream behaviour: keep the duplicate torch decoder")
    p.add_argument("--ref-audio", help="reference track for style/timbre guidance (e.g. keep a band's voices across an album)")
    p.add_argument("--ref-strength", type=float, default=0.25, help="reference influence 0..1 (docs: ~0.2 for style transfer)")
    p.add_argument("--format", default="mp3", choices=["mp3", "flac", "wav"])
    p.add_argument("--out", default=str(HERE / "output"))
    a = p.parse_args()

    lyrics = ""
    if a.lyrics == "-":
        lyrics = sys.stdin.read()
    elif a.lyrics:
        lyrics = Path(a.lyrics).read_text()

    a.out = str(Path(a.out).resolve())
    if a.ref_audio:
        a.ref_audio = str(Path(a.ref_audio).resolve())
    os.chdir(ACE)  # the pipeline resolves checkpoints/ relative to the project
    from acestep.handler import AceStepHandler
    from acestep.llm_inference import LLMHandler
    from acestep.inference import GenerationParams, GenerationConfig, generate_music

    if not a.keep_torch_dit:
        patch_mlx_conversion(bf16=a.bf16 or "xl" in a.model)

    t0 = time.time()
    dit = AceStepHandler()
    msg, ok = dit.initialize_service(project_root=str(ACE), config_path=a.model, device="auto")
    if not ok:
        sys.exit(f"DiT init failed: {msg}")
    llm = LLMHandler()
    if a.lm != "none":
        msg, ok = llm.initialize(checkpoint_dir=str(ACE / "checkpoints"), lm_model_path=a.lm,
                                 backend="mlx", device="auto")
        if not ok:
            sys.exit(f"LM init failed: {msg}")
    try:
        import mlx.core as mx
        mx.clear_cache()
    except Exception:
        pass
    print(f"models loaded in {time.time() - t0:.0f}s", flush=True)

    params = GenerationParams(
        caption=a.caption, lyrics=lyrics, instrumental=a.instrumental or not lyrics and a.lm == "none",
        vocal_language=a.language, duration=a.duration, bpm=a.bpm, keyscale=a.key,
        seed=a.seed, inference_steps=a.steps, shift=a.shift, thinking=a.lm != "none",
        **({"reference_audio": str(Path(a.ref_audio).resolve()), "audio_cover_strength": a.ref_strength}
           if a.ref_audio else {}),
    )
    config = GenerationConfig(batch_size=a.count, audio_format=a.format,
                              use_random_seed=a.seed < 0, seeds=[a.seed] if a.seed >= 0 else None)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    t1 = time.time()
    res = generate_music(dit, llm, params, config, save_dir=a.out)
    if not res.success:
        sys.exit(f"generation failed: {res.error}")
    print(f"generated in {time.time() - t1:.0f}s")
    for au in res.audios:
        print(f"  {au['path']}  seed={au['params'].get('seed')}")


if __name__ == "__main__":
    main()
