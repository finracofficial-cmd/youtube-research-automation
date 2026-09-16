#!/usr/bin/env bash
# Remotion は staticFile() をプロセスの作業ディレクトリ基準で解決する。
# リポジトリ直下から --prefix video で呼ぶと public/ を見失い、
# エラーも出さずに画像が全部消えた黒い動画が出来上がる。
# 事故を防ぐため、必ずこのスクリプト経由で叩く。
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d public ]]; then
  echo "public/ が見つからない。video/ の中で実行すること" >&2
  exit 1
fi
PROPS="${PROPS:-props.json}"
if [[ ! -f "$PROPS" ]]; then
  echo "props が無い: $PROPS  （build_props.py で作る）" >&2
  exit 1
fi
exec npx remotion "$@" --props="$PROPS"
