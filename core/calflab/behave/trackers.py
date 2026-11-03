"""Pose trackers (ADR-077): video -> keypoint tracks with a confidence per point.

* ``csv``: tracking done elsewhere (DeepLabCut, SLEAP, by hand): reads the CSV
  next to the video (same name), at the video's frame rate.
* ``synthetic``: finds coloured marker discs by colour; made for the stick calf
  of :mod:`calflab.behave.synthetic` and for tests.
* ``rtmpose_ap10k``: RTMPose-m trained on AP-10K (17 animal keypoints), top-down
  after a YOLOX-s COCO detector, through ONNX Runtime (DirectML on the AMD GPU
  when available, else CPU). Needs the ``track`` extra and the downloaded
  weights (:mod:`calflab.behave.models`).

Every tracker returns image pixels with y up (as :mod:`calflab.behave.keypoints`)
and fills ``KeypointTracks.model`` with its provenance.
"""

from __future__ import annotations

import importlib.util
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel

from calflab.behave import models
from calflab.behave.keypoints import KeypointTracks, read_tracks
from calflab.behave.video import open_video, probe
from calflab.plugins import PoseTracker, TrackerCancelled, register
from calflab.schema import P

log = logging.getLogger(__name__)

Report = Callable[[float, str], None] | None
Cancelled = Callable[[], bool] | None


def _check(cancelled: Cancelled) -> None:
    if cancelled is not None and cancelled():
        raise TrackerCancelled()


# ---------------------------------------------------------------------- csv
@register
class CsvTracker(PoseTracker):
    """Keypoints tracked elsewhere: the CSV next to the video."""

    key = "csv"
    label = "CSV next to the video"
    description = ("Keypoints tracked elsewhere (DeepLabCut, SLEAP, by hand): reads <video name>.csv (or the file named "
                   "here) beside the video, at the video's own frame rate.")
    model_id = "csv"
    model_version = "1"
    needs_sidecar = True

    class Params(BaseModel):
        file: str = P("", desc="CSV beside the video (empty = the video's name with .csv, or <name>*.csv).")
        format: str = P("auto", choices=["auto", "dlc", "long", "wide"], desc="CSV layout.")
        fps: float = P(0.0, unit="fps", ge=0, le=1000, desc="Frame rate (0 = the video's own).")

    def sidecar(self, video: Path) -> Path | None:
        p = self.params
        if p.file:  # type: ignore[attr-defined]
            c = video.parent / p.file  # type: ignore[attr-defined]
            return c if c.is_file() else None
        exact = video.with_suffix(".csv")
        if exact.is_file():
            return exact
        found = sorted(video.parent.glob(f"{video.stem}*.csv"))
        return found[0] if found else None

    def track(self, video: Path, report: Report = None, cancelled: Cancelled = None) -> KeypointTracks:
        video = Path(video)
        csv = self.sidecar(video)
        if csv is None:
            raise FileNotFoundError(f"No CSV beside {video.name}: put the tracker's output there as {video.stem}.csv")
        fps = float(self.params.fps) or probe(video).fps  # type: ignore[attr-defined]
        tracks = read_tracks(csv, fps, self.params.format)  # type: ignore[attr-defined]
        if report is not None:
            report(1.0, f"read {csv.name}")
        prov = {**self.provenance(), "file": csv.name}
        return tracks.model_copy(update={"model": prov, "source": video.name})


# ---------------------------------------------------------------------- synthetic (colour markers)
def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _default_markers() -> dict[str, str]:
    from calflab.behave.synthetic import MARKERS

    return {n: "#{:02x}{:02x}{:02x}".format(*col) for n, (_, _, col) in MARKERS.items()}


@register
class SyntheticTracker(PoseTracker):
    """Finds coloured marker discs (the synthetic stick calf)."""

    key = "synthetic"
    label = "Colour markers (synthetic)"
    description = ("Finds each landmark as the centre of the pixels of its marker colour. Made for the synthetic stick "
                   "calf drawn from the robot's forward kinematics; works on any footage with painted markers.")
    model_id = "colour-markers"
    model_version = "1"

    class Params(BaseModel):
        markers: dict[str, str] = P(default_factory=_default_markers, ui="json",
                                    desc="Landmark name -> marker colour (#rrggbb).")
        tolerance: int = P(24, ge=0, le=128, desc="Largest difference per colour channel that still counts.")
        min_pixels: int = P(3, ge=1, le=1000, desc="Fewer marker pixels than this = not seen.")

    def keypoint_names(self) -> list[str]:
        return list(self.params.markers)  # type: ignore[attr-defined]

    def track(self, video: Path, report: Report = None, cancelled: Cancelled = None) -> KeypointTracks:
        p = self.params
        names = self.keypoint_names()
        cols = np.array([_hex(c) for c in p.markers.values()], dtype=np.int16)  # type: ignore[attr-defined]
        with open_video(Path(video)) as r:
            n = r.info.frames
            xy = np.full((n, len(names), 2), np.nan)
            conf = np.zeros((n, len(names)))
            for i, img in r.frames():
                _check(cancelled)
                im = img.astype(np.int16)
                for k, c in enumerate(cols):
                    mask = np.all(np.abs(im - c) <= p.tolerance, axis=2)  # type: ignore[attr-defined]
                    cnt = int(mask.sum())
                    if cnt >= p.min_pixels:  # type: ignore[attr-defined]
                        ys, xs = np.nonzero(mask)
                        xy[i, k] = (xs.mean(), ys.mean())
                        conf[i, k] = 1.0
                if report is not None and (i % 10 == 0 or i == n - 1):
                    report((i + 1) / max(n, 1), f"frame {i + 1}/{n}")
            info = r.info
        xy[:, :, 1] = -xy[:, :, 1]
        return KeypointTracks(fps=info.fps, names=names, xy=xy, likelihood=conf, source=Path(video).name,
                              model=self.provenance(), image_size=(info.width, info.height))


# ---------------------------------------------------------------------- RTMPose AP-10K
#: Keypoint names of the AP-10K model, in output order. The ONNX file carries no names: its ``detail.json`` names
#: the MMPose config ``rtmpose-m_8xb64-210e_ap10k-256x256.py``, whose dataset metainfo
#: (https://github.com/open-mmlab/mmpose/blob/v1.1.0/configs/_base_/datasets/ap10k.py, read 2026-11-03) lists these.
#: The count is checked against the model's output when it is loaded.
AP10K_KEYPOINTS = ["L_Eye", "R_Eye", "Nose", "Neck", "Root of tail", "L_Shoulder", "L_Elbow", "L_F_Paw", "R_Shoulder",
                   "R_Elbow", "R_F_Paw", "L_Hip", "L_Knee", "L_B_Paw", "R_Hip", "R_Knee", "R_B_Paw"]
AP10K_SKELETON = [("L_Eye", "R_Eye"), ("L_Eye", "Nose"), ("R_Eye", "Nose"), ("Nose", "Neck"), ("Neck", "Root of tail"),
                  ("Neck", "L_Shoulder"), ("L_Shoulder", "L_Elbow"), ("L_Elbow", "L_F_Paw"), ("Neck", "R_Shoulder"),
                  ("R_Shoulder", "R_Elbow"), ("R_Elbow", "R_F_Paw"), ("Root of tail", "L_Hip"), ("L_Hip", "L_Knee"),
                  ("L_Knee", "L_B_Paw"), ("Root of tail", "R_Hip"), ("R_Hip", "R_Knee"), ("R_Knee", "R_B_Paw")]
#: COCO class indices of the YOLOX detector that a calf may be detected as
COCO_ANIMALS = {"dog": 16, "horse": 17, "sheep": 18, "cow": 19}


def _session(path: Path, device: str) -> tuple[Any, str]:
    import onnxruntime as ort

    avail = ort.get_available_providers()
    so = ort.SessionOptions()
    if device in ("auto", "directml") and "DmlExecutionProvider" in avail:
        so.enable_mem_pattern = False  # required by DirectML
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        try:
            return ort.InferenceSession(str(path), so, providers=["DmlExecutionProvider", "CPUExecutionProvider"]), "directml"
        except Exception as exc:  # a GPU driver problem must not stop tracking
            if device == "directml":
                raise
            log.warning("DirectML failed (%s); using the CPU", exc)
    if device == "directml":
        raise RuntimeError("DirectML is not available in this onnxruntime (install onnxruntime-directml)")
    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"]), "cpu"


def _letterbox(img: np.ndarray, size: int = 640) -> tuple[np.ndarray, float]:
    import cv2

    h, w = img.shape[:2]
    r = min(size / h, size / w)
    out = np.full((size, size, 3), 114, dtype=np.uint8)
    out[: int(h * r), : int(w * r)] = cv2.resize(img, (int(w * r), int(h * r)), interpolation=cv2.INTER_LINEAR)
    return out, r


def _yolox_decode(raw: np.ndarray, size: int = 640) -> np.ndarray:
    """YOLOX head output [n, 85] -> boxes (cx, cy, w, h) in letterbox pixels, objectness, class scores."""
    grids, strides = [], []
    for s in (8, 16, 32):
        g = size // s
        yv, xv = np.meshgrid(np.arange(g), np.arange(g), indexing="ij")
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
        strides.append(np.full((g * g, 1), s))
    grid = np.concatenate(grids)
    stride = np.concatenate(strides)
    out = raw.copy()
    out[:, :2] = (out[:, :2] + grid) * stride
    out[:, 2:4] = np.exp(out[:, 2:4]) * stride
    return out


def estimate(pose: Any, rgb: np.ndarray, box: np.ndarray, padding: float = 1.25) -> tuple[np.ndarray, np.ndarray]:
    """One top-down RTMPose estimate: keypoints [k, 2] in image pixels (y down) and their scores, for the animal in
    ``box`` (cx, cy, w, h). Pre- and post-processing as the model's ``pipeline.json``: the box enlarged by
    ``padding`` to the model's aspect, affine crop to 256 x 256, RGB normalised, SimCC argmax / 2."""
    import cv2

    W = H = 256
    mean = np.array([123.675, 116.28, 103.53], dtype=np.float32)
    std = np.array([58.395, 57.12, 57.375], dtype=np.float32)
    cx, cy, bw, bh = box[0], box[1], box[2] * padding, box[3] * padding
    if bw / bh > W / H:  # keep the model's aspect ratio
        bh = bw * H / W
    else:
        bw = bh * W / H
    sx, sy = W / bw, H / bh
    M = np.array([[sx, 0, -(cx - bw / 2) * sx], [0, sy, -(cy - bh / 2) * sy]], dtype=np.float32)
    crop = cv2.warpAffine(rgb, M, (W, H), flags=cv2.INTER_LINEAR)
    inp = ((crop.astype(np.float32) - mean) / std).transpose(2, 0, 1)[None]
    sx_out, sy_out = pose.run(None, {pose.get_inputs()[0].name: inp})
    lx, ly = sx_out[0].argmax(axis=1), sy_out[0].argmax(axis=1)
    vx, vy = sx_out[0].max(axis=1), sy_out[0].max(axis=1)
    xy = np.stack([lx / 2.0 / sx + (cx - bw / 2), ly / 2.0 / sy + (cy - bh / 2)], axis=1)  # simcc_split_ratio 2.0
    return xy, np.clip(np.minimum(vx, vy), 0.0, None)


@register
class RTMPoseAP10K(PoseTracker):
    """RTMPose-m (AP-10K) after a YOLOX-s detector, through ONNX Runtime."""

    key = "rtmpose_ap10k"
    label = "RTMPose AP-10K (animal keypoints)"
    description = ("A pretrained animal pose model: YOLOX-s finds the animal (COCO cow, horse, sheep or dog), RTMPose-m "
                   "gives 17 AP-10K keypoints with a confidence each. Runs on the AMD GPU through DirectML, else the "
                   "CPU. Apache-2.0; trained on AP-10K (CC-BY-4.0).")
    model_id = "rtmpose-m_simcc-ap10k_pt-aic-coco_210e-256x256-7a041aa1_20230206 + yolox_s 0.1.1rc0"
    model_version = "2023-02-06"

    class Params(BaseModel):
        device: str = P("auto", choices=["auto", "directml", "cpu"], desc="Where to run (auto = DirectML if present).")
        animals: list[str] = P(default_factory=lambda: ["cow", "horse", "sheep", "dog"], ui="json",
                               desc="Detector classes the calf may be found as.")
        detect_threshold: float = P(0.3, ge=0.05, le=0.95, step=0.05, desc="Lowest detection score accepted.")
        detect_every: int = P(1, ge=1, le=30, desc="Run the detector every n frames; between, follow the keypoints.")
        stride: int = P(1, ge=1, le=10, desc="Track every n-th frame (others are left for cleaning to fill).")
        padding: float = P(1.25, ge=1.0, le=2.0, step=0.05, desc="Box enlargement before pose estimation.")

    def available(self) -> tuple[bool, str]:
        lacking = [m for m in ("cv2", "onnxruntime") if importlib.util.find_spec(m) is None]
        if lacking:
            return False, f"Missing {', '.join(lacking)}: install the optional extra 'track' (uv sync --extra track)"
        files = models.missing("rtmpose_ap10k")
        if files:
            return False, (f"Model weights not downloaded ({', '.join(files)}): run "
                           "'.\\calflab.ps1 tracker download rtmpose_ap10k' or use Download in the Behave panel")
        return True, "ok"

    def keypoint_names(self) -> list[str]:
        return list(AP10K_KEYPOINTS)

    def provenance(self) -> dict[str, Any]:
        prov = super().provenance()
        st = models.status("rtmpose_ap10k")
        if st["manifest"]:
            prov["files"] = {f["name"]: f["file_sha256"] for f in st["manifest"]["files"]}
        return prov

    def track(self, video: Path, report: Report = None, cancelled: Cancelled = None) -> KeypointTracks:
        import cv2

        ok, why = self.available()
        if not ok:
            raise RuntimeError(why)
        p = self.params
        pose, dev = _session(models.file_path("rtmpose_ap10k", "rtmpose-m_ap10k_256x256.onnx"), p.device)  # type: ignore[attr-defined]
        det, _ = _session(models.file_path("rtmpose_ap10k", "yolox_s.onnx"), p.device)  # type: ignore[attr-defined]
        classes = [COCO_ANIMALS[a] for a in p.animals if a in COCO_ANIMALS]  # type: ignore[attr-defined]
        if not classes:
            raise ValueError(f"No known detector class in {p.animals}; choose from {', '.join(COCO_ANIMALS)}")  # type: ignore[attr-defined]
        names = self.keypoint_names()
        with open_video(Path(video)) as r:
            info = r.info
            n = info.frames
            xy = np.full((n, len(names), 2), np.nan)
            conf = np.zeros((n, len(names)))
            boxes = np.full((n, 5), np.nan)
            box: np.ndarray | None = None
            for i, rgb in r.frames(step=int(p.stride)):  # type: ignore[attr-defined]
                _check(cancelled)
                if box is None or i % int(p.detect_every) == 0:  # type: ignore[attr-defined]
                    lb, ratio = _letterbox(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
                    raw = det.run(None, {det.get_inputs()[0].name: lb.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
                    d = _yolox_decode(raw)
                    scores = d[:, 4:5] * d[:, 5:]
                    best = scores[:, classes].max(axis=1)
                    keep = best >= p.detect_threshold  # type: ignore[attr-defined]
                    found = None
                    if np.any(keep):
                        cand = d[keep, :4] / ratio
                        sc = best[keep]
                        if box is not None:  # follow the same animal: nearest centre, then score
                            dist = np.hypot(cand[:, 0] - box[0], cand[:, 1] - box[1]) / max(box[2], box[3], 1.0)
                            k = int(np.argmin(dist - sc))
                        else:
                            k = int(np.argmax(sc))
                        found = np.array([*cand[k], sc[k]])
                    if found is not None:
                        box = found
                if box is None:
                    continue
                boxes[i] = box
                kxy, kc = estimate(pose, rgb, box, float(p.padding))  # type: ignore[attr-defined]
                if len(kc) != len(names):
                    raise RuntimeError(f"The pose model gives {len(kc)} keypoints, its metainfo names "
                                       f"{len(names)}: wrong model file?")
                xy[i], conf[i] = kxy, kc
                # follow the animal between detections: the box round the confident keypoints
                good = conf[i] > 0.3
                if good.sum() >= 4:
                    x0, y0 = xy[i, good].min(axis=0)
                    x1, y1 = xy[i, good].max(axis=0)
                    box = np.array([(x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) * 1.1, (y1 - y0) * 1.1, box[4]])
                if report is not None and (i % 5 == 0 or i >= n - 1):
                    report((i + 1) / max(n, 1), f"frame {i + 1}/{n} ({dev})")
        xy[:, :, 1] = -xy[:, :, 1]
        prov = {**self.provenance(), "device": dev, "boxes_found": int(np.sum(~np.isnan(boxes[:, 0])))}
        return KeypointTracks(fps=info.fps, names=names, xy=xy, likelihood=conf, source=Path(video).name, model=prov,
                              image_size=(info.width, info.height))
