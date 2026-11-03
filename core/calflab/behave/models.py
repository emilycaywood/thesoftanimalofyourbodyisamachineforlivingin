"""Model weights for pose trackers: what to download, from where, under which licence (ADR-077).

Weights are not Python packages, so they are fetched by ``calflab tracker
download <key>`` (or the Behave panel's button) into
:func:`calflab.paths.models_dir`, checked against the SHA-256 recorded
here, and described in ``<models>/<key>/manifest.json``. Nothing is
downloaded implicitly: a tracker whose files are missing says so and how to
get them.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from calflab.paths import models_dir


class ModelFile(BaseModel):
    name: str  # file name in <models>/<key>/
    url: str
    sha256: str  # of the downloaded file (the archive, if ``member`` is set)
    size_mb: float
    member: str = ""  # path inside a zip archive
    licence: str = ""


class ModelPackage(BaseModel):
    key: str
    label: str
    files: list[ModelFile]
    licence: str
    research_use: str
    notes: str = ""


PACKAGES: dict[str, ModelPackage] = {
    "rtmpose_ap10k": ModelPackage(
        key="rtmpose_ap10k",
        label="RTMPose-m (AP-10K animal keypoints) + YOLOX-s (COCO detector)",
        files=[
            ModelFile(
                name="rtmpose-m_ap10k_256x256.onnx",
                url="https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/"
                    "rtmpose-m_simcc-ap10k_pt-aic-coco_210e-256x256-7a041aa1_20230206.zip",
                sha256="2d75445331cf2f21d6e164430f96ffa765cd874872965ae1736932dda03987f0",
                size_mb=50.7,
                member="20230831/rtmpose_onnx/rtmpose-m_simcc-ap10k_pt-aic-coco_210e-256x256-7a041aa1_20230206/"
                       "end2end.onnx",
                licence="Apache-2.0 (OpenMMLab MMPose); trained on AP-10K (CC-BY-4.0)",
            ),
            ModelFile(
                name="yolox_s.onnx",
                url="https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.onnx",
                sha256="c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063",
                size_mb=35.9,
                licence="Apache-2.0 (Megvii YOLOX); trained on COCO",
            ),
        ],
        licence="Apache-2.0 code and weights; AP-10K annotations CC-BY-4.0 (cite Yu et al., NeurIPS 2021)",
        research_use="yes (permissive; attribution)",
        notes="Approved by the researcher on 2026-11-03 (ADR-077).",
    ),
}


def package_dir(key: str) -> Path:
    return models_dir() / key


def file_path(key: str, name: str) -> Path:
    return package_dir(key) / name


def missing(key: str) -> list[str]:
    pkg = PACKAGES[key]
    return [f.name for f in pkg.files if not file_path(key, f.name).is_file()]


def status(key: str) -> dict[str, Any]:
    pkg = PACKAGES[key]
    man = package_dir(key) / "manifest.json"
    return {
        "key": key, "label": pkg.label, "licence": pkg.licence, "research_use": pkg.research_use,
        "dir": str(package_dir(key)), "missing": missing(key),
        "size_mb": round(sum(f.size_mb for f in pkg.files), 1),
        "manifest": json.loads(man.read_text(encoding="utf-8")) if man.is_file() else None,
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(key: str, report: Callable[[float, str], None] | None = None,
             cancelled: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Fetch every missing file of a package, check its SHA-256, unpack, write the manifest."""
    if key not in PACKAGES:
        raise KeyError(f"No model package {key!r}. Known: {', '.join(PACKAGES)}")
    pkg = PACKAGES[key]
    dest = package_dir(key)
    dest.mkdir(parents=True, exist_ok=True)
    total = sum(f.size_mb for f in pkg.files) or 1.0
    done_mb = 0.0
    record: list[dict[str, Any]] = []
    for f in pkg.files:
        target = dest / f.name
        if not target.is_file():
            with tempfile.TemporaryDirectory(dir=dest) as tmp:
                raw = Path(tmp) / "download"
                with urllib.request.urlopen(f.url, timeout=60) as resp, raw.open("wb") as out:  # noqa: S310 - fixed URLs
                    got = 0
                    while True:
                        if cancelled is not None and cancelled():
                            raise RuntimeError("Download cancelled")
                        block = resp.read(1 << 20)
                        if not block:
                            break
                        out.write(block)
                        got += len(block)
                        if report is not None:
                            report(min(0.99, (done_mb + got / 1e6) / total), f"{f.name}: {got / 1e6:.1f} MB")
                digest = _sha256(raw)
                if digest != f.sha256:
                    raise ValueError(f"{f.url}: SHA-256 {digest} does not match the recorded {f.sha256}; not used")
                if f.member:
                    with zipfile.ZipFile(raw) as z, z.open(f.member) as src, (Path(tmp) / f.name).open("wb") as out:
                        shutil.copyfileobj(src, out)
                    shutil.move(str(Path(tmp) / f.name), target)
                else:
                    shutil.move(str(raw), target)
        done_mb += f.size_mb
        record.append({"name": f.name, "url": f.url, "download_sha256": f.sha256, "member": f.member,
                       "file_sha256": _sha256(target), "licence": f.licence})
    manifest = {"key": key, "label": pkg.label, "licence": pkg.licence, "research_use": pkg.research_use,
                "downloaded": time.strftime("%Y-%m-%dT%H:%M:%S"), "files": record}
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if report is not None:
        report(1.0, "done")
    return manifest
