# ShengHidInput

sheng touch input through IOHIDDevice.

used by the sheng touch path.

Build and interface details: [documentation](https://unixnu.com/drivers/sheng-hid-input). Component sources and dependencies: [catalog](https://unixnu.com/reference/components).

The legacy builder is limited to arm64 iOS 17 / IOHIDFamily 2031.120.4.
For arm64e source-interface compilation, use UniXNU's
`scripts/build-sheng-source-drivers.py`. It selects `IOHIDDevice.h`, uses the
report-type enum and omits the legacy virtual-table edge-event patch.
The generated report distinguishes compilation from family linking and device
qualification; HID startup and edge gestures remain pending.
See the [migration procedure](https://unixnu.com/porting/migration#source-drivers).
