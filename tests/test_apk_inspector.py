from __future__ import annotations
import subprocess
import zipfile
from pathlib import Path
import pytest
from novera.apk_inspector import APKInspectionError, inspect_apk


def make_fake_apk(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return path


def test_inspects_native_abis_from_apk_contents(tmp_path, monkeypatch):
    monkeypatch.setattr("novera.apk_inspector.shutil.which", lambda _name: None)
    apk = make_fake_apk(tmp_path / "filename-says-x86.apk", {
        "AndroidManifest.xml": b"binary manifest placeholder",
        "lib/arm64-v8a/libnative.so": b"fake native library",
        "lib/armeabi-v7a/libnative.so": b"fake native library",
    })
    info = inspect_apk(apk)
    assert info.native_abis == ("arm64-v8a", "armeabi-v7a")
    assert info.package_name is None
    assert info.inspection_method == "ZIP ABI scan"
    assert any("aapt" in note for note in info.notes)


def test_apk_inspector_uses_aapt_metadata_when_available(tmp_path, monkeypatch):
    apk = make_fake_apk(tmp_path / "app.apk", {"AndroidManifest.xml": b"manifest"})
    monkeypatch.setattr("novera.apk_inspector.shutil.which", lambda name: "/fake/aapt" if name == "aapt" else None)
    fake = subprocess.CompletedProcess(args=["aapt"], returncode=0, stdout=(
        "package: name='org.example.app' versionCode='42' versionName='4.2'\n"
        "sdkVersion:'23'\ntargetSdkVersion:'35'\nnative-code: 'arm64-v8a' 'x86_64'\n"
    ), stderr="")
    monkeypatch.setattr("novera.apk_inspector.subprocess.run", lambda *args, **kwargs: fake)
    info = inspect_apk(apk)
    assert info.package_name == "org.example.app"
    assert info.version_name == "4.2"
    assert info.version_code == "42"
    assert info.min_sdk == "23"
    assert info.target_sdk == "35"
    assert info.native_abis == ("arm64-v8a", "x86_64")


def test_split_package_formats_not_misidentified_as_standalone(tmp_path):
    path = tmp_path / "bundle.apks"
    path.write_bytes(b"not inspected as a standalone APK")
    with pytest.raises(APKInspectionError, match="container/split-package"):
        inspect_apk(path)


def test_zip_without_android_manifest_is_not_apk(tmp_path):
    path = make_fake_apk(tmp_path / "not-an-apk.apk", {"readme.txt": b"just a zip"})
    with pytest.raises(APKInspectionError, match="AndroidManifest.xml"):
        inspect_apk(path)


def test_invalid_apk_rejected(tmp_path):
    path = tmp_path / "broken.apk"
    path.write_bytes(b"not zip")
    with pytest.raises(APKInspectionError, match="ZIP/APK yang valid"):
        inspect_apk(path)
