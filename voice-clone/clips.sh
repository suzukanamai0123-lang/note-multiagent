#!/bin/bash
# 長い録音から参照クリップを自動で切り出す（scripts/make_clips.py）
source "$(cd "$(dirname "$0")" && pwd)/env.sh"
cd "$VC_DIR"
exec .venv/bin/python scripts/make_clips.py "$@"
