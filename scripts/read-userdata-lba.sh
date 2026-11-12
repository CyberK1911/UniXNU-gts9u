#!/usr/bin/env bash
# Read the real `userdata` GPT geometry off the SM-X916 (Galaxy Tab S9 Ultra 5G) and patch board.toml.
#
# The userdata image must sit exactly on the partition: a wrong first_lba writes over the
# neighbouring partition.  Run this with the tablet in TWRP (adb root available) or on a rooted
# LineageOS, then commit the board.toml change so the numbers are no longer sheng's.
#
#   scripts/read-userdata-lba.sh            # print only
#   scripts/read-userdata-lba.sh --write    # also rewrite first_lba/last_lba in board.toml
set -euo pipefail

ADB="${ADB:-adb}"
BOARD="$(cd "$(dirname "$0")/.." && pwd)/board.toml"
WRITE=0
[ "${1:-}" = "--write" ] && WRITE=1

echo "== block devices =="
$ADB shell "ls /dev/block/sd* /dev/block/mmcblk* 2>/dev/null" | tr -d '\r'

for disk in /dev/block/sda /dev/block/mmcblk0; do
  if $ADB shell "[ -b $disk ]" 2>/dev/null; then
    echo "== GPT of $disk =="
    table=$($ADB shell "sgdisk -p $disk 2>/dev/null || parted -s $disk print 2>/dev/null" | tr -d '\r')
    echo "$table" | sed -n '1,40p'
    line=$(echo "$table" | grep -i ' userdata$' || true)
    if [ -z "$line" ]; then
      echo "no userdata entry on $disk"
      continue
    fi
    # sgdisk: "  12  1234567  2345678 ... userdata"
    first=$(echo "$line" | awk '{print $2}')
    last=$(echo "$line" | awk '{print $3}')
    # parted: "12  1234s  5678s  ... userdata"
    if ! [[ "$first" =~ ^[0-9]+$ ]]; then
      first=$(echo "$line" | awk '{print $2}' | tr -d 's')
      last=$(echo "$line" | awk '{print $3}' | tr -d 's')
    fi
    if ! [[ "$first" =~ ^[0-9]+$ ]]; then
      echo "could not parse sector numbers from: $line" >&2
      exit 1
    fi
    printf 'userdata: first_lba = 0x%x (%d), last_lba = 0x%x (%d), sectors = %d\n' \
      "$first" "$first" "$last" "$last" "$((last - first + 1))"
    echo "expected image size: $(( (last - first + 1) * 4096 / 1024 / 1024 )) MiB at 4096-byte LBAs"

    if [ "$WRITE" = "1" ]; then
      python3 - "$BOARD" "$first" "$last" <<'PY'
import re, sys
path, first, last = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
text = open(path, encoding="utf-8").read()
text = re.sub(r"^first_lba = 0x[0-9a-fA-F]+", f"first_lba = 0x{first:x}", text, flags=re.M)
text = re.sub(r"^last_lba = 0x[0-9a-fA-F]+", f"last_lba = 0x{last:x}", text, flags=re.M)
open(path, "w", encoding="utf-8").write(text)
print(f"patched {path}")
PY
      grep -n 'first_lba\|last_lba' "$BOARD"
    fi
    exit 0
  fi
done

echo "no disk device found over adb" >&2
exit 1
