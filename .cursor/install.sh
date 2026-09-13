#!/usr/bin/env bash
#
# Idempotent setup for this Blender project.
# Installs Blender 5.2.x (matching the version the .blend files were authored in)
# plus the small set of archive utilities used to inspect the bundled assets.
set -euo pipefail

BLENDER_SERIES="5.2"
BLENDER_VERSION="5.2.1"
BLENDER_TARBALL="blender-${BLENDER_VERSION}-linux-x64.tar.xz"
BLENDER_URL="https://download.blender.org/release/Blender${BLENDER_SERIES}/${BLENDER_TARBALL}"
BLENDER_PREFIX="/opt/blender"

echo "==> Installing system utilities"
sudo apt-get update -y
# unrar/zstd are only needed to inspect the archived + compressed assets in this repo.
# The remaining libraries are runtime dependencies Blender may need on a minimal image.
sudo apt-get install -y --no-install-recommends \
  unrar zstd curl xz-utils \
  libx11-6 libxi6 libxxf86vm1 libxfixes3 libxrender1 \
  libgl1 libglx-mesa0 libegl1 libgomp1

if command -v blender >/dev/null 2>&1 && blender --version 2>/dev/null | grep -q "${BLENDER_VERSION}"; then
  echo "==> Blender ${BLENDER_VERSION} already installed: $(command -v blender)"
  exit 0
fi

echo "==> Downloading Blender ${BLENDER_VERSION}"
tmp_archive="$(mktemp --suffix=.tar.xz)"
curl -fL -o "${tmp_archive}" "${BLENDER_URL}"

echo "==> Installing Blender into ${BLENDER_PREFIX}"
sudo rm -rf "${BLENDER_PREFIX}"
sudo mkdir -p "${BLENDER_PREFIX}"
sudo tar -xf "${tmp_archive}" -C "${BLENDER_PREFIX}" --strip-components=1
rm -f "${tmp_archive}"
sudo ln -sf "${BLENDER_PREFIX}/blender" /usr/local/bin/blender

echo "==> Blender installed:"
blender --version | head -1
