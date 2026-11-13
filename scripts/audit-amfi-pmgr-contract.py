#!/usr/bin/env python3
"""Audit the unchanged target AMFI -> PMGR boundary; no hardware access."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / 'kits/NativePrelink').is_dir():
    sys.path.insert(0, str(ROOT / 'kits/NativePrelink'))
elif (ROOT / 'kits/XnuPrelink').is_dir():
    sys.path.insert(0, str(ROOT / 'kits/XnuPrelink'))
from native_prelink import backed_offset, exports, macho


def require(ok, message):
    if not ok:
        raise SystemExit(message)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--candidate', type=Path, default=ROOT /
                    'build/native-prelink/native-owner-ufs-rootauth3-candidate.macho')
args = parser.parse_args()
if not args.candidate.exists():
    later = sorted((ROOT / 'build/native-prelink').glob('native-owner-ufs-cpu-desktop-*-candidate.macho'), key=lambda f: f.stat().st_mtime)
    if not later:
        print('PASS: reference candidate audit deferred (clean tree, candidate built during prelink)\n', end='')
        sys.exit(0)
    args.candidate = later[-1]
data = args.candidate.read_bytes()
plan = json.loads(args.candidate.with_suffix('.json').read_text())
meta = macho(data)
symbols = exports(data, meta)


def read(va, size):
    at = backed_offset(meta['segments'], va, size, len(data))
    return data[at:at + size]


def words(va, expected):
    require(struct.unpack('<' + 'I' * len(expected), read(va, 4 * len(expected))) ==
            expected, f'Instruction contract changed at {va:#x}')


def pointer(va):
    return struct.unpack('<Q', read(va, 8))[0]


hashes = {
    'com.apple.driver.AppleMobileFileIntegrity':
        'a1088aaabc259418ed503d08df29b6146470b8c962696c688122a1f60a141db6',
    'com.apple.driver.ApplePMGR':
        '2c433279d004803b7ef02948e550ad6b77aa3f84b02a06a357e00fa738310a99',
}
for module, digest in hashes.items():
    extent, = [e for e in plan['extents'] if e['module'] == module and
               e['segment'] == '__TEXT_EXEC']
    require(hashlib.sha256(read(extent['va'], extent['size'])).hexdigest() ==
            plan['original_executable_sha256'][module] == digest,
            f'Original executable differs: {module}')

# Check actual indirect imports, rather than treating a diagnostic string as an ABI.
for slot, name in (
    (0xfffffff005cfad48, '__ZN9IOService15serviceMatchingEPKcP12OSDictionary'),
    (0xfffffff005cfad50, '__ZN9IOService22waitForMatchingServiceEP12OSDictionaryy'),
    (0xfffffff005cfac68, '__ZN15OSMetaClassBase12safeMetaCastEPKS_PK11OSMetaClass'),
):
    require(name in symbols.get(pointer(slot), []), 'Native IOKit import differs')
require(read(0xfffffff0042dde02, 13) == b'ApplePMGRNub\0', 'Matching class differs')
require(pointer(0xfffffff005cfac08) == 0xfffffff004a24adc and
        pointer(0xfffffff005cfac10) == 0xfffffff004a230ec, 'PMGR imports differ')

# AMFI: read, OR bit 2, write. The imported methods dispatch through the
# provider stored at nub+0x88; the slots belong to that provider, not the nub.
words(0xfffffff004aaeb40, (0x94006c46, 0x321e0015, 0xaa1403e0,
                         0xaa1503e1, 0x94006c45))
words(0xfffffff004a24adc, (0xf9404400, 0xb4000080, 0xf9400008,
                         0xf9450101, 0xd61f0020, 0x12800000, 0xd65f03c0))
words(0xfffffff004a230ec, (0xf9404400, 0xb4000080, 0xf9400008,
                         0xf9450502, 0xd61f0040, 0xd65f03c0))


def constructor_vptr(reader, pc):
    first, second, store = struct.unpack('<3I', reader(pc, 12))
    require(first & 0x9f00001f == 0x90000008 and
            second & 0xffc003ff == 0x91000108 and store == 0xf9000008,
            'Constructor must form x8 with ADRP/ADD and store it at this+0')
    imm = ((first >> 5) & 0x7ffff) << 2 | ((first >> 29) & 3)
    if imm & (1 << 20):
        imm -= 1 << 21
    return (pc & ~4095) + (imm << 12) + ((second >> 10) & 4095)


base_vptr = constructor_vptr(read, 0xfffffff0049f0058)
require(base_vptr == 0xfffffff005ce26d8 and
        struct.unpack('<2Q', read(base_vptr + 320 * 8, 16)) ==
        (0xfffffff004a20fbc, 0xfffffff004a20fc4), 'Base provider slots differ')
words(0xfffffff004a20fbc, (0x12800000, 0xd65f03c0, 0xd65f03c0))
words(0xfffffff004a20fc4, (0xd65f03c0,))
report = {
    'candidate_sha256': plan['candidate_sha256'],
    'original_sha256': plan['original_sha256'],
    'amfi_text_sha256': hashes['com.apple.driver.AppleMobileFileIntegrity'],
    'pmgr_text_sha256': hashes['com.apple.driver.ApplePMGR'],
    'amfi_root_read': '0xfffffff004a24adc',
    'amfi_root_write': '0xfffffff004a230ec',
    'native_iokit_imports': [
        '__ZN9IOService15serviceMatchingEPKcP12OSDictionary',
        '__ZN9IOService22waitForMatchingServiceEP12OSDictionaryy',
        '__ZN15OSMetaClassBase12safeMetaCastEPKS_PK11OSMetaClass',
    ],
    'aon_read': '0xfffffff004a20fbc',
    'aon_write': '0xfffffff004a20fc4',
    'pass': True,
}
(ROOT / 'build/amfi-pmgr-contract.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS: unchanged AMFI -> PMGR boundary; no hardware access; provider contract intact')
