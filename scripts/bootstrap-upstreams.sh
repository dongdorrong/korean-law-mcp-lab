#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAMS_DIR="${ROOT_DIR}/upstreams"

mkdir -p "${UPSTREAMS_DIR}"

if [ ! -d "${UPSTREAMS_DIR}/korean-law-mcp/.git" ]; then
  git clone --depth 1 https://github.com/chrisryugj/korean-law-mcp.git "${UPSTREAMS_DIR}/korean-law-mcp"
else
  git -C "${UPSTREAMS_DIR}/korean-law-mcp" fetch --depth 1 origin main
  git -C "${UPSTREAMS_DIR}/korean-law-mcp" checkout main
  git -C "${UPSTREAMS_DIR}/korean-law-mcp" pull --ff-only
fi

if [ ! -d "${UPSTREAMS_DIR}/legalize-kr/.git" ]; then
  git clone --depth 1 --filter=blob:none --sparse https://github.com/legalize-kr/legalize-kr.git "${UPSTREAMS_DIR}/legalize-kr"
  git -C "${UPSTREAMS_DIR}/legalize-kr" sparse-checkout set --no-cone \
    README.md \
    'kr/민법/*' \
    'kr/개인정보보호법/*' \
    'kr/근로기준법/*'
  git -C "${UPSTREAMS_DIR}/legalize-kr" fetch --unshallow --filter=blob:none || true
else
  git -C "${UPSTREAMS_DIR}/legalize-kr" fetch origin main
  git -C "${UPSTREAMS_DIR}/legalize-kr" checkout main
  git -C "${UPSTREAMS_DIR}/legalize-kr" pull --ff-only
fi

echo "Upstreams are ready under ${UPSTREAMS_DIR}"
