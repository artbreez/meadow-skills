#!/bin/sh
# Install the deck fonts for the current user (macOS / Linux). Needed to edit or render the PPTX faithfully.
set -e
SRC="$(cd "$(dirname "$0")/../assets/fonts" && pwd)"
case "$(uname)" in
  Darwin) DST="$HOME/Library/Fonts" ;;
  *) DST="$HOME/.local/share/fonts"; mkdir -p "$DST" ;;
esac
cp "$SRC"/*.ttf "$DST"/
command -v fc-cache >/dev/null && fc-cache -f "$DST" >/dev/null || true
echo "Installed $(ls "$SRC"/*.ttf | wc -l | tr -d ' ') fonts into $DST"
