"""参照音声づくりの補助: 元の音声から区間を切り出して refs/ に WAV を作り、文字起こしの下書きを付ける。

使い方（run.sh と同じく env.sh を読んだうえで .venv の Python で動かす。ref.sh 経由が簡単）:
  ./ref.sh --src ~/Downloads/S001.m4a --start 0.40 --end 9.39 --name ref_a

出力:
  refs/<name>.wav  24kHz モノラル 16bit（元ファイルは読むだけで変更しない）
  refs/<name>.txt  文字起こしの下書き（Qwen3-ASR）。必ず聞きながら一字一句直すこと
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "refs"
ASR_MODEL = "mlx-community/Qwen3-ASR-0.6B-8bit"


def find_ffmpeg():
    for c in (shutil.which("ffmpeg"), str(Path.home() / "homebrew/bin/ffmpeg"), "/opt/homebrew/bin/ffmpeg"):
        if c and Path(c).exists():
            return c
    sys.exit("ffmpeg が見つかりません（m4a などの読み込みに必要）")


def ensure_asr_model():
    from huggingface_hub import snapshot_download

    try:
        return snapshot_download(ASR_MODEL, local_files_only=True)
    except Exception:
        pass
    print(f"文字起こしモデルが未取得です: https://huggingface.co/{ASR_MODEL}")
    print("サイズは 1GB 前後（Apache-2.0）。保存先はこのフォルダ内の hf-home/")
    if input("ダウンロードしますか？ [y/N]: ").strip().lower() != "y":
        return None
    return snapshot_download(ASR_MODEL)


def main():
    p = argparse.ArgumentParser(description="参照音声の切り出しと文字起こしの下書き")
    p.add_argument("--src", required=True, help="元の音声・動画ファイル（自分の声だけのもの）")
    p.add_argument("--start", type=float, required=True, help="開始秒")
    p.add_argument("--end", type=float, required=True, help="終了秒")
    p.add_argument("--name", required=True, help="refs/ に作るファイル名（拡張子なし）")
    p.add_argument("--no-asr", action="store_true", help="文字起こしをしない")
    args = p.parse_args()

    src = Path(args.src).expanduser().resolve()
    if not src.exists():
        p.error(f"見つかりません: {src}")
    dur = args.end - args.start
    if not 3 <= dur <= 15:
        p.error(f"長さが {dur:.1f} 秒です。5〜10秒にしてください")

    REFS.mkdir(exist_ok=True)
    wav = REFS / f"{args.name}.wav"
    txt = REFS / f"{args.name}.txt"
    if wav.exists():
        p.error(f"既にあります（上書きしません）: {wav}")

    fade = min(0.05, dur / 10)
    subprocess.run(
        [
            find_ffmpeg(), "-v", "error", "-n",
            "-ss", f"{args.start}", "-to", f"{args.end}", "-i", str(src),
            "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le",
            "-af", f"afade=t=in:d={fade},afade=t=out:st={dur - fade}:d={fade}",
            str(wav),
        ],
        check=True,
    )
    print(f"切り出し: {wav}（{dur:.1f}秒）")

    if args.no_asr:
        return
    if ensure_asr_model() is None:
        print("文字起こしは飛ばしました。refs/ に .txt を自分で書いてください")
        return

    from mlx_audio.stt import load

    model = load(ASR_MODEL)
    text = model.generate(str(wav), language="Japanese").text.strip()
    txt.write_text(text + "\n", encoding="utf-8")
    print(f"文字起こし（下書き）: {txt}")
    print(f"  {text}")
    print("→ afplay で聞きながら、言い間違いも含めて一字一句そのままに直してください")


if __name__ == "__main__":
    main()
