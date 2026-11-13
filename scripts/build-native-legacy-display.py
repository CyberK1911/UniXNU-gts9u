#!/usr/bin/env python3
"""Bind an owned concrete backend to the unchanged original Legacy lifecycle."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/native-legacy-display'
OUT.mkdir(parents=True, exist_ok=True)
if (ROOT / 'kits/NativePrelink').is_dir():
    sys.path.insert(0, str(ROOT / 'kits/NativePrelink'))
elif (ROOT / 'kits/XnuPrelink').is_dir():
    sys.path.insert(0, str(ROOT / 'kits/XnuPrelink'))
from native_prelink import macho, backed_offset, exports


def run(cmd, **kw):
    return subprocess.check_output([str(x) for x in cmd], timeout=90, **kw)


def require(v, why):
    if not v:
        raise SystemExit(why)


plan_path = ROOT / 'build/display-analysis/mobile-graphics-legacy-abi.json'
recorded = ROOT / 'scripts/data/mobile-graphics-legacy-abi.json'
if not plan_path.exists() and recorded.exists():
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_bytes(recorded.read_bytes())

print(run(['python3', ROOT / 'scripts/audit-mobile-graphics-legacy.py'], text=True), end='')
audit = json.loads(plan_path.read_text())
pure = audit['abstract_slots']
methods = audit['methods']

header = '''// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
#include <IOKit/IOService.h>
#include <libkern/libkern.h>
struct OriginalLegacySwapRequest;
class IOMobileFramebufferLegacy : public IOService {
 OSDeclareAbstractStructors(IOMobileFramebufferLegacy)
 unsigned char originalPrivate[0x18a0-sizeof(IOService)];
public:
 void installBootDimensions(uint32_t width,uint32_t height) {
  *reinterpret_cast<uint32_t *>(reinterpret_cast<unsigned char *>(this)+5808)=width;
  *reinterpret_cast<uint32_t *>(reinterpret_cast<unsigned char *>(this)+5812)=height;
 }
 const OriginalLegacySwapRequest *pendingSwapRequest() const {
  const OriginalLegacySwapRequest *request=nullptr;
  memcpy(&request,reinterpret_cast<const unsigned char *>(this)+5480,sizeof(request));return request;
 }
 bool activateOnlyPendingSwap(const OriginalLegacySwapRequest *request) {
  auto self=reinterpret_cast<unsigned char *>(this);
  auto bytes=reinterpret_cast<const unsigned char *>(request);
  const void *current=nullptr,*head=nullptr,*tail=nullptr,*next=nullptr,*previous=nullptr;
  memcpy(&current,self+5472,8);memcpy(&head,self+5480,8);memcpy(&tail,self+5488,8);
  if(!request || current || head!=request)return false;
  memcpy(&next,bytes+2960,8);memcpy(&previous,bytes+2968,8);
  if(previous!=self+5480)return false;
  if(next) {
   const void *link=self+5480;
   memcpy(const_cast<unsigned char *>(reinterpret_cast<const unsigned char *>(next))+2968,&link,8);
  } else if(tail!=bytes+2960)return false;
  memcpy(self+5472,&request,8);
  if(next) {memcpy(self+5480,&next,8);}
  else {const void *empty=nullptr,*emptyTail=self+5480;memcpy(self+5480,&empty,8);memcpy(self+5488,&emptyTail,8);}
  return true;
 }
 void free() override;
 bool init(OSDictionary *properties=nullptr) override;
 IOReturn setProperties(OSObject *) override;
 void systemWillShutdown(IOOptionBits) override;
 IOService *probe(IOService *,SInt32 *) override;
 bool start(IOService *) override;
 void stop(IOService *) override;
 IOWorkLoop *getWorkLoop() const override;
 IOReturn newUserClient(task_t,void *,UInt32,IOUserClient **) override;
 IOReturn setPowerState(unsigned long,IOService *) override;
'''
for i in range(168, 358):
    if i == 184: header += ' virtual bool isMainDisplay();\n'
    elif i == 188: header += ' virtual IOReturn getDotPitch(uint32_t *);\n'
    elif i == 213: header += ' virtual IOReturn supportedFrameInfo(uint32_t,uint32_t *,char *,uint32_t *)=0;\n'
    elif i == 249: header += ' virtual void getDisplayDimensions(uint32_t *,uint32_t *);\n'
    elif i == 290: header += ' virtual void kickSwapQueue();\n'
    elif i == 296: header += ' virtual bool validateSwap(const OriginalLegacySwapRequest *);\n'
    elif i == 295: header += ' virtual void completeCurrentSwap();\n'
    elif i == 337: header += ' virtual IOReturn collectCompletionReports(uint32_t,void *,uint32_t *,uint32_t)=0;\n'
    elif i == 288: header += ' virtual bool startHardware();\n'
    elif i == 301: header += ' virtual bool getRefreshAttributes(uint64_t *,bool);\n'
    elif i in pure: header += f' virtual __attribute__((noreturn)) void opaque{i}()=0;\n'
    else: header += f' virtual __attribute__((deprecated("Unclassified ABI: never call from source"))) void opaque{i}();\n'
header += '};\nstatic_assert(sizeof(IOMobileFramebufferLegacy)==0x18a0,"Actual original instance extent");\n'
(OUT / 'OriginalLegacyFramebufferABI.h').write_text(header)

print(run(['python3', ROOT / 'scripts/build-arm-driver.py', 'NativeLegacyDisplay'], text=True), end='')
obj = OUT / 'NativeLegacyDisplay.o'
raw = obj.read_bytes()
image = macho(raw)
st = next(p for c, p, _ in image['commands'] if c == 2)
sy, count, strings, _ = struct.unpack_from('<4I', raw, st + 8)
symbols = []
for i in range(count):
    ix, kind, section, _, va = struct.unpack_from('<IBBHQ', raw, sy + i * 16)
    symbols.append((raw[strings + ix:raw.index(b'\0', strings + ix)].decode(), va, kind))
vtable = next(va for name, va, _ in symbols if name == '__ZTV19NativeLegacyDisplay')
relocations = {}
for segment in image['segments']:
    for sec in segment['sections']:
        if sec['va'] <= vtable < sec['va'] + sec['size']:
            ro, rc = struct.unpack_from('<2I', raw, sec['command_offset'] + 56)
            for i in range(rc):
                offset, bits = struct.unpack_from('<2I', raw, ro + i * 8)
                if bits >> 27 & 1 and bits >> 28 == 0 and bits >> 25 & 3 == 3:
                    relocations[sec['va'] + offset] = symbols[bits & 0xffffff][0]
compiled = [relocations.get(vtable + 16 + i * 8) for i in range(358)]
require(all(compiled) and vtable + 16 + 358 * 8 not in relocations, 'Exact owned 358-entry vtable')

candidate = ROOT / 'build/native-prelink/native-owner-mobile-graphics-candidate.macho'
has_cand = candidate.exists()
if not has_cand:
    later = sorted((ROOT / 'build/native-prelink').glob('native-owner-ufs-cpu-desktop-*-candidate.macho'), key=lambda f: f.stat().st_mtime)
    if later:
        candidate = later[-1]
        has_cand = True

bindings = {'__ZN25IOMobileFramebufferLegacyC2EPK11OSMetaClass': 0xfffffff0057865cc,
            '__ZN25IOMobileFramebufferLegacyD2Ev': 0xfffffff005786618,
            '__ZN25IOMobileFramebufferLegacy10gMetaClassE': 0xfffffff006b35940,
            '__ZTV25IOMobileFramebufferLegacy': int(audit['legacy_vptr'], 16) - 16}
owned = []
native = []

if has_cand:
    old = candidate.read_bytes()
    old_image = macho(old)
    names = {n: v for v, group in exports(old, old_image).items() for n in group}
    for i, name in enumerate(compiled):
        expected = int(methods[i]['address'], 16)
        if name.startswith(('__ZN19NativeLegacyDisplay', '__ZNK19NativeLegacyDisplay')):
            owned.append(i)
            require(i in (0, 1, 7, 14, 84, 86, 87, 141, 155, 184, 188, 288, 290, 296, 301) or i in pure, 'Only qualified own methods and guarded leaves override')
        elif '25IOMobileFramebufferLegacy' in name:
            require(i not in pure, 'No unresolved original abstract backend target')
            bindings[name] = expected
        else:
            require(i < 168 and names.get(name) == expected, 'Actual inherited native base symbol ' + str(i))
            native.append(i)
else:
    for i, name in enumerate(compiled):
        expected = int(methods[i]['address'], 16)
        if name.startswith(('__ZN19NativeLegacyDisplay', '__ZNK19NativeLegacyDisplay')):
            owned.append(i)
        elif '25IOMobileFramebufferLegacy' in name:
            bindings[name] = expected

require(owned == sorted([0, 1, 7, 14, 84, 86, 87, 141, 155, 184, 188, 288, 290, 296, 301] + pure), 'Exact owned method set')
undefined = {n for n, _, k in symbols if k == 1 and 'IOMobileFramebufferLegacy' in n}
require(undefined == set(bindings), 'All and only actual original-class imports qualified')

for name, address, field, wide in [
    ('descriptor', 0xfffffff004b9ead0, 48, True), ('width', 0xfffffff004b9ebbc, 88, True),
    ('height', 0xfffffff004b9ebc4, 96, True), ('stride', 0xfffffff004b9ebd4, 104, True),
    ('allocation', 0xfffffff004b9ebfc, 144, True), ('format', 0xfffffff004b9ebac, 128, False),
    ('planes', 0xfffffff004b9ebf4, 152, False)]:
    bindings['_native_legacy_surface_' + name] = address

bindings['_native_legacy_vsync_notify'] = 0xfffffff005796720
bindings['_native_legacy_set_refresh_properties'] = 0xfffffff00579ebb8

asm = OUT / 'original-bindings.S'
asm.write_text(''.join(f'.globl {name}\n.set {name}, {va:#x}\n' for name, va in sorted(bindings.items())))
sdk = run(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
run(['xcrun', 'clang', '-target', 'arm64-apple-ios17.0', '-isysroot', sdk, '-c', asm, '-o', OUT / 'original-bindings.o'])

objcopy = shutil.which('llvm-objcopy')
if not objcopy:
    try:
        llvm_prefix = run(['brew', '--prefix', 'llvm'], text=True).strip()
        objcopy = str(Path(llvm_prefix) / 'bin/llvm-objcopy')
    except Exception:
        objcopy = 'llvm-objcopy'

late = OUT / 'NativeLegacyDisplay.late.o'
run([objcopy, '--remove-section=__DATA,__mod_init_func', '--globalize-symbol=__GLOBAL__sub_I_NativeLegacyDisplay.cpp', obj, late])


def code(data, info):
    sec = next(s for g in info['segments'] for s in g['sections'] if s['name'] == '__text')
    return data[sec['fileoff']:sec['fileoff'] + sec['size']]


require(code(raw, image) == code(late.read_bytes(), macho(late.read_bytes())), 'Only owned initializer section registration changes')

r = json.loads((ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json').read_text().strip().rstrip(','))
cmd = []
args = r['arguments']
i = 0
source = ROOT / 'kits/sheng/LegacyDisplayProbe.cpp'
while i < len(args):
    value = args[i]
    if value == r['file']: cmd.append(str(source))
    elif value == '-o': cmd += ['-o', str(OUT / 'LegacyDisplayProbe.o')]; i += 1
    elif value == '-Xclang' and args[i + 1].startswith('-W'): i += 1
    elif not value.startswith('-W'): cmd.append(value)
    i += 1
cmd += ['-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-unnecessary-virtual-specifier', '-Wno-c99-designator', '-Wno-reorder-init-list',
        '-Wno-deprecated-enum-enum-conversion', '-I', str(ROOT / '.cache/xnu-work/osfmk')]
run(cmd, cwd=r['directory'])

hid_source = ROOT / 'kits/sheng/HidInputProbe.cpp'
hid_obj = OUT / 'HidInputProbe.o'
hid_cmd = [str(hid_source) if str(arg) == str(source) else str(hid_obj) if str(arg) == str(OUT / 'LegacyDisplayProbe.o') else arg for arg in cmd]
run(hid_cmd, cwd=r['directory'])

keystore_source = ROOT / 'kits/sheng/KeyStoreProbe.cpp'
keystore_obj = OUT / 'KeyStoreProbe.o'
keystore_cmd = [str(keystore_source) if str(arg) == str(source) else str(keystore_obj) if str(arg) == str(OUT / 'LegacyDisplayProbe.o') else arg for arg in cmd]
run(keystore_cmd, cwd=r['directory'])

process_source = ROOT / 'kits/sheng/BootProcessProbe.c'
process_obj = OUT / 'BootProcessProbe.o'
pr = json.loads((ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/osfmk/DEVELOPMENT/startup.o.json').read_text().strip().rstrip(','))
process_cmd = []
pa = pr['arguments']
j = 0
while j < len(pa):
    value = pa[j]
    if value == pr['file']: process_cmd.append(str(process_source))
    elif value in ('-o', '-MF', '-MT', '-MJ'):
        if value == '-o': process_cmd += ['-o', str(process_obj)]
        j += 1
    elif value == '-Xclang' and pa[j + 1].startswith('-W'): j += 1
    elif not value.startswith('-W'): process_cmd.append(value)
    j += 1
process_cmd += ['-Wall', '-Wextra', '-Werror', '-mgeneral-regs-only', '-I', str(ROOT / '.cache/xnu-work/osfmk')]
run(process_cmd, cwd=pr['directory'])

trace_source = ROOT / 'kits/sheng/BootUiTraceProbe.c'
trace_obj = OUT / 'BootUiTraceProbe.o'
trace_cmd = [str(trace_source) if arg == str(process_source) else str(trace_obj) if arg == str(process_obj) else arg for arg in process_cmd]
run(trace_cmd, cwd=pr['directory'])

log_source = ROOT / 'kits/sheng/BootLog.c'
log_obj = OUT / 'BootLog.o'
run([str(log_source) if arg == str(process_source) else str(log_obj) if arg == str(process_obj) else arg for arg in process_cmd] + ['-I', str(ROOT / 'kits/sheng')], cwd=pr['directory'])

reset_source = ROOT / 'kits/sheng/BootReset.c'
reset_obj = OUT / 'BootReset.o'
run([str(reset_source) if arg == str(process_source) else str(reset_obj) if arg == str(process_obj) else arg for arg in process_cmd] + ['-I', str(ROOT / 'kits/sheng')], cwd=pr['directory'])

geni_spi_dir = ROOT / 'drivers/NativeGeniSpi'
if not geni_spi_dir.is_dir() and (ROOT / 'drivers/QcomGeniSpi').is_dir():
    geni_spi_dir = ROOT / 'drivers/QcomGeniSpi'

adreno_dir = ROOT / 'drivers/NativeAdreno'
if not adreno_dir.is_dir() and (ROOT / 'drivers/Adreno740').is_dir():
    adreno_dir = ROOT / 'drivers/Adreno740'

cmd += ['-I', str(ROOT / 'kits/sheng'), '-I', str(geni_spi_dir), '-I', str(ROOT / 'drivers/NativeNovatekTouch')]
touch_dir = OUT / 'touch'
touch_dir.mkdir(exist_ok=True)
touch_cpp = ROOT / 'kits/sheng/TouchProbe.cpp'
touch_cpp_obj = touch_dir / 'TouchProbe.o'
cpufreq_cpp = ROOT / 'kits/sheng/CpuFreqProbe.cpp'
cpufreq_obj = touch_dir / 'CpuFreqProbe.o'
gpupower_cpp = ROOT / 'kits/sheng/GpuPowerProbe.cpp'
gpupower_obj = touch_dir / 'GpuPowerProbe.o'
wifi_cpp = ROOT / 'kits/sheng/WifiProbe.cpp'
wifi_obj = touch_dir / 'WifiProbe.o'
buttons_cpp = ROOT / 'kits/sheng/ButtonProbe.cpp'
buttons_obj = touch_dir / 'ButtonProbe.o'
backlight_cpp = ROOT / 'kits/sheng/BacklightProbe.cpp'
backlight_obj = touch_dir / 'BacklightProbe.o'
backlight_class_cpp = ROOT / 'kits/sheng/AppleARMBacklight.cpp'
backlight_class_obj = touch_dir / 'AppleARMBacklight.o'
backlight_class_late = touch_dir / 'AppleARMBacklight.late.o'

run([str(touch_cpp) if str(arg) == str(source) else str(touch_cpp_obj) if str(arg) == str(OUT / 'LegacyDisplayProbe.o') else arg for arg in cmd], cwd=r['directory'])
run([str(gpupower_cpp) if str(arg) == str(source) else str(gpupower_obj) if str(arg) == str(OUT / 'LegacyDisplayProbe.o') else arg for arg in cmd] + ['-I', str(adreno_dir), '-I', str(ROOT / 'kits/ArmSmmu4K'), '-I', str(ROOT / 'kits/AdrenoFirmware'), '-I', str(ROOT / 'kits/AdrenoPM4')], cwd=r['directory'])
run([str(cpufreq_cpp) if str(arg) == str(source) else str(cpufreq_obj) if str(arg) == str(OUT / 'LegacyDisplayProbe.o') else arg for arg in cmd], cwd=r['directory'])
run([str(wifi_cpp) if str(arg) == str(source) else str(wifi_obj) if str(arg) == str(OUT / 'LegacyDisplayProbe.o') else arg for arg in cmd], cwd=r['directory'])
run([str(buttons_cpp) if str(arg) == str(source) else str(buttons_obj) if str(arg) == str(OUT / 'LegacyDisplayProbe.o') else arg for arg in cmd], cwd=r['directory'])
run([str(backlight_cpp) if str(arg) == str(source) else str(backlight_obj) if str(arg) == str(OUT / 'LegacyDisplayProbe.o') else arg for arg in cmd], cwd=r['directory'])
run([str(backlight_class_cpp) if str(arg) == str(source) else str(backlight_class_obj) if str(arg) == str(OUT / 'LegacyDisplayProbe.o') else arg for arg in cmd], cwd=r['directory'])

print(run(['python3', ROOT / 'scripts/gen-touch-firmware.py'], text=True), end='')
touch_c = [ROOT / 'drivers/NativeNovatekTouch/NvtProtocol.c',
           ROOT / 'drivers/NativeNovatekTouch/NvtTouchCore.c',
           ROOT / 'build/native-touch/NvtFirmware.c']
geni_c = geni_spi_dir / 'GeniSpi.c'
if geni_c.is_file():
    touch_c.insert(0, geni_c)

touch_objs = []
for src in touch_c:
    tobj = touch_dir / (src.stem + '.o')
    touch_objs.append(tobj)
    run([str(src) if arg == str(process_source) else str(tobj) if arg == str(process_obj) else arg for arg in process_cmd], cwd=pr['directory'])

run([objcopy, '--remove-section=__DATA,__mod_init_func', '--globalize-symbol=__GLOBAL__sub_I_AppleARMBacklight.cpp',
     backlight_class_obj, backlight_class_late])

archive = OUT / 'libNativeLegacyDisplay.late.a'
archive.unlink(missing_ok=True)
print(run(['python3', ROOT / 'scripts/build-native-hid-input.py'], text=True), end='')
hid_dir = ROOT / 'build/native-hid-input'
print(run(['python3', ROOT / 'scripts/build-arm-driver.py', 'NativeKeyStoreEvents'], text=True), end='')
keyevents = ROOT / 'build/native-keystore-events'
keyevents_late = keyevents / 'NativeKeyStoreEvents.late.o'
run([objcopy, '--remove-section=__DATA,__mod_init_func',
     '--globalize-symbol=__GLOBAL__sub_I_NativeKeyStoreEvents.cpp',
     keyevents / 'NativeKeyStoreEvents.o', keyevents_late])
require(code((keyevents / 'NativeKeyStoreEvents.o').read_bytes(), macho((keyevents / 'NativeKeyStoreEvents.o').read_bytes())) ==
        code(keyevents_late.read_bytes(), macho(keyevents_late.read_bytes())), 'Owned event-service instructions unchanged by late init staging')

run(['xcrun', 'ar', 'rcs', archive, late, OUT / 'original-bindings.o', OUT / 'LegacyDisplayProbe.o', hid_obj, keystore_obj, process_obj, trace_obj, log_obj, reset_obj,
     hid_dir / 'NativeHidInput.late.o', hid_dir / 'hid-original-bindings.o', keyevents_late, touch_cpp_obj, cpufreq_obj, gpupower_obj, wifi_obj, buttons_obj, backlight_obj, backlight_class_late, *touch_objs])
report = {
    'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'late_display_sha256': hashlib.sha256(late.read_bytes()).hexdigest(),
    'bindings': {name: hex(va) for name, va in bindings.items()},
    'owned_slots': owned,
}
(OUT / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS: NativeLegacyDisplay bound against audited original framebuffer lifecycle')
