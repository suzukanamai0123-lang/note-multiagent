#!/bin/bash
# Phase 2: 隔離環境の構築（このフォルダの中だけに作る）
# 使い方: bash scripts/setup.sh
#   モデルを手動で選ぶ場合: MODEL=mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit bash scripts/setup.sh
set -euo pipefail

source "$(cd "$(dirname "$0")/.." && pwd)/env.sh"
cd "$VC_DIR"

MLX_AUDIO_VERSION="0.5.9"
MODEL_SMALL="mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit"
MODEL_LARGE="mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit"

confirm() {
  read -r -p "$1 [y/N]: " ans
  [[ "$ans" == "y" || "$ans" == "Y" ]]
}

mkdir -p logs
LOG="logs/setup-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "=== 1. 前提チェック ==="
if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "Apple Silicon の macOS ではないので中止します（$(uname -s) $(uname -m)）"
  exit 1
fi
os_major=$(sw_vers -productVersion | cut -d. -f1)
echo "macOS $(sw_vers -productVersion)"
if [ "$os_major" -lt 14 ]; then
  echo "mlx の配布パッケージは macOS 14 (Sonoma) 以上が必要です。macOS を更新してから再実行してください。"
  exit 1
fi
mem_gb=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
free_gb=$(df -g "$VC_DIR" | tail -n 1 | awk '{print $4}')
echo "メモリ ${mem_gb}GB / 空き ${free_gb}GB"
if [ "$free_gb" -lt 8 ]; then
  echo "空き容量が 8GB 未満です。不要なファイルを整理してから再実行してください。"
  exit 1
fi

if [ -z "${MODEL:-}" ]; then
  if [ "$mem_gb" -ge 16 ]; then MODEL="$MODEL_LARGE"; else MODEL="$MODEL_SMALL"; fi
fi
echo "使用モデル: $MODEL"

echo
echo "=== 2. uv ==="
UV="$(command -v uv || true)"
[ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ] && UV="$HOME/.local/bin/uv"
if [ -z "$UV" ]; then
  echo "uv が見つかりません。次のどちらかで入れられます:"
  echo "  A) 公式インストーラ: curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo "     → ~/.local/bin/uv に1ファイル置くだけ。シェル設定に PATH が追記されることがあります"
  echo "  B) Homebrew: brew install uv"
  echo "このスクリプトは自動では入れません。入れてから再実行してください。"
  exit 1
fi
echo "$UV ($("$UV" --version))"

echo
echo "=== 3. Python 3.12 と仮想環境（$VC_DIR/.venv）==="
"$UV" python install 3.12
if [ ! -x .venv/bin/python ]; then
  "$UV" venv --python 3.12 .venv
fi
.venv/bin/python --version

echo
echo "=== 4. mlx-audio ${MLX_AUDIO_VERSION} ==="
"$UV" pip install --python .venv/bin/python "mlx-audio==${MLX_AUDIO_VERSION}"
"$UV" pip freeze --python .venv/bin/python > logs/requirements-lock.txt
.venv/bin/python -c "import mlx.core as mx, importlib.metadata as m; print('mlx', m.version('mlx'), '/ mlx-audio', m.version('mlx-audio'), '/ device', mx.default_device())"

echo
echo "=== 5. モデルのダウンロード ==="
echo "取得元: https://huggingface.co/$MODEL"
echo "サイズ: 0.6B は約 2.0GB / 1.7B は約 3.1GB（Apache-2.0）"
echo "保存先: $HF_HOME"
if confirm "ダウンロードしますか？"; then
  .venv/bin/python -c "from huggingface_hub import snapshot_download; print(snapshot_download('$MODEL'))"
  echo "$MODEL" > model.txt
else
  echo "ダウンロードを中止しました。モデル以外の準備は完了しています。"
  exit 0
fi

echo
echo "=== 6. 読み込みテスト ==="
HF_HUB_OFFLINE=1 .venv/bin/python -c "
from mlx_audio.tts.utils import load_model
m = load_model('$MODEL')
print('OK', type(m).__name__, 'sample_rate', m.sample_rate)
print('languages', m.get_supported_languages())
"
echo
echo "完了。ログ: $LOG"
