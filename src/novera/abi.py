"""Device ABI detection and APK recommendation (honest about verification level)."""
from __future__ import annotations

import platform
import shutil
import subprocess

_MACHINE = {"aarch64": ["arm64-v8a", "armeabi-v7a"], "arm64": ["arm64-v8a", "armeabi-v7a"],
            "armv8l": ["armeabi-v7a"], "armv7l": ["armeabi-v7a"], "x86_64": ["x86_64", "x86"], "i686": ["x86"]}


def device_abis() -> tuple[list[str], str]:
    """Return (abis, source). 'getprop' is authoritative on Android; machine() is a fallback."""
    if shutil.which("getprop"):
        try:
            out = subprocess.run(["getprop", "ro.product.cpu.abilist"], capture_output=True, text=True, timeout=5).stdout.strip()
            if out:
                return out.split(","), "getprop"
        except (OSError, subprocess.SubprocessError):
            pass
    return list(_MACHINE.get(platform.machine().lower(), [])), "platform.machine"


def recommend_apk(assets, abis: list[str]):
    """Pick the best APK for abis. Returns (asset|None, explanation).

    ABI from filenames is a hint, not proof: always confirm with `novera inspect-apk` after download.
    """
    apks = [a for a in assets if (a.kind or "").lower() == "apk" or a.name.lower().endswith(".apk")]
    if not apks:
        return None, "Tidak ada APK."
    for abi in abis:
        for a in apks:
            if a.architecture == abi:
                return a, f"Cocok dengan ABI perangkat {abi} (dari nama file; verifikasi dengan inspect-apk setelah unduh)."
    universal = [a for a in apks if not a.architecture or a.architecture == "universal"]
    if universal:
        return universal[0], "APK tanpa penanda ABI/universal; ABI belum terverifikasi sampai diperiksa dengan inspect-apk."
    return None, f"Tidak ada APK cocok untuk ABI {', '.join(abis) or 'tidak diketahui'}."
