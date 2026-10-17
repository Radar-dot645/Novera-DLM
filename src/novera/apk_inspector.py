"""Read-only APK metadata inspection without executing or extracting the APK."""
from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path


class APKInspectionError(ValueError):
    pass


_SPLIT_SUFFIXES = {".apks", ".xapk", ".apkm"}
_KNOWN_ABIS = {"armeabi", "armeabi-v7a", "arm64-v8a", "x86", "x86_64", "mips", "mips64", "riscv64"}


@dataclass
class APKInfo:
    path: Path
    size_bytes: int
    package_name: str | None
    version_name: str | None
    version_code: str | None
    min_sdk: str | None
    target_sdk: str | None
    native_abis: tuple[str, ...]
    inspection_method: str
    notes: tuple[str, ...] = ()


def _aapt_metadata(path: Path) -> dict[str, str]:
    tool = shutil.which("aapt")
    if not tool:
        return {}
    try:
        result = subprocess.run([tool, "dump", "badging", str(path)], capture_output=True,
                                text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    output = result.stdout + "\n" + result.stderr
    found: dict[str, str] = {}
    patterns = {
        "package": r"^package:\s+name='([^']+)'",
        "version_name": r"^package:.*?\bversionName='([^']*)'",
        "version_code": r"^package:.*?\bversionCode='([^']*)'",
        "min_sdk": r"^sdkVersion:'([^']*)'",
        "target_sdk": r"^targetSdkVersion:'([^']*)'",
        "native_code": r"^native-code:(.*)$",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, output, re.MULTILINE)
        if match:
            found[key] = match.group(1).strip()
    return found


def inspect_apk(path: Path | str) -> APKInfo:
    """Inspect the APK container and native ABI folders. No files are extracted.

    `aapt` is used for manifest metadata when available. Without it, package name,
    version, and SDK levels may remain unknown; native ABI directories are read
    from the APK ZIP directory only. Filenames are not used as evidence.
    """
    target = Path(path).expanduser()
    if not target.is_file():
        raise FileNotFoundError(f"File tidak ditemukan: {target}")
    if target.suffix.lower() in _SPLIT_SUFFIXES:
        raise APKInspectionError(f"{target.suffix.lower()} adalah container/split-package, bukan APK standalone. Instalasi/inspeksi split package memerlukan tool khusus dan tidak dilakukan Novera.")
    if target.suffix.lower() != ".apk":
        raise APKInspectionError("File harus berekstensi .apk; container .apks/.xapk/.apkm tidak dianggap APK standalone.")
    if not zipfile.is_zipfile(target):
        raise APKInspectionError("Berkas bukan ZIP/APK yang valid.")
    try:
        with zipfile.ZipFile(target, "r") as archive:
            infos = archive.infolist()
            if len(infos) > 100_000:
                raise APKInspectionError("APK memiliki terlalu banyak entri ZIP; inspeksi dihentikan sebagai perlindungan sumber daya.")
            manifest = next((info for info in infos if info.filename == "AndroidManifest.xml"), None)
            if manifest is None:
                raise APKInspectionError("AndroidManifest.xml tidak ditemukan; berkas ini bukan APK standalone yang dapat dikenali.")
            if manifest.file_size > 10 * 1024 * 1024:
                raise APKInspectionError("AndroidManifest.xml terlalu besar untuk inspeksi aman.")
            abis: set[str] = set()
            for info in infos:
                parts = info.filename.split("/")
                if len(parts) >= 3 and parts[0] == "lib" and parts[1] in _KNOWN_ABIS and not info.is_dir():
                    abis.add(parts[1])
                if len(parts) >= 4 and parts[0] == "base" and parts[1] == "lib" and parts[2] in _KNOWN_ABIS and not info.is_dir():
                    abis.add(parts[2])
    except zipfile.BadZipFile as exc:
        raise APKInspectionError("Struktur ZIP/APK rusak.") from exc
    metadata = _aapt_metadata(target)
    method = "aapt + ZIP ABI scan" if metadata else "ZIP ABI scan"
    notes: list[str] = []
    if not metadata:
        notes.append("aapt tidak tersedia atau metadata manifest tidak terbaca; package/version/SDK dapat tetap unknown.")
    if not abis:
        notes.append("Tidak ada native library ABI terdeteksi; ini tidak otomatis membuktikan APK universal.")
    native_text = metadata.get("native_code", "")
    reported_abis = set(re.findall(r"'([^']+)'", native_text)) & _KNOWN_ABIS
    abis.update(reported_abis)
    return APKInfo(
        path=target.resolve(),
        size_bytes=target.stat().st_size,
        package_name=metadata.get("package"),
        version_name=metadata.get("version_name"),
        version_code=metadata.get("version_code"),
        min_sdk=metadata.get("min_sdk"),
        target_sdk=metadata.get("target_sdk"),
        native_abis=tuple(sorted(abis)),
        inspection_method=method,
        notes=tuple(notes),
    )
