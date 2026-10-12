#!/usr/bin/env bash
# Imports an audio file into the game as an Ogg Vorbis track.
#
#   tools/import_music.sh "My Song.m4a"            -> assets/audio/music/my_song.ogg
#   tools/import_music.sh track.flac hell          -> assets/audio/music/hell.ogg
#   tools/import_music.sh *.wav                    -> one track each
#
# Reserved names:
#   menu            the between-round hive music
#   hell gold lava paradise purple godly
#                   one per backdrop theme (unset themes share the pool)
# Anything else joins the rotation pool, used in turn as the arena's mood
# changes.  Requires ffmpeg with libvorbis.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out_dir="$root/assets/audio/music"
mkdir -p "$out_dir"

if [ "$#" -eq 0 ]; then
    sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "import_music: ffmpeg is required" >&2
    exit 1
fi

name_override=""
if [ "$#" -ge 2 ] && [[ "$2" != *.* || "$2" == *.ogg ]]; then
    name_override="$2"
    set -- "$1"
fi

for src in "$@"; do
    [ -f "$src" ] || { echo "import_music: no such file: $src" >&2; exit 1; }
    base="$(basename "$src")"
    stem="${base%.*}"
    if [ -n "$name_override" ]; then
        stem="$name_override"
    fi
    stem="$(printf '%s' "$stem" | tr '[:upper:]' '[:lower:]' | tr ' -' '__')"
    dest="$out_dir/$stem.ogg"
    printf 'importing %s -> %s\n' "$base" "${dest#$root/}"
    # 44.1 kHz stereo Vorbis: exactly what the engine's decoder expects.
    ffmpeg -v error -y -i "$src" -vn -ar 44100 -ac 2 -c:a libvorbis -q:a 5 "$dest"
done
echo "done. tracks now in $out_dir:"
ls -1 "$out_dir"
