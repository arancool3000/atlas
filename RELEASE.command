#!/bin/bash
# Cut a new Atlas release: bump version -> build -> zip -> checksum -> latest.json ->
# publish to GitHub Releases + push the website (GitHub Pages).
#
#   ./RELEASE.command            # auto-bump the patch version (1.0.0 -> 1.0.1)
#   ./RELEASE.command 1.2.0      # release a specific version
#
# One-time setup (create repo, set GITHUB_OWNER, enable Pages): see PUBLISH_SETUP.md.
# Edit RELEASE_NOTES.md before running to set this release's notes.
set -euo pipefail
cd "$(dirname "$0")"

ARG="${1:-auto}"

OWNER="$(python3 -c 'import version; print(version.GITHUB_OWNER)')"
if [ "$OWNER" = "YOUR_GITHUB_USERNAME" ]; then
  echo "✗ Set GITHUB_OWNER in version.py first (see PUBLISH_SETUP.md). Aborting."
  exit 1
fi
REPO="$(python3 -c 'import version; print(version.GITHUB_REPO)')"

echo "▶ Bumping version…"
NEWVER="$(python3 _release_helper.py bump "$ARG")"
TAG="v$NEWVER"
echo "  → $TAG"

echo "▶ Syncing website config from version.py…"
python3 _release_helper.py sync-site

echo "▶ Building Atlas.app (first build: 3-6 min)…"
python3 -c "import PyQt6, google.genai" >/dev/null 2>&1 || python3 -m pip install -r requirements.txt
python3 -m pip install --quiet --upgrade pyinstaller
rm -rf build dist
python3 -m PyInstaller --noconfirm Atlas.spec

echo "▶ Signing bundle (ad-hoc — fixes slow first launch)…"
rm -f dist/Atlas 2>/dev/null || true
xattr -cr dist/Atlas.app 2>/dev/null || true
find dist/Atlas.app -exec xattr -c {} \; 2>/dev/null || true
dot_clean -m dist/Atlas.app 2>/dev/null || true
codesign --force --deep --sign - dist/Atlas.app 2>/dev/null || true

echo "▶ Zipping bundle (ditto — preserves symlinks + signature)…"
rm -f dist/Atlas-macOS.zip
/usr/bin/ditto -c -k --keepParent dist/Atlas.app dist/Atlas-macOS.zip

echo "▶ Writing latest.json + checksum…"
PUBDATE="$(date +%F)"
SHA="$(python3 _release_helper.py manifest macos "$NEWVER" dist/Atlas-macOS.zip RELEASE_NOTES.md "$PUBDATE")"
echo "  sha256: ${SHA:0:16}…"

echo "▶ Publishing the GitHub release…"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  if gh release view "$TAG" >/dev/null 2>&1; then
    gh release upload "$TAG" dist/Atlas-macOS.zip dist/latest.json --clobber
  else
    gh release create "$TAG" dist/Atlas-macOS.zip dist/latest.json \
       --title "Atlas $TAG" --notes-file RELEASE_NOTES.md
  fi
  echo "  ✓ release $TAG: Atlas-macOS.zip + latest.json"
else
  cat <<EOF
  gh CLI not available/authed — finish the release in the browser:
    1. https://github.com/$OWNER/$REPO/releases/new   (or edit the existing $TAG release)
    2. Tag: $TAG   Title: Atlas $TAG
    3. Upload assets:  dist/Atlas-macOS.zip   and   dist/latest.json
    4. Paste RELEASE_NOTES.md as the description, then Publish release.
    (Tip: 'brew install gh && gh auth login' automates this next time.)
EOF
fi

echo "▶ Pushing website (GitHub Pages) + version bump…"
if [ -d .git ] && git remote get-url origin >/dev/null 2>&1; then
  git add version.py docs/ RELEASE_NOTES.md
  git commit -m "Release $TAG" >/dev/null 2>&1 || true
  git push origin HEAD || echo "  (push failed — push manually to update the website)"
  echo "  ✓ pushed; GitHub Pages redeploys in ~1 min"
else
  echo "  No git 'origin' remote yet — see PUBLISH_SETUP.md, then commit + push version.py + docs/."
fi

echo ""
echo "✅ Release $TAG complete."
echo "   App:   dist/Atlas.zip"
echo "   Site:  https://$OWNER.github.io/$REPO/"
echo "   Installed copies auto-update to $TAG on next launch."
[ -t 0 ] && { echo "Press Enter to close."; read -r _; } || true
