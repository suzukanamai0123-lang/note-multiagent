#!/bin/bash
# Irodori-TTS で生成（irodori.py）。初回だけモデルのダウンロード確認があるのでオンラインで動かす
source "$(cd "$(dirname "$0")" && pwd)/env.sh"
cd "$VC_DIR"
exec .venv/bin/python irodori.py "$@"
