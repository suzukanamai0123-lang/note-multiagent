#!/bin/bash
# Phase 1: 環境確認（読むだけ。何もインストール・変更しない）
# 使い方: bash check_env.sh

echo "=== macOS ==="
sw_vers 2>/dev/null || echo "sw_vers なし"
echo
echo "=== チップ / アーキテクチャ ==="
sysctl -n machdep.cpu.brand_string 2>/dev/null
uname -m
echo
echo "=== メモリ ==="
mem_bytes=$(sysctl -n hw.memsize 2>/dev/null)
[ -n "$mem_bytes" ] && echo "$((mem_bytes / 1024 / 1024 / 1024)) GB"
echo
echo "=== 空きディスク（ホームのあるボリューム）==="
df -h "$HOME" | tail -n 1
echo
echo "=== Python ==="
for p in python3 python3.12 python3.11; do
  if command -v "$p" >/dev/null 2>&1; then
    echo "$p: $(command -v "$p") ($("$p" --version 2>&1))"
  fi
done
echo
echo "=== uv ==="
if command -v uv >/dev/null 2>&1; then
  echo "$(command -v uv) ($(uv --version))"
elif [ -x "$HOME/.local/bin/uv" ]; then
  echo "$HOME/.local/bin/uv ($("$HOME/.local/bin/uv" --version))  ※PATH未登録"
else
  echo "未インストール"
fi
echo
echo "=== Homebrew ==="
if command -v brew >/dev/null 2>&1; then
  echo "$(command -v brew) ($(brew --version 2>/dev/null | head -n 1))"
elif [ -x "$HOME/homebrew/bin/brew" ]; then
  echo "$HOME/homebrew/bin/brew ($("$HOME/homebrew/bin/brew" --version 2>/dev/null | head -n 1))  ※PATH未登録"
else
  echo "見つからない"
fi
echo
echo "=== ffmpeg ==="
if command -v ffmpeg >/dev/null 2>&1; then
  echo "$(command -v ffmpeg) ($(ffmpeg -version 2>/dev/null | head -n 1))"
elif [ -x "$HOME/homebrew/bin/ffmpeg" ]; then
  echo "$HOME/homebrew/bin/ffmpeg  ※PATH未登録"
else
  echo "なし（WAV出力だけなら不要）"
fi
echo
echo "=== Xcode Command Line Tools ==="
xcode-select -p 2>/dev/null || echo "未インストール"
echo
echo "=== 作業予定ディレクトリ ==="
if [ -e "$HOME/suzukana-voice-clone" ]; then
  echo "~/suzukana-voice-clone は既に存在する（中身を確認してから進める）"
  ls -la "$HOME/suzukana-voice-clone" | head -n 20
else
  echo "~/suzukana-voice-clone はまだ無い"
fi
echo
echo "=== 既存 HF キャッシュ（参考）==="
du -sh "$HOME/.cache/huggingface" 2>/dev/null || echo "なし"
