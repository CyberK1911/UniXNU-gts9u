<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/logo-light.svg">
    <img alt="UniXNU" src="assets/logo-light.svg" width="200">
  </picture>
</p>

<p align="center">
  <a href="https://unixnu.com"><img alt="Documentation" src="https://img.shields.io/badge/docs-unixnu.com-2A5BD7?logo=readthedocs&logoColor=white"></a>
  <a href="https://t.me/unixnu"><img alt="Telegram" src="https://img.shields.io/badge/Telegram-@unixnu-26A5E4?logo=telegram&logoColor=white"></a>
  <a href="https://x.com/unixnu"><img alt="X" src="https://img.shields.io/badge/X-@unixnu-000000?logo=x&logoColor=white"></a>
</p>

# UniXNU-gts9u

Device repository for the **Samsung Galaxy Tab S9 Ultra 5G** (codename `gts9u`, models `SM-X916B`, `SM-X916N`, `SM-X916U`, powered by Qualcomm Snapdragon 8 Gen 2 for Galaxy / SM8550-AC). It holds the board description (`board.toml`), kernel defconfig, preflight checks, ADT generator, device scripts, drivers, and package integration.

Derived from `UniXNU-gts9uwifi` and upstream `UniXNU-sheng`.

---

## Device Specification & Comparison

| Component | Tab S9 Ultra 5G (`gts9u`, SM-X916) | Tab S9 Ultra Wi-Fi (`gts9uwifi`, SM-X910) |
| :--- | :--- | :--- |
| **SoC** | Qualcomm Snapdragon 8 Gen 2 for Galaxy (SM8550-AC, kalama) | Qualcomm Snapdragon 8 Gen 2 for Galaxy (SM8550-AC, kalama) |
| **CPU Topology** | 1x Cortex-X3 @ 3.36GHz, 2x A715 @ 2.8GHz, 2x A710 @ 2.8GHz, 3x A510 @ 2.0GHz | Same |
| **GPU** | Adreno 740 | Adreno 740 |
| **Display** | 14.6" 1848 × 2960 Dynamic AMOLED 2X, 120Hz | 14.6" 1848 × 2960 Dynamic AMOLED 2X, 120Hz |
| **Storage** | UFS 4.0 | UFS 4.0 |
| **Modem / Radio** | Snapdragon X70 5G (inactive in UniXNU) | Omitted / Disabled |
| **GPT Userdata** | Shifted offsets due to radio partitions (modem, fsg, etc.) | Standard Wi-Fi LBA partition layout |
| **UEFI Package** | `Platforms/Samsung/gts9uPkg` | `Platforms/Samsung/gts9uwifiPkg` |
| **Device Compatible** | `samsung,gts9u\0qcom,sm8550\0` | `samsung,gts9uwifi\0qcom,sm8550\0` |

> **Note on Cellular:** UniXNU uses pure Application Processor (AP) bring-up with "Hactivation" (simulated activated state without baseband or SEP hardware). The cellular modem is kept offline.

---

## Build Prerequisites

1. Clone [UniXNU](https://github.com/UniXNU/UniXNU) main repository:
   ```sh
   git clone --recurse-submodules https://github.com/UniXNU/UniXNU.git
   ```

2. Place this device repository next to it:
   ```sh
   git clone https://github.com/your-username/UniXNU-gts9u.git
   ```

3. Ensure Mu-Silicium UEFI environment contains the Samsung `gts9uPkg` definitions or symlink/configure your UEFI build directory.

---

## Partition Geometry Setup (`userdata` LBA)

The 5G variant contains additional radio and modem partitions on UFS LUN 0 (`/dev/block/sda`), shifting the exact sector offsets for the `userdata` partition.

With your Tab S9 Ultra 5G booted into TWRP or rooted Android (with ADB enabled and rooted):

```sh
# Probe GPT table and print userdata first/last LBA
./scripts/read-userdata-lba.sh

# Automatically rewrite first_lba and last_lba in board.toml:
./scripts/read-userdata-lba.sh --write
```

---

## Building UniXNU for Tab S9 Ultra 5G

Run these commands from your root `UniXNU` checkout directory:

```sh
# 1. Select the gts9u defconfig
./unixnu defconfig gts9u_defconfig -D ../UniXNU-gts9u

# 2. Fetch required IPSW components (iPadOS 17.7.11)
./unixnu fetch
./unixnu ipsw fetch

# 3. Build kernel and device packages
./unixnu build kernel
./unixnu build package

# 4. Build UEFI firmware (specifying your Mu-Silicium checkout)
./unixnu build firmware --uefi ../Mu-Silicium

# 5. Assemble payload ramdisk & boot image
./unixnu build payload --unique-chip-id <hex> --trust-cache <bundle> --data-ramdisk <seed>
./unixnu bootimg --uefi ../Mu-Silicium --dtb <gts9u.dtb>
```

---

## Feature Support Matrix

| Feature | State | Notes |
| :--- | :---: | :--- |
| **UEFI Boot** | ⚠️ WIP | Requires SM-X916 vendor DXE extraction from ABL |
| **Video Console / GOP** | ✅ | Framebuffer over Dynamic AMOLED |
| **UFS Storage** | ✅ | Native UFS 4.0 root driver |
| **Touchscreen** | ⚠️ | Needs panel touch firmware extraction |
| **GPU Acceleration** | ✅ | Native Metal compositing on Adreno 740 |
| **Cellular (5G)** | ❌ | Disabled by design (AP-only / Hactivation mode) |
| **Wi-Fi / BT** | ❌ | Not yet adapted for Samsung Broadcom/Qualcomm WLAN |
| **Audio** | ❌ | Stubbed |

---

## License

BSD-2-Clause-Patent. See [LICENSE](LICENSE).
