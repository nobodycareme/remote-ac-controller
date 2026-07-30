# Third-Party Notices — IR Simple Learner

The IR Simple Learner tool is licensed under the Apache License, Version 2.0.
Third-party components retain their own licenses as noted below.

## Runtime Dependency

| Component | Version | Purpose | License |
|-----------|---------|---------|---------|
| pyserial  | >=3.5   | Serial port communication (CH9102 USB-UART) | BSD-3-Clause |

## Build-Only Dependency

| Component  | Version | Purpose | License |
|------------|---------|---------|---------|
| PyInstaller | >=6.0  | Packaging Python script into standalone Windows EXE | GPL-2.0-or-later (bootloader); Apache-2.0 (support code) |

The PyInstaller bootloader, licensed under GPL-2.0-or-later, is statically linked
into the distributed EXE. Distributors must ensure compliance with the GPL
requirements when redistributing the built executable. The IR Simple Learner
source code itself remains Apache-2.0.

## Notes

- No third-party component in this repository is re-licensed as Apache-2.0
  original work; each retains its stated license.
- The Python standard library (including `tkinter`) is covered by the
  Python Software Foundation License.
