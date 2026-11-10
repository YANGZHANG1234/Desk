#!/bin/bash
set -euo pipefail

if [[ $# != 1 ]]; then
    echo "Usage: $0 /path/to/verified-python-runtime.tar.gz" >&2
    exit 2
fi
runtime=$1
if [[ $runtime != /* ]]; then runtime="$PWD/$runtime"; fi
runtime_sha=8392b6ea51d94391befb2c31ebe75463f045d0b69dfcf5e1bb3234e1f5fa3405
printf '%s  %s\n' "$runtime_sha" "$runtime" | shasum -a 256 -c -

cd "$(dirname "$0")/../.."
repo=$PWD
if [[ -n $(git status --porcelain) ]]; then
    echo "Commit the source before packaging." >&2
    exit 1
fi
version=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' packaging/macos/Info.plist)
minimum_os=$(/usr/libexec/PlistBuddy -c 'Print :LSMinimumSystemVersion' packaging/macos/Info.plist)
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT

image="$stage/image"
contents="$image/Desk.app/Contents"
resources="$contents/Resources"
mkdir -p "$contents/MacOS" "$resources" "$repo/dist"
git archive HEAD -- README.md LICENSE .system/app .system/config/registry.example.json .system/context/default.md .system/templates |
    tar -xf - -C "$resources"
tar -xzf "$runtime" -C "$resources"
cp packaging/macos/{Desk.icns,desktop.py,Runtime.md} "$resources/"
cp packaging/macos/Info.plist "$contents/"
clang -fobjc-arc -Wall -Wextra -Werror -Wno-unused-parameter -arch arm64 \
    -mmacosx-version-min="$minimum_os" -framework Cocoa \
    packaging/macos/Launcher.m -o "$contents/MacOS/Desk"
/usr/bin/codesign --force --sign - "$image/Desk.app"
/usr/bin/codesign --verify --deep --strict "$image/Desk.app"
ln -s /Applications "$image/Applications"

dmg="Desk-$version-macos-arm64.dmg"
hdiutil create -volname Desk -srcfolder "$image" -fs HFS+ -format UDZO "$stage/$dmg"
hdiutil verify "$stage/$dmg"
mv "$stage/$dmg" "$repo/dist/$dmg"
(cd "$repo/dist" && shasum -a 256 "$dmg" > "$dmg.sha256")
