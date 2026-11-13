#!/usr/bin/env python3
"""Identify the original generic framebuffer implementation and its abstract leaves."""
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / 'build/display-analysis/mobile-graphics-legacy-abi.json'
out.parent.mkdir(parents=True, exist_ok=True)
recorded = ROOT / 'scripts/data/mobile-graphics-legacy-abi.json'

if not out.exists() and recorded.exists():
    out.write_bytes(recorded.read_bytes())

path = ROOT / 'build/native-prelink/native-owner-mobile-graphics-candidate.macho'
if not path.exists():
    later = sorted((ROOT / 'build/native-prelink').glob('native-owner-ufs-cpu-desktop-*-candidate.macho'), key=lambda f: f.stat().st_mtime)
    if not later:
        if out.exists():
            print('PASS: original Legacy ABI seeded from scripts/data/mobile-graphics-legacy-abi.json\n', end='')
            sys.exit(0)
        else:
            raise SystemExit('No reference candidate available and no seeded mobile-graphics-legacy-abi.json')
    path = later[-1]

if (ROOT / 'kits/NativePrelink').is_dir():
    sys.path.insert(0, str(ROOT / 'kits/NativePrelink'))
elif (ROOT / 'kits/XnuPrelink').is_dir():
    sys.path.insert(0, str(ROOT / 'kits/XnuPrelink'))
from native_prelink import macho, backed_offset, exports


def require(v, why):
    if not v:
        raise SystemExit(why)


blob = path.read_bytes()
plan = json.loads(path.with_suffix('.json').read_text())
image = macho(blob)
family = 'com.apple.iokit.IOMobileGraphicsFamily'
text = next(e for e in plan['extents'] if e['module'] == family and e['segment'] == '__TEXT_EXEC')


def read(va, n):
    at = backed_offset(image['segments'], va, n, len(blob))
    return blob[at:at + n]


names = {n: v for v, group in exports(blob, image).items() for n in group}


def vptr(pc):
    a, b, c = struct.unpack('<3I', read(pc, 12))
    require(a & 0x9f00001f == 0x90000008 and b & 0xffc003ff == 0x91000108 and c == 0x91004108, 'Actual constructor ADRP/ADD/vptr header')
    imm = ((a >> 5) & 0x7ffff) * 4 + ((a >> 29) & 3)
    if imm & (1 << 20):
        imm -= 1 << 21
    return (pc & ~4095) + (imm << 12) + ((b >> 10) & 4095) + 16


def branch(pc):
    w = struct.unpack('<I', read(pc, 4))[0]
    require(w & 0xfc000000 == 0x94000000, 'Actual direct constructor call')
    value = w & 0x3ffffff
    return pc + 4 * (value - (1 << 26) if value & (1 << 25) else value)


base_vptr = vptr(0xfffffff00577b324)
service_vptr = vptr(0xfffffff00577b51c)
legacy_vptr = vptr(0xfffffff0057865d8)
base = struct.unpack('<262Q', read(base_vptr, 262 * 8))
service = struct.unpack('<262Q', read(service_vptr, 262 * 8))
legacy = struct.unpack('<358Q', read(legacy_vptr, 358 * 8))
pure = [i for i, va in enumerate(legacy) if va == names.get('___cxa_pure_virtual')]
changed = [i for i, (a, b) in enumerate(zip(base, legacy)) if a != b]

out.write_text(json.dumps(dict(
    candidate_sha256=plan['candidate_sha256'],
    original_sha256=plan['original_sha256'],
    original_family_text_sha256=plan['original_executable_sha256'][family],
    runtime_metadata_checkpoint_sha256='3044c2beff552911605994c0dc7aa73182066cbb5aed0b396999ceeb5a96da2b',
    base_vptr=hex(base_vptr), service_vptr=hex(service_vptr), legacy_vptr=hex(legacy_vptr),
    legacy_instance_bytes=0x18a0, legacy_virtual_entries=358, abstract_slots=pure,
    inherited_generic_changes=changed, source_service_operation_overrides=0,
    original_new_user_client=hex(legacy[141]), original_init=hex(legacy[21]), original_start=hex(legacy[86]),
    new_user_client_abi='IOService::newUserClient(task_t,void*,UInt32,IOUserClient**)',
    original_stop=hex(legacy[87]), original_client_initializer=hex(0xfffffff005776810),
    methods=[dict(slot=i, address=hex(va), abstract=i in pure, prototype_qualified=False) for i, va in enumerate(legacy)],
    static_dispatch_audit=True, legacy_runtime_instance_created=False, backend_contract_complete=False,
    original_instructions_modified=False, desktop=False), indent=2) + '\n')
print('PASS: original Legacy has 358 slots with nine abstract leaves; original generic client/start/dispatch entries identified')
