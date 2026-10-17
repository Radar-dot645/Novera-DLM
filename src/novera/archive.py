"""Safe ZIP extraction: blocks traversal, absolute paths, symlinks, zip bombs."""
from __future__ import annotations

import stat
import zipfile
from pathlib import Path


class ArchiveError(ValueError):
    pass


MAX_FILES = 100_000
MAX_TOTAL = 8 * 1024**3
MAX_RATIO = 1000


def safe_extract(zip_path: Path, dest: Path, progress=None) -> int:
    """Extract zip_path into dest. progress(done_bytes,total_bytes). Returns file count."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArchiveError(f"ZIP rusak atau tidak bisa dibuka: {exc}") from exc
    with zf:
        infos = zf.infolist()
        total = sum(i.file_size for i in infos)
        if len(infos) > MAX_FILES or total > MAX_TOTAL:
            raise ArchiveError("ZIP melampaui batas jumlah file/ukuran (indikasi zip bomb).")
        dest.mkdir(parents=True, exist_ok=True)
        root = dest.resolve()
        plan = []
        for i in infos:
            name = i.filename
            if name.startswith(("/", "\\")) or (len(name) > 1 and name[1] == ":") or "\x00" in name:
                raise ArchiveError(f"Path absolut/tidak valid ditolak: {name!r}")
            mode = i.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ArchiveError(f"Symlink ditolak: {name!r}")
            if i.compress_size and i.file_size / max(i.compress_size, 1) > MAX_RATIO and i.file_size > 10 * 1024**2:
                raise ArchiveError(f"Rasio kompresi mencurigakan: {name!r}")
            target = (root / name).resolve()
            if target != root and root not in target.parents:
                raise ArchiveError(f"Path traversal ditolak: {name!r}")
            plan.append((i, target))
        done = count = 0
        for i, target in plan:
            if i.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                raise ArchiveError(f"Target adalah symlink: {i.filename!r}")
            with zf.open(i) as src, target.open("wb") as out:
                while chunk := src.read(256 * 1024):
                    out.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
            count += 1
        return count
