#!/bin/bash
# 参照音声の切り出しと文字起こしの下書き（scripts/make_ref.py）
source "$(cd "$(dirname "$0")" && pwd)/env.sh"
cd "$VC_DIR"
exec .venv/bin/python scripts/make_ref.py "$@"
