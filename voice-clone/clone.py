"""Phase 3: 参照音声（自分の声）＋文字起こしから、日本語テキストを自分の声で読み上げる。

使い方:
  ./run.sh --ref-audio refs/me.wav --ref-text "参照音声で話している内容" \
           --text "こんにちは。今日は錫奏AIクローンボイスの動作確認をしています。"

出力（outputs/ 以下、元の参照音声には一切書き込まない）:
  <日時>_<先頭の文字>.wav          生成音声
  <日時>_<先頭の文字>_compare.wav  参照音声 → 無音0.7秒 → 生成音声 をつないだ聞き比べ用
  history.jsonl                    入力文・モデル・設定・結果の記録（1生成1行）
"""

import argparse
import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "outputs"
HISTORY = OUT_DIR / "history.jsonl"


def default_model():
    path = ROOT / "model.txt"
    if path.exists():
        return path.read_text().strip()
    return "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit"


def read_arg_or_file(value, file):
    if file:
        return Path(file).read_text(encoding="utf-8").strip()
    return value.strip() if value else None


def slug(text, n=12):
    s = re.sub(r"[\s\\/:*?\"<>|。、！？!?,.]+", "", text)
    return s[:n] or "audio"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def append_history(record):
    OUT_DIR.mkdir(exist_ok=True)
    with open(HISTORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_list(value, cast):
    return [cast(v) for v in str(value).split(",") if v.strip()]


def main():
    p = argparse.ArgumentParser(description="Qwen3-TTS (mlx-audio) で自分の声をクローンして読み上げる")
    p.add_argument("--ref-audio", required=True, help="参照音声（自分の声のみ、5〜10秒、BGM/SEなし）")
    p.add_argument("--ref-text", help="参照音声の文字起こし（一字一句）")
    p.add_argument("--ref-text-file", help="文字起こしをファイルで渡す場合")
    p.add_argument("--text", help="読み上げる文章")
    p.add_argument("--text-file", help="読み上げる文章をファイルで渡す場合（改行ごとに分割して生成し、1つにつなぐ）")
    p.add_argument("--model", default=default_model())
    p.add_argument("--lang", default="japanese", help="言語（auto / japanese など）")
    p.add_argument("--temperature", default="0.9", help="カンマ区切りで複数指定可（例: 0.8,1.0）")
    p.add_argument("--top-p", type=float, default=1.0)
    p.add_argument("--top-k", type=int, default=50)
    p.add_argument("--repetition-penalty", type=float, default=1.05)
    p.add_argument("--seed", default="0", help="カンマ区切りで複数指定可（例: 0,1,2）。同じ値なら同じ結果になりやすい")
    p.add_argument("--name", help="出力ファイル名（拡張子なし）。省略時は日時＋文章の先頭")
    p.add_argument("--play", action="store_true", help="生成後に afplay で 参照→生成 の順に再生")
    args = p.parse_args()

    ref_text = read_arg_or_file(args.ref_text, args.ref_text_file)
    text = read_arg_or_file(args.text, args.text_file)
    if not ref_text:
        p.error("--ref-text か --ref-text-file が必要です")
    if not text:
        p.error("--text か --text-file が必要です")
    ref_path = Path(args.ref_audio).expanduser().resolve()
    if not ref_path.exists():
        p.error(f"参照音声が見つかりません: {ref_path}")
    temperatures = parse_list(args.temperature, float)
    seeds = parse_list(args.seed, int)
    variants = [(t, s) for t in temperatures for s in seeds]

    OUT_DIR.mkdir(exist_ok=True)
    stem = args.name or f"{datetime.now():%Y%m%d-%H%M%S}_{slug(text)}"
    jobs = []
    for t, s in variants:
        name = stem if len(variants) == 1 else f"{stem}_{ref_path.stem}_t{t}_s{s}"
        out_wav = OUT_DIR / f"{name}.wav"
        if out_wav.exists():
            p.error(f"同名の出力が既にあります（上書きしません）: {out_wav}")
        jobs.append((t, s, out_wav, OUT_DIR / f"{name}_compare.wav"))

    import mlx.core as mx
    import numpy as np
    from mlx_audio.audio_io import write as audio_write
    from mlx_audio.tts.utils import load_model
    from mlx_audio.utils import load_audio

    base = {
        "model": args.model,
        "mlx_audio": importlib.metadata.version("mlx-audio"),
        "mlx": importlib.metadata.version("mlx"),
        "ref_audio": str(ref_path),
        "ref_audio_sha256": sha256(ref_path),
        "ref_text": ref_text,
        "text": text,
    }

    t0 = time.time()
    model = load_model(args.model)
    load_seconds = round(time.time() - t0, 2)
    sr = model.sample_rate

    langs = model.get_supported_languages()
    if args.lang != "auto" and args.lang not in langs:
        print(f"警告: '{args.lang}' はこのモデルの言語一覧 {langs} にありません（autoとして扱われます）")

    ref = np.array(load_audio(str(ref_path), sample_rate=sr))
    ref_sec = len(ref) / sr
    if not 3 <= ref_sec <= 15:
        print(f"警告: 参照音声が {ref_sec:.1f} 秒です。5〜10秒程度を推奨します")

    done, failed = [], 0
    for temperature, seed, out_wav, cmp_wav in jobs:
        record = dict(
            base,
            time=datetime.now().isoformat(timespec="seconds"),
            load_seconds=load_seconds,
            ref_seconds=round(ref_sec, 2),
            settings={
                "lang": args.lang,
                "temperature": temperature,
                "top_p": args.top_p,
                "top_k": args.top_k,
                "repetition_penalty": args.repetition_penalty,
                "seed": seed,
            },
        )
        try:
            mx.random.seed(seed)
            t1 = time.time()
            segments, peak = [], 0.0
            for r in model.generate(
                text=text,
                ref_audio=mx.array(ref),
                ref_text=ref_text,
                lang_code=args.lang,
                temperature=temperature,
                top_p=args.top_p,
                top_k=args.top_k,
                repetition_penalty=args.repetition_penalty,
                split_pattern="\n",
            ):
                segments.append(np.array(r.audio))
                peak = max(peak, r.peak_memory_usage)
            gen_sec = time.time() - t1

            audio = np.concatenate(segments)
            audio_write(str(out_wav), audio, sr)
            gap = np.zeros(int(sr * 0.7), dtype=audio.dtype)
            audio_write(str(cmp_wav), np.concatenate([ref.astype(audio.dtype), gap, audio]), sr)

            out_sec = len(audio) / sr
            record.update(
                status="ok",
                output=str(out_wav),
                compare=str(cmp_wav),
                segments=len(segments),
                output_seconds=round(out_sec, 2),
                generate_seconds=round(gen_sec, 2),
                real_time_factor=round(gen_sec / out_sec, 2) if out_sec else None,
                peak_memory_gb=round(peak, 2),
            )
            append_history(record)
            done.append(out_wav)
            print(f"生成: {out_wav.name}  ({out_sec:.1f}秒の音声を {gen_sec:.1f}秒で生成, ピークメモリ {peak:.2f}GB)")
        except Exception as e:
            record.update(status="error", error=f"{type(e).__name__}: {e}", traceback=traceback.format_exc())
            append_history(record)
            failed += 1
            print(f"エラー（temperature={temperature}, seed={seed}）: {e}（詳細は {HISTORY}）", file=sys.stderr)

    if len(jobs) == 1 and done:
        print(f"聞き比べ: {jobs[0][3]}")
        if args.play:
            subprocess.run(["afplay", str(jobs[0][3])], check=False)
    elif args.play:
        for out_wav in done:
            print(f"再生: {out_wav.name}")
            subprocess.run(["afplay", str(out_wav)], check=False)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
