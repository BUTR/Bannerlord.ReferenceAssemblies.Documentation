#!/usr/bin/env bash
# The render fingerprint of a version: what produced the published HTML.
#
# Printed to stdout, without a newline, in the exact form recorded on the host
# with `set-state`, so the two compare byte for byte:
#
#   meta=<pkgs hash from the metadata manifest> docs=<tree> build=<tree> docfx=<version>
#
# meta= identifies the metadata archive the pages were rendered from: it is the
# pkgs field of the release manifest, which changes only when the game ships a
# new build under the same version or the extraction tooling changed. docs= and
# build= are the design and tooling in this checkout; docfx= the renderer. Any
# difference means the published pages are stale and render.yml rebuilds them.
#
# Versions published before the metadata/render split recorded pkgs= instead of
# meta=; they compare unequal once and are rebuilt once. That is intended.
#
# Usage: fingerprint.sh <manifest.json>     from the repository root
set -euo pipefail

manifest="${1:?usage: fingerprint.sh <manifest.json>}"
meta=$(jq -r '.pkgs // empty' "$manifest")
[ -n "$meta" ] || { echo "error: $manifest has no pkgs field" >&2; exit 1; }
docs=$(git rev-parse "HEAD:docs")
build=$(git rev-parse "HEAD:build")
tool=$(docfx --version 2>/dev/null | head -1 | tr -d ' ')
printf 'meta=%s docs=%s build=%s docfx=%s' "$meta" "${docs:0:12}" "${build:0:12}" "$tool"
