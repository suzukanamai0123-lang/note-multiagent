"""長い録音（配信アーカイブや語りの録音）から、参照音声用のきれいなクリップを自動で切り出す。

息継ぎ（無音）の位置で区切り、音割れのある区間と無音が多すぎる区間は避ける。
元ファイルは読むだけで変更しない。

使い方:
  ./clips.sh --src ~/Downloads/録音.m4a --name calm
  → refs/calm_01.wav, refs/calm_02.wav ... （24kHz モノラル、合計 --total 秒まで）
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "refs"
SR = 24000


def find_ffmpeg():
    for c in (shutil.which("ffmpeg"), str(Path.home() / "homebrew/bin/ffmpeg"), "/opt/homebrew/bin/ffmpeg"):
        if c and Path(c).exists():
            return c
    sys.exit("ffmpeg が見つかりません（m4a などの読み込みに必要）")


def main():
    p = argparse.ArgumentParser(description="長い録音から参照音声用のクリップを切り出す")
    p.add_argument("--src", required=True, help="元の録音（自分の声だけのもの）")
    p.add_argument("--name", required=True, help="refs/<name>_01.wav ... の <name>")
    p.add_argument("--min", type=float, default=8.0, help="1クリップの最短秒数")
    p.add_argument("--max", type=float, default=14.0, help="1クリップの最長秒数")
    p.add_argument("--total", type=float, default=100.0, help="切り出す合計秒数の上限")
    args = p.parse_args()

    src = Path(args.src).expanduser().resolve()
    if not src.exists():
        p.error(f"見つかりません: {src}")
    ffmpeg = find_ffmpeg()
    raw = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(src), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True, check=True,
    ).stdout
    x = np.frombuffer(raw, dtype=np.float32)

    hop = SR // 100
    frames = x[: len(x) // hop * hop].reshape(-1, hop)
    db = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    quiet = db < db.max() - 40
    clipped = (np.abs(frames) > 0.99).any(axis=1)

    # 0.3秒以上の無音の中央を区切り候補にする
    cuts, i = [0], 0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            if j - i >= 30:
                cuts.append((i + j) // 2)
            i = j
        else:
            i += 1
    cuts.append(len(quiet))

    # 前から順に、条件を満たす一番長い区間を取っていく（重ならない）
    clips, total, a = [], 0.0, 0
    while a < len(cuts) - 1 and total < args.total:
        best = None
        for b in range(a + 1, len(cuts)):
            s, e = cuts[a], cuts[b]
            dur = (e - s) / 100
            if dur > args.max:
                break
            if dur >= args.min and not clipped[s:e].any() and quiet[s:e].mean() < 0.4:
                best = b
        if best is None:
            a += 1
            continue
        clips.append((cuts[a], cuts[best]))
        total += (cuts[best] - cuts[a]) / 100
        a = best

    if not clips:
        sys.exit("条件に合う区間が見つかりませんでした（--min / --max を変えてみてください）")

    REFS.mkdir(exist_ok=True)
    for n, (s, e) in enumerate(clips, 1):
        out = REFS / f"{args.name}_{n:02d}.wav"
        if out.exists():
            print(f"既にあるので飛ばします: {out.name}")
            continue
        subprocess.run(
            [ffmpeg, "-v", "error", "-n", "-ss", f"{s / 100:.2f}", "-to", f"{e / 100:.2f}", "-i", str(src),
             "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(out)],
            check=True,
        )
        print(f"{out.name}  {s / 100:7.2f}–{e / 100:7.2f}秒（{(e - s) / 100:.1f}秒）")
    print(f"合計 {total:.1f}秒、{len(clips)}クリップ")


if __name__ == "__main__":
    main()
