"""Irodori-TTS（日本語専用・MLX 版）で、自分の声の参照クリップから台本を読み上げる。

参照音声の文字起こしは不要。複数クリップ（合計120秒まで）を渡すと、まとめて声の特徴として使う。
文の分け方・読み仮名の辞書・文末の整え方・履歴の記録は clone.py と共通。

使い方:
  ./irodori.sh --ref "calm_*" --text-file 台本_特急.txt --join-lines
  ./irodori.sh --ref "calm_*" --text "こんにちは。" --instruct "落ち着いた語り口で、近い距離感で話す"
"""

import argparse
import importlib.metadata
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from clone import (
    HISTORY,
    OUT_DIR,
    ROOT,
    append_history,
    apply_readings,
    join_lines,
    load_readings,
    parse_list,
    read_arg_or_file,
    slug,
    split_text,
    tidy_segment,
)

DEFAULT_MODEL = "mlx-community/Irodori-TTS-v4.1-Small-8bit"


def ensure_model(model_id):
    """未取得なら、サイズとライセンスを表示して確認してからダウンロードする"""
    from huggingface_hub import HfApi, snapshot_download

    try:
        return snapshot_download(model_id, local_files_only=True)
    except Exception:
        pass
    size, license_ = "不明", "不明"
    try:
        info = HfApi().model_info(model_id, files_metadata=True)
        size = f"{sum((s.size or 0) for s in info.siblings) / 1e9:.2f}GB"
        license_ = (info.card_data or {}).get("license", "不明") if info.card_data else "不明"
    except Exception:
        pass
    print(f"モデルが未取得です: https://huggingface.co/{model_id}")
    print(f"  サイズ: {size} / ライセンス: {license_} / 保存先: このフォルダ内の hf-home/")
    if input("ダウンロードしますか？ [y/N]: ").strip().lower() != "y":
        sys.exit("中止しました")
    return snapshot_download(model_id)


def main():
    p = argparse.ArgumentParser(description="Irodori-TTS で自分の声をクローンして読み上げる")
    p.add_argument("--ref", required=True, help="refs/ 内の参照クリップ名。ワイルドカード可（例: \"calm_*\"）。カンマ区切りで複数指定も可")
    p.add_argument("--text", help="読み上げる文章")
    p.add_argument("--text-file", help="読み上げる文章をファイルで渡す場合")
    p.add_argument("--instruct", help="話し方の指定（例: 落ち着いた語り口で、近い距離感で話す）")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--seed", default="0,1,2", help="カンマ区切りで複数指定可")
    p.add_argument("--speed", type=float, default=1.0, help="話す速さ（0.5〜2.0）。モデルの長さ予測を調整する")
    p.add_argument("--steps", type=int, help="生成ステップ数（少ないほど速く、品質は下がる）")
    p.add_argument("--join-lines", action="store_true", help="行をまたぐ台本向けの区切り方")
    p.add_argument("--max-chars", type=int, default=40, help="1回に読ませる最大文字数")
    p.add_argument("--pause", type=float, default=1.0, help="文と文の間の長さの倍率（0.5で半分、0で間なし）")
    p.add_argument("--no-split", action="store_true")
    p.add_argument("--no-tidy", action="store_true")
    p.add_argument("--dict", default=str(ROOT / "dict.tsv"))
    p.add_argument("--name", help="出力ファイル名（拡張子なし）")
    p.add_argument("--play", action="store_true")
    args = p.parse_args()

    text = read_arg_or_file(args.text, args.text_file)
    if not text:
        p.error("--text か --text-file が必要です")
    if not 0.5 <= args.speed <= 2.0:
        p.error("--speed は 0.5〜2.0 で指定してください")

    refs = []
    for pattern in args.ref.split(","):
        refs += sorted((ROOT / "refs").glob(pattern.strip() + ("" if pattern.endswith(".wav") else ".wav")))
    if not refs:
        p.error(f"refs/ に参照クリップが見つかりません: {args.ref}")

    spoken = apply_readings(text, load_readings(Path(args.dict)))
    if args.no_split:
        chunks = [(spoken, 0.0)]
    elif args.join_lines:
        chunks = join_lines(spoken, max_len=args.max_chars)
    else:
        chunks = split_text(spoken, max_len=args.max_chars)
    seeds = parse_list(args.seed, int)

    OUT_DIR.mkdir(exist_ok=True)
    stem = args.name or f"{datetime.now():%Y%m%d-%H%M%S}_{slug(text)}"
    jobs = []
    for seed in seeds:
        name = stem if len(seeds) == 1 else f"{stem}_irodori_s{seed}"
        out_wav = OUT_DIR / f"{name}.wav"
        if out_wav.exists():
            p.error(f"同名の出力が既にあります（上書きしません）: {out_wav}")
        jobs.append((seed, out_wav))

    ensure_model(args.model)

    import subprocess

    import numpy as np
    from mlx_audio.audio_io import write as audio_write
    from mlx_audio.tts.utils import load_model

    model = load_model(args.model)
    sr = model.sample_rate
    print(f"参照クリップ {len(refs)} 本: {', '.join(r.name for r in refs)}")

    extra = {"duration_scale": 1.0 / args.speed}
    if args.steps:
        extra["num_steps"] = args.steps

    done = []
    for seed, out_wav in jobs:
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "engine": "irodori",
            "model": args.model,
            "mlx_audio": importlib.metadata.version("mlx-audio"),
            "ref_audio": [str(r) for r in refs],
            "text": text,
            "spoken_text": spoken,
            "chunks": [c for c, _ in chunks],
            "settings": {"seed": seed, "speed": args.speed, "pause": args.pause, "instruct": args.instruct, "steps": args.steps,
                         "tidy": not args.no_tidy},
        }
        try:
            t1 = time.time()
            pieces, peak = [], 0.0
            for i, (chunk, pause) in enumerate(chunks):
                seg = []
                for r in model.generate(text=chunk, ref_audio=[str(x) for x in refs], instruct=args.instruct,
                                        rng_seed=seed + 1000 * i, **extra):
                    seg.append(np.array(r.audio))
                    peak = max(peak, r.peak_memory_usage)
                seg = np.concatenate(seg)
                if not args.no_tidy:
                    seg = tidy_segment(seg, sr)
                pieces += [seg, np.zeros(int(sr * pause * args.pause), dtype=seg.dtype)]
            gen_sec = time.time() - t1
            audio = np.concatenate(pieces)
            audio_write(str(out_wav), audio, sr)
            out_sec = len(audio) / sr
            record.update(status="ok", output=str(out_wav), output_seconds=round(out_sec, 2),
                          generate_seconds=round(gen_sec, 2), peak_memory_gb=round(peak, 2))
            append_history(record)
            done.append(out_wav)
            print(f"生成: {out_wav.name}  ({out_sec:.1f}秒の音声を {gen_sec:.1f}秒で生成, ピークメモリ {peak:.2f}GB)")
        except Exception as e:
            record.update(status="error", error=f"{type(e).__name__}: {e}", traceback=traceback.format_exc())
            append_history(record)
            print(f"エラー（seed={seed}）: {e}（詳細は {HISTORY}）", file=sys.stderr)

    if args.play:
        for out_wav in done:
            print(f"再生: {out_wav.name}")
            subprocess.run(["afplay", str(out_wav)], check=False)
    if not done:
        sys.exit(1)


if __name__ == "__main__":
    main()
