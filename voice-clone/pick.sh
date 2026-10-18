#!/bin/bash
# 聞き比べ用のまとめ（scripts/pick_best.py）
source "$(cd "$(dirname "$0")" && pwd)/env.sh"
cd "$VC_DIR"
exec .venv/bin/python scripts/pick_best.py "$@"
