"""Phase 3: 参照音声（自分の声）＋文字起こしから、日本語テキストを自分の声で読み上げる。

使い方:
  ./run.sh --text "こんにちは。今日は錫奏AIクローンボイスの動作確認をしています。"
  （参照音声・温度・seed は defaults.json の値。--ref ref_b などで切り替え）

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
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "outputs"
HISTORY = OUT_DIR / "history.jsonl"


def load_defaults():
    """defaults.json（あれば）から既定の参照音声・温度・seed を読む"""
    path = ROOT / "defaults.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


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


SENTENCE_END = "。！？!?"
MAX_RETRY = 2
PAUSE = {"sentence": 0.35, "comma": 0.15, "line": 0.5}


def split_text(text, max_len=40, min_len=10):
    """文末（。！？）と改行で区切る。max_len を超える文だけ読点でさらに区切る。
    min_len 未満の短い文（「こんにちは。」など）は次の文とまとめて読ませる。

    戻り値は (チャンク, 後ろに入れる無音の秒数) のリスト。
    """
    chunks = []
    for line in [l.strip() for l in text.splitlines() if l.strip()]:
        sentences = re.findall(rf"[^{SENTENCE_END}]+[{SENTENCE_END}]*", line)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) <= max_len:
                chunks.append([sentence, PAUSE["sentence"]])
                continue
            buf = ""
            for piece in re.findall(r"[^、，,]+[、，,]*", sentence):
                if buf and len(buf) + len(piece) > max_len:
                    chunks.append([buf, PAUSE["comma"]])
                    buf = ""
                buf += piece
            if buf:
                chunks.append([buf, PAUSE["sentence"]])
        if chunks:
            chunks[-1][1] = PAUSE["line"]
    merged = []
    for chunk in chunks:
        if merged and len(merged[-1][0]) < min_len and merged[-1][1] == PAUSE["sentence"]:
            merged[-1] = [merged[-1][0] + chunk[0], chunk[1]]
        else:
            merged.append(chunk)
    if merged:
        merged[-1][1] = 0.0
    return [tuple(c) for c in merged]


LINE_END = re.compile(r"(です|ます|でした|ました|ですよ|ですね|ですか|ません|んです|けど|[。！？!?])$")


def join_lines(text, max_len=40):
    """台本向け: 行の境目だけで区切り、文が終わる行（〜です／〜ました／？など）までを1回で読ませる。
    行の途中の改行は読点にする。max_len を超えそうなら行の境目で区切る。

    戻り値は split_text と同じ (チャンク, 後ろに入れる無音の秒数) のリスト。
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    chunks, buf = [], ""
    for line in lines:
        if buf and len(buf) + len(line) > max_len:
            chunks.append([buf, PAUSE["comma"]])
            buf = ""
        if buf and buf[-1] not in SENTENCE_END + "、，,":
            buf += "、"
        buf += line
        if LINE_END.search(line):
            chunks.append([buf, PAUSE["sentence"]])
            buf = ""
    if buf:
        chunks.append([buf, PAUSE["sentence"]])
    if chunks:
        chunks[-1][1] = 0.0
    return [tuple(c) for c in chunks]


def load_readings(path):
    """dict.tsv（表記<TAB>読み）を読む。# から始まる行は無視"""
    readings = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#") and "\t" in line:
                surface, reading = line.split("\t", 1)
                readings.append((surface.strip(), reading.strip()))
    return sorted(readings, key=lambda r: -len(r[0]))


def apply_readings(text, readings):
    for surface, reading in readings:
        text = text.replace(surface, reading)
    return text


def parse_list(value, cast):
    return [cast(v) for v in str(value).split(",") if v.strip()]


def main():
    p = argparse.ArgumentParser(description="Qwen3-TTS (mlx-audio) で自分の声をクローンして読み上げる")
    defaults = load_defaults()
    p.add_argument("--ref", default=defaults.get("ref"), help="refs/<名前>.wav と refs/<名前>.txt を使う（既定は defaults.json の ref）")
    p.add_argument("--ref-audio", help="参照音声のパス（自分の声のみ、5〜10秒、BGM/SEなし）。--ref より優先")
    p.add_argument("--ref-text", help="参照音声の文字起こし（一字一句）")
    p.add_argument("--ref-text-file", help="文字起こしをファイルで渡す場合")
    p.add_argument("--text", help="読み上げる文章")
    p.add_argument("--text-file", help="読み上げる文章をファイルで渡す場合（改行ごとに分割して生成し、1つにつなぐ）")
    p.add_argument("--model", default=default_model())
    p.add_argument("--lang", default="japanese", help="言語（auto / japanese など）")
    p.add_argument("--temperature", default=str(defaults.get("temperature", "0.9")), help="カンマ区切りで複数指定可（例: 0.8,1.0）")
    p.add_argument("--top-p", type=float, default=1.0)
    p.add_argument("--top-k", type=int, default=50)
    p.add_argument("--repetition-penalty", type=float, default=1.05)
    p.add_argument("--seed", default=str(defaults.get("seed", "0")), help="カンマ区切りで複数指定可（例: 0,1,2）。同じ値なら同じ結果になりやすい")
    p.add_argument("--no-split", action="store_true", help="文ごとに分けずに一度に生成する")
    p.add_argument("--join-lines", action="store_true", help="改行を読点として扱い、行をまたぐ文をひと続きで読ませる（台本向け）")
    p.add_argument("--dict", default=str(ROOT / "dict.tsv"), help="読み仮名の辞書（表記<TAB>読み）")
    p.add_argument("--name", help="出力ファイル名（拡張子なし）。省略時は日時＋文章の先頭")
    p.add_argument("--play", action="store_true", help="生成後に afplay で 参照→生成 の順に再生")
    args = p.parse_args()

    if not args.ref_audio:
        if not args.ref:
            p.error("--ref か --ref-audio が必要です")
        args.ref_audio = str(ROOT / "refs" / f"{args.ref}.wav")
        if not (args.ref_text or args.ref_text_file):
            args.ref_text_file = str(ROOT / "refs" / f"{args.ref}.txt")
    ref_text = read_arg_or_file(args.ref_text, args.ref_text_file)
    text = read_arg_or_file(args.text, args.text_file)
    if not ref_text:
        p.error("--ref-text か --ref-text-file が必要です")
    if not text:
        p.error("--text か --text-file が必要です")
    ref_path = Path(args.ref_audio).expanduser().resolve()
    if not ref_path.exists():
        p.error(f"参照音声が見つかりません: {ref_path}")
    spoken = apply_readings(text, load_readings(Path(args.dict)))
    if args.no_split:
        chunks = [(spoken, 0.0)]
    elif args.join_lines:
        chunks = join_lines(spoken)
    else:
        chunks = split_text(spoken)
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
        "spoken_text": spoken,
        "chunks": [c for c, _ in chunks],
    }

    def clear_cache():
        fn = getattr(mx, "clear_cache", None) or getattr(getattr(mx, "metal", None), "clear_cache", None)
        if fn:
            fn()

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

    def speaker_similarity(audio):
        """話者エンコーダの埋め込みで参照音声とのコサイン類似度を出す（1に近いほど似ている）"""
        try:
            a = np.array(model.extract_speaker_embedding(mx.array(audio), sr=sr)).ravel()
            b = ref_embedding
            return round(float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b))), 3)
        except Exception:
            return None

    try:
        ref_embedding = np.array(model.extract_speaker_embedding(mx.array(ref), sr=sr)).ravel()
    except Exception as e:
        ref_embedding = None
        print(f"警告: 似かたスコアを計算できません（{e}）")

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
            t1 = time.time()
            pieces, peak, retried = [], 0.0, 0
            for i, (chunk, pause) in enumerate(chunks):
                # 12.5 トークン/秒。ゆっくり読んでも1文字0.35秒+3秒に収まる長さを上限にして、暴走を止める
                limit_sec = len(chunk) * 0.35 + 3
                for attempt in range(MAX_RETRY + 1):
                    mx.random.seed(seed + 1000 * i + 100000 * attempt)
                    seg = []
                    for r in model.generate(
                        text=chunk,
                        ref_audio=mx.array(ref),
                        ref_text=ref_text,
                        lang_code=args.lang,
                        temperature=temperature,
                        top_p=args.top_p,
                        top_k=args.top_k,
                        repetition_penalty=args.repetition_penalty,
                        max_tokens=int(12.5 * limit_sec),
                        split_pattern="\n",
                    ):
                        seg.append(np.array(r.audio))
                        peak = max(peak, r.peak_memory_usage)
                    seg = np.concatenate(seg)
                    clear_cache()
                    if len(seg) / sr < limit_sec * 0.95:
                        break
                    retried += 1
                    print(f"  文 {i + 1} が長すぎるので作り直します（{len(seg) / sr:.1f}秒）: {chunk[:20]}")
                pieces += [seg, np.zeros(int(sr * pause), dtype=seg.dtype)]
            gen_sec = time.time() - t1

            audio = np.concatenate(pieces)
            audio_write(str(out_wav), audio, sr)
            similarity = speaker_similarity(audio) if ref_embedding is not None else None
            gap = np.zeros(int(sr * 0.7), dtype=audio.dtype)
            audio_write(str(cmp_wav), np.concatenate([ref.astype(audio.dtype), gap, audio]), sr)

            out_sec = len(audio) / sr
            record.update(
                status="ok",
                output=str(out_wav),
                compare=str(cmp_wav),
                segments=len(chunks),
                retried=retried,
                output_seconds=round(out_sec, 2),
                generate_seconds=round(gen_sec, 2),
                real_time_factor=round(gen_sec / out_sec, 2) if out_sec else None,
                peak_memory_gb=round(peak, 2),
                speaker_similarity=similarity,
            )
            append_history(record)
            done.append((similarity if similarity is not None else -1, out_wav))
            sim = f", 似かた {similarity:.3f}" if similarity is not None else ""
            print(f"生成: {out_wav.name}  ({out_sec:.1f}秒の音声を {gen_sec:.1f}秒で生成, ピークメモリ {peak:.2f}GB{sim})")
        except Exception as e:
            record.update(status="error", error=f"{type(e).__name__}: {e}", traceback=traceback.format_exc())
            append_history(record)
            failed += 1
            print(f"エラー（temperature={temperature}, seed={seed}）: {e}（詳細は {HISTORY}）", file=sys.stderr)

    if len(jobs) == 1 and done:
        print(f"聞き比べ: {jobs[0][3]}")
        if args.play:
            subprocess.run(["afplay", str(jobs[0][3])], check=False)
    elif done:
        ranked = sorted(done, key=lambda d: -d[0])
        print("似かたスコア順（1に近いほど参照音声に近い。最終判断は耳で）:")
        for score, out_wav in ranked:
            print(f"  {score:.3f}  {out_wav.name}" if score >= 0 else f"  -      {out_wav.name}")
        best_wav = OUT_DIR / f"{stem}_best.wav"
        if not best_wav.exists():
            shutil.copyfile(ranked[0][1], best_wav)
            print(f"一番スコアが高いもの: {best_wav.name}")
        if args.play:
            for _, out_wav in ranked:
                print(f"再生: {out_wav.name}")
                subprocess.run(["afplay", str(out_wav)], check=False)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
