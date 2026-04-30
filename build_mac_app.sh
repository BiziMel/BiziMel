#!/usr/bin/env bash
set -euo pipefail

version="1.0"
export PYINSTALLER_CONFIG_DIR="${PWD}/release/pyinstaller-cache"
mkdir -p "${PYINSTALLER_CONFIG_DIR}"

python3 -m PyInstaller \
  --noconfirm \
  --distpath release/mac \
  --workpath release/build-mac \
  PipeFlow_mac.spec

if hdiutil create \
  -volname "PipeFlow ${version}" \
  -srcfolder release/mac/PipeFlow.app \
  -ov \
  -format UDZO \
  "release/PipeFlow-mac-v${version}.dmg"; then
  echo "Created release/PipeFlow-mac-v${version}.dmg"
else
  ditto -c -k --keepParent release/mac/PipeFlow.app "release/PipeFlow-mac-v${version}.zip"
  echo "DMG creation failed, created release/PipeFlow-mac-v${version}.zip instead"
fi
