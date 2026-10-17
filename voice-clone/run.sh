#!/bin/bash
# 生成の実行用。モデルはダウンロード済みのものだけを使う（オフライン）
source "$(cd "$(dirname "$0")" && pwd)/env.sh"
cd "$VC_DIR"
HF_HUB_OFFLINE=1 exec .venv/bin/python clone.py "$@"
