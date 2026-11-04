#!/bin/sh
# Build dist/<skill>.zip for every skill, for upload to claude.ai / Claude Design
# (Settings -> Capabilities -> Skills -> Upload, or an org admin can provision it for everyone).
set -e
cd "$(dirname "$0")"
mkdir -p dist; OLDPWD_ROOT=$(pwd)
for d in plugins/*/skills/*/; do
  name=$(basename "$d")
  rm -f "dist/$name.zip"
  (cd "$(dirname "$d")" && zip -qr "$OLDPWD_ROOT/dist/$name.zip" "$name" -x "*/__pycache__/*" "*.DS_Store" "*/evals/*")
  echo "dist/$name.zip  $(du -h "dist/$name.zip" | cut -f1)"
done
