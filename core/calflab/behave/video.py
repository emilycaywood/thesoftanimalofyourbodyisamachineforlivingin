"""Reading video files: frames and the real frame rate (ADR-076).

Two readers, chosen by :func:`open_video`:

* **OpenCV** (``cv2``, the optional ``video`` extra): mp4, mov, avi, mkv and
  whatever else the bundled FFmpeg decodes. Imported only when a video is
  opened.
* **Built-in AVI** (no dependency): RIFF AVI 1.0 with uncompressed frames
  (8-bit paletted or 24-bit BGR) or Motion JPEG (decoded with Pillow, if it
  is installed). Enough for synthetic test footage and for cameras that write
  MJPEG AVI.

The frame rate is the one the file declares (OpenCV's ``CAP_PROP_FPS``; the
AVI stream header's rate / scale), never assumed. Frames come back as RGB
``uint8`` arrays ``[height, width, 3]``.

:func:`write_avi` writes 8-bit paletted AVI (readable by both readers and by
any FFmpeg-based player) for synthetic footage; :func:`encode_image` turns a
frame into JPEG (OpenCV) or PNG (built in) bytes for the web lab.
"""

from __future__ import annotations

import importlib.util
import io
import struct
import zlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel

VIDEO_SUFFIXES = (".mp4", ".mov", ".avi", ".mkv")


class VideoError(Exception):
    """A video that cannot be read, with the reason (shown to the user as is)."""


class VideoInfo(BaseModel):
    """What the file declares. ``frames`` may be approximate for some containers (OpenCV)."""

    fps: float
    frames: int
    width: int
    height: int
    codec: str = ""
    reader: str = ""  # opencv | avi

    @property
    def duration_s(self) -> float:
        return self.frames / self.fps if self.fps > 0 else 0.0


def opencv_available() -> bool:
    return importlib.util.find_spec("cv2") is not None


def missing_reader_message(suffix: str) -> str:
    return (f"Cannot read {suffix} files: OpenCV is not installed. Install the optional extra 'video' "
            "(uv sync --extra video, or .\\calflab.ps1 setup), or convert the video to MJPEG AVI.")


class VideoReader:
    """Sequential and random access to one video's frames."""

    info: VideoInfo

    def frame(self, index: int) -> np.ndarray:
        raise NotImplementedError

    def frames(self, start: int = 0, stop: int | None = None, step: int = 1) -> Iterator[tuple[int, np.ndarray]]:
        stop = self.info.frames if stop is None else min(stop, self.info.frames)
        for i in range(start, stop, step):
            yield i, self.frame(i)

    def close(self) -> None:  # noqa: B027 - optional hook
        pass

    def __enter__(self) -> VideoReader:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


# ---------------------------------------------------------------------- OpenCV
class OpenCVReader(VideoReader):
    def __init__(self, path: Path):
        import cv2  # lazy: optional extra

        self._cv2 = cv2
        self._cap = cv2.VideoCapture(str(path))
        if not self._cap.isOpened():
            raise VideoError(f"{path.name}: OpenCV cannot open this file (unsupported codec or not a video)")
        fps = float(self._cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if not np.isfinite(fps) or fps <= 0:
            raise VideoError(f"{path.name}: the file does not declare a frame rate")
        fourcc = int(self._cap.get(cv2.CAP_PROP_FOURCC) or 0)
        codec = "".join(chr((fourcc >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00 ") if fourcc else ""
        self.info = VideoInfo(
            fps=fps, frames=int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0),
            width=int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)), height=int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            codec=codec, reader="opencv",
        )
        self._next = 0

    def frame(self, index: int) -> np.ndarray:
        cv2 = self._cv2
        if index != self._next:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, img = self._cap.read()
        if not ok:
            raise VideoError(f"Frame {index} could not be read")
        self._next = index + 1
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    def frames(self, start: int = 0, stop: int | None = None, step: int = 1) -> Iterator[tuple[int, np.ndarray]]:
        cv2 = self._cv2
        if start != self._next:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        i = start
        while stop is None or i < stop:
            ok, img = self._cap.read()
            if not ok:
                break
            if (i - start) % step == 0:
                yield i, cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            i += 1
        self._next = i

    def close(self) -> None:
        self._cap.release()


# ---------------------------------------------------------------------- built-in AVI
def _chunks(data: bytes, start: int, end: int) -> Iterator[tuple[bytes, int, int, bytes | None]]:
    """(fourcc, data offset, size, list type or None) for each chunk between start and end."""
    pos = start
    while pos + 8 <= end:
        fourcc = data[pos:pos + 4]
        (size,) = struct.unpack_from("<I", data, pos + 4)
        if fourcc in (b"LIST", b"RIFF"):
            yield fourcc, pos + 12, size - 4, data[pos + 8:pos + 12]
        else:
            yield fourcc, pos + 8, size, None
        pos += 8 + size + (size & 1)


class AviReader(VideoReader):
    """RIFF AVI 1.0, one video stream: uncompressed 8/24-bit DIB or MJPEG."""

    def __init__(self, path: Path):
        data = path.read_bytes()
        if data[:4] != b"RIFF" or data[8:12] != b"AVI ":
            raise VideoError(f"{path.name}: not a RIFF AVI file")
        self._data = data
        self._offsets: list[tuple[int, int]] = []
        strh: tuple[int, int] | None = None
        bih: bytes | None = None
        palette: np.ndarray | None = None
        handler = b""

        def walk(start: int, end: int) -> None:
            nonlocal strh, bih, palette, handler
            for fourcc, off, size, ltype in _chunks(data, start, end):
                if ltype is not None:
                    walk(off, off + size)
                elif fourcc == b"strh" and data[off:off + 4] == b"vids" and strh is None:
                    handler = data[off + 4:off + 8]
                    scale, rate = struct.unpack_from("<II", data, off + 20)
                    strh = (scale, rate)
                elif fourcc == b"strf" and bih is None and strh is not None:
                    bih = data[off:off + 40]
                    bits = struct.unpack_from("<H", bih, 14)[0]
                    if bits <= 8 and size > 40:
                        n = (size - 40) // 4
                        pal = np.frombuffer(data, dtype=np.uint8, count=n * 4, offset=off + 40).reshape(n, 4)
                        palette = pal[:, [2, 1, 0]].copy()  # BGRA -> RGB
                elif fourcc[2:] in (b"db", b"dc") and fourcc[:2] == b"00":
                    self._offsets.append((off, size))

        walk(12, min(len(data), 8 + struct.unpack_from("<I", data, 4)[0]))
        if strh is None or bih is None:
            raise VideoError(f"{path.name}: no video stream header")
        scale, rate = strh
        if scale == 0 or rate == 0:
            raise VideoError(f"{path.name}: the stream header has no frame rate")
        _, w, h, _, bits, comp = struct.unpack_from("<IiiHHI", bih, 0)
        self._w, self._h, self._bits, self._flip = w, abs(h), bits, h > 0
        self._comp = comp
        self._palette = palette
        codec = struct.pack("<I", comp).decode("latin-1").strip("\x00 ") if comp else "raw"
        if comp not in (0,) and struct.pack("<I", comp) not in (b"MJPG", b"mjpg"):
            raise VideoError(f"{path.name}: the built-in AVI reader handles uncompressed and MJPEG frames only "
                             f"(this one is {codec!r}). {missing_reader_message('.avi')}")
        if comp == 0 and bits not in (8, 24):
            raise VideoError(f"{path.name}: {bits}-bit uncompressed frames are not supported")
        self.info = VideoInfo(fps=rate / scale, frames=len(self._offsets), width=w, height=abs(h),
                              codec=codec or handler.decode("latin-1"), reader="avi")

    def frame(self, index: int) -> np.ndarray:
        if not 0 <= index < len(self._offsets):
            raise VideoError(f"Frame {index} is outside the video (0..{len(self._offsets) - 1})")
        off, size = self._offsets[index]
        if self._comp != 0:
            try:
                from PIL import Image
            except ImportError as exc:
                raise VideoError("MJPEG frames need Pillow or OpenCV; " + missing_reader_message(".avi")) from exc
            return np.asarray(Image.open(io.BytesIO(self._data[off:off + size])).convert("RGB"))
        w, h = self._w, self._h
        bpp = self._bits // 8
        stride = (w * bpp + 3) & ~3
        rows = np.frombuffer(self._data, dtype=np.uint8, count=stride * h, offset=off).reshape(h, stride)
        px = rows[:, : w * bpp]
        if self._flip:
            px = px[::-1]
        if bpp == 1:
            if self._palette is None:
                raise VideoError("8-bit frames without a palette")
            return self._palette[px]
        return px.reshape(h, w, 3)[:, :, ::-1].copy()


def open_video(path: Path) -> VideoReader:
    """A reader for ``path``: OpenCV when installed, else the built-in AVI reader for .avi files."""
    path = Path(path)
    if not path.is_file():
        raise VideoError(f"No file {path}")
    if opencv_available():
        try:
            return OpenCVReader(path)
        except VideoError:
            if path.suffix.lower() != ".avi":
                raise
    if path.suffix.lower() == ".avi":
        return AviReader(path)
    raise VideoError(missing_reader_message(path.suffix.lower()))


def probe(path: Path) -> VideoInfo:
    with open_video(path) as r:
        return r.info


# ---------------------------------------------------------------------- writing (synthetic footage)
def write_avi(path: Path, frames: list[np.ndarray] | np.ndarray, fps: float, palette: np.ndarray) -> Path:
    """Write 8-bit paletted, uncompressed AVI. ``frames``: [n, h, w] palette indices (uint8);
    ``palette``: [<=256, 3] RGB. The frame rate is stored exactly as rate/scale = fps*1000/1000."""
    frames = np.asarray(frames, dtype=np.uint8)
    n, h, w = frames.shape
    pal = np.zeros((256, 4), dtype=np.uint8)
    pal[: len(palette), :3] = np.asarray(palette, dtype=np.uint8)[:, ::-1]  # RGB -> BGR(A)
    stride = (w + 3) & ~3
    frame_size = stride * h
    scale, rate = 1000, int(round(fps * 1000))

    def chunk(fourcc: bytes, payload: bytes) -> bytes:
        return fourcc + struct.pack("<I", len(payload)) + payload + (b"\x00" if len(payload) & 1 else b"")

    def lst(ltype: bytes, payload: bytes) -> bytes:
        return b"LIST" + struct.pack("<I", len(payload) + 4) + ltype + payload

    avih = struct.pack("<IIIIIIIIII16x", int(round(1e6 / fps)), frame_size * int(np.ceil(fps)), 0, 0x10, n, 0, 1,
                       frame_size, w, h)
    strh = b"vids" + b"\x00\x00\x00\x00" + struct.pack("<IHHIIIIIIIIhhhh", 0, 0, 0, 0, scale, rate, 0, n, frame_size,
                                                      0xFFFFFFFF, 0, 0, 0, w, h)
    bih = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 8, 0, frame_size, 0, 0, 256, 0) + pal.tobytes()
    hdrl = lst(b"hdrl", chunk(b"avih", avih) + lst(b"strl", chunk(b"strh", strh) + chunk(b"strf", bih)))
    body = bytearray()
    index = bytearray()
    pad = np.zeros((h, stride), dtype=np.uint8)
    for f in frames:
        pad[:, :w] = f[::-1]  # bottom-up rows
        index += b"00db" + struct.pack("<III", 0x10, 4 + len(body), frame_size)
        body += chunk(b"00db", pad.tobytes())
    movi = lst(b"movi", bytes(body))
    riff_body = b"AVI " + hdrl + movi + chunk(b"idx1", bytes(index))
    path = Path(path)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(riff_body)) + riff_body)
    return path


# ---------------------------------------------------------------------- images for the web lab
def _png(rgb: np.ndarray) -> bytes:
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def encode_image(rgb: np.ndarray, max_width: int = 0) -> tuple[bytes, str]:
    """(bytes, media type) of a frame: JPEG through OpenCV when installed, else PNG. ``max_width`` > 0 scales it
    down (nearest neighbour without OpenCV)."""
    img: Any = np.ascontiguousarray(rgb, dtype=np.uint8)
    if max_width and img.shape[1] > max_width:
        if opencv_available():
            import cv2

            h = int(round(img.shape[0] * max_width / img.shape[1]))
            img = cv2.resize(img, (max_width, h), interpolation=cv2.INTER_AREA)
        else:
            step = int(np.ceil(img.shape[1] / max_width))
            img = img[::step, ::step]
    if opencv_available():
        import cv2

        ok, buf = cv2.imencode(".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if ok:
            return bytes(buf), "image/jpeg"
    return _png(np.ascontiguousarray(img)), "image/png"
