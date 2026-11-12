#!/usr/bin/env bash
# Read the real `userdata` (or target partition) GPT geometry off the device and patch board.toml.
#
# Works via ADB when running in TWRP or rooted Android.
#
# Usage:
#   scripts/read-userdata-lba.sh            # print geometry only
#   scripts/read-userdata-lba.sh --write    # also rewrite first_lba/last_lba in board.toml
#   scripts/read-userdata-lba.sh --part win # inspect another partition (e.g. win, sda36)
set -euo pipefail

ADB="${ADB:-adb}"
BOARD="$(cd "$(dirname "$0")/.." && pwd)/board.toml"
WRITE=0
TARGET="userdata"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --write)
      WRITE=1
      shift
      ;;
    --part)
      TARGET="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

echo "== Probing device over ADB =="
device=$($ADB get-serialno 2>/dev/null || true)
if [ -z "$device" ] || [ "$device" = "unknown" ]; then
  echo "No device detected over ADB. Please make sure device is connected and authorized." >&2
  exit 1
fi
echo "Connected device: $device"

# Resolve partition block name
part_link=$($ADB shell "readlink -f /dev/block/by-name/$TARGET 2>/dev/null" | tr -d '\r')
if [ -z "$part_link" ]; then
  if $ADB shell "[ -b /dev/block/$TARGET ]"; then
    part_link="/dev/block/$TARGET"
  else
    echo "Partition '$TARGET' not found on device." >&2
    exit 1
  fi
fi
part_name=$(basename "$part_link")
disk_name=$(echo "$part_name" | sed 's/[0-9]*$//')

echo "Target partition: $TARGET -> $part_link ($part_name on $disk_name)"

# Read start, size, and sector size
start_512=$($ADB shell "cat /sys/class/block/$part_name/start 2>/dev/null" | tr -d '\r')
size_512=$($ADB shell "cat /sys/class/block/$part_name/size 2>/dev/null" | tr -d '\r')
lba_bytes=$($ADB shell "cat /sys/class/block/$disk_name/queue/logical_block_size 2>/dev/null || /system/bin/blockdev --getss /dev/block/$disk_name 2>/dev/null || echo 4096" | tr -d '\r')

if [ -z "$start_512" ] || [ -z "$size_512" ] || [ -z "$lba_bytes" ]; then
  echo "Failed to read partition attributes from /sys/class/block/$part_name" >&2
  exit 1
fi

ratio=$((lba_bytes / 512))
first_lba=$((start_512 / ratio))
last_lba=$(( (start_512 + size_512) / ratio - 1 ))
total_lbas=$((last_lba - first_lba + 1))
total_mib=$(( (total_lbas * lba_bytes) / 1024 / 1024 ))
total_gib=$(python3 -c "print(f'{$total_mib / 1024:.2f}')")

printf '\n== Partition Geometry ==\n'
printf 'Partition:    %s (%s)\n' "$TARGET" "$part_link"
printf 'LBA bytes:    %d\n' "$lba_bytes"
printf 'first_lba:    0x%x (%d)\n' "$first_lba" "$first_lba"
printf 'last_lba:     0x%x (%d)\n' "$last_lba" "$last_lba"
printf 'Total LBAs:   %d\n' "$total_lbas"
printf 'Capacity:     %d MiB (%s GiB)\n\n' "$total_mib" "$total_gib"

if [ "$WRITE" = "1" ]; then
  python3 - "$BOARD" "$first_lba" "$last_lba" "$lba_bytes" <<'PY'
import re, sys
path, first, last, lba_bytes = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
text = open(path, encoding="utf-8").read()
text = re.sub(r"^first_lba\s*=\s*0x[0-9a-fA-F]+", f"first_lba = 0x{first:x}", text, flags=re.M)
text = re.sub(r"^last_lba\s*=\s*0x[0-9a-fA-F]+", f"last_lba = 0x{last:x}", text, flags=re.M)
text = re.sub(r"^lba_bytes\s*=\s*[0-9]+", f"lba_bytes = {lba_bytes}", text, flags=re.M)
open(path, "w", encoding="utf-8").write(text)
print(f"Successfully patched {path}:")
PY
  grep -n 'first_lba\|last_lba\|lba_bytes' "$BOARD"
fi
