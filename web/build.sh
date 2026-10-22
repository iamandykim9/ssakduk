#!/usr/bin/env bash
# 웹사이트를 _site 폴더로 만든다 (라이브러리를 같은 주소에서 제공하도록 복사)
set -euo pipefail
cd "$(dirname "$0")"
npm install --no-audit --no-fund --silent
OUT="${1:-../_site}"
rm -rf "$OUT" && mkdir -p "$OUT/vendor/ffmpeg" "$OUT/vendor/core"
cp index.html app.js style.css icon.svg sitemap.xml llms.txt google*.html "$OUT/"
cp node_modules/@ffmpeg/ffmpeg/dist/esm/*.js "$OUT/vendor/ffmpeg/"
cp node_modules/@ffmpeg/core/dist/esm/ffmpeg-core.js node_modules/@ffmpeg/core/dist/esm/ffmpeg-core.wasm "$OUT/vendor/core/"
cp node_modules/fflate/esm/browser.js "$OUT/vendor/fflate.js"
touch "$OUT/.nojekyll"
echo "site built: $OUT"
