# source env.sh で読み込む。すべての保存先をこのフォルダ内に閉じ込める
VC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export VC_DIR
export HF_HOME="$VC_DIR/hf-home"
export HF_HUB_DISABLE_TELEMETRY=1
export UV_PYTHON_INSTALL_DIR="$VC_DIR/.uv-python"
export UV_CACHE_DIR="$VC_DIR/.uv-cache"
export UV_PYTHON_PREFERENCE=only-managed
