"""聞き比べ用のまとめ: history.jsonl から、参照音声×文章ごとに似かたスコアが一番高い生成を選び、
参照音声ごとに1本の WAV（outputs/best_<参照名>.wav）へつなぐ。文と文の間は1秒あける。

使い方: ./pick.sh            （つないだあと、参照音声ごとに順番に再生する）
        ./pick.sh --no-play
"""

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "outputs"
HISTORY = OUT_DIR / "history.jsonl"


def main():
    p = argparse.ArgumentParser(description="似かたスコアが一番高い生成を参照音声ごとに1本へまとめる")
    p.add_argument("--no-play", action="store_true")
    args = p.parse_args()

    import numpy as np
    from mlx_audio.audio_io import write as audio_write
    from mlx_audio.utils import load_audio

    best = {}
    order = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        score = r.get("speaker_similarity")
        if r.get("status") != "ok" or score is None or not Path(r["output"]).exists():
            continue
        ref = Path(r["ref_audio"]).stem
        key = (ref, r["text"])
        if key not in best:
            order.append(key)
        if key not in best or score > best[key]["speaker_similarity"]:
            best[key] = r

    if not best:
        print("似かたスコア付きの生成がまだありません。先に run.sh で生成してください")
        return

    refs = list(dict.fromkeys(ref for ref, _ in order))
    made = []
    for ref in refs:
        rows = [best[k] for k in order if k[0] == ref]
        sr = 24000
        pieces = []
        print(f"\n[{ref}]")
        for i, r in enumerate(rows, 1):
            audio = np.array(load_audio(r["output"], sample_rate=sr))
            pieces += [audio, np.zeros(sr, dtype=audio.dtype)]
            print(f"  {i}. {r['speaker_similarity']:.3f}  {r['text'][:30]}  ({Path(r['output']).name})")
        out = OUT_DIR / f"best_{ref}.wav"
        audio_write(str(out), np.concatenate(pieces), sr)
        made.append(out)
        print(f"  → {out.name}")

    if not args.no_play:
        for out in made:
            print(f"\n再生: {out.name}")
            subprocess.run(["afplay", str(out)], check=False)


if __name__ == "__main__":
    main()
