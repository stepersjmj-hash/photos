"""사진 자동 리사이즈 + 품질 분류 프로그램.

watch_folder 에 새 사진이 들어오면:
1. EXIF 회전 적용 + 긴 축 3840px 리사이즈
2. 블러 판별 (Laplacian variance, 얼굴 영역 우선)
3. 눈 감김 판별 (MediaPipe Face Mesh, EAR)
4. ok/ blur/ eyes_closed/ 하위 폴더로 분류. 파일은 절대 삭제하지 않는다.

사용법:
    python photo_sorter.py            # 기존 파일 일괄 처리 후 폴더 감시 시작
    python photo_sorter.py --once     # 기존 파일만 처리하고 종료 (테스트용)
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import logging
import shutil
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import yaml
from PIL import Image, ImageOps
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIC_OK = True
except ImportError:
    HEIC_OK = False

import mediapipe as mp

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic"}
CATEGORIES = ("ok", "blur", "eyes_closed", "originals")
MEASURE_LONG_EDGE = 512  # 선명도 측정 전 패치를 이 크기로 정규화 (임계값 일관성)

# MediaPipe Face Mesh 랜드마크 인덱스 (좌/우 눈)
LEFT_EYE = {"top": 386, "bottom": 374, "left": 362, "right": 263}
RIGHT_EYE = {"top": 159, "bottom": 145, "left": 33, "right": 133}

GPS_IFD_TAG = 0x8825

log = logging.getLogger("photo_sorter")


# ---------------------------------------------------------------- 경로/설정

def get_desktop_path() -> Path:
    """실제 바탕화면 경로 조회 (OneDrive 리다이렉트 반영). Windows 전용."""
    if sys.platform == "win32":
        CSIDL_DESKTOPDIRECTORY = 0x10
        buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_DESKTOPDIRECTORY, None, 0, buf)
        return Path(buf.value)
    return Path.home() / "Desktop"


def load_config(config_path: Path) -> dict:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    defaults = {
        "watch_folder": None,
        "max_long_edge": 3840,
        "jpeg_quality": 90,
        "blur_threshold": 100,
        "ear_threshold": 0.18,
        "keep_originals": True,
        "strip_gps_exif": False,
    }
    for k, v in defaults.items():
        cfg.setdefault(k, v)
    if not cfg["watch_folder"]:
        cfg["watch_folder"] = str(get_desktop_path() / "Photos")
    return cfg


def setup_logging(watch_folder: Path) -> None:
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)s  %(message)s", "%Y-%m-%d %H:%M:%S")
    handlers = [logging.FileHandler(watch_folder / "photo_sorter.log", encoding="utf-8")]
    if sys.stdout is not None:  # pythonw(콘솔 없는 실행)에서는 stdout 이 없음
        handlers.append(logging.StreamHandler(sys.stdout))
    for handler in handlers:
        handler.setFormatter(fmt)
        log.addHandler(handler)


def already_running() -> bool:
    """중복 실행 방지 (자동 시작 + 수동 실행이 겹치면 이중 처리되므로)."""
    if sys.platform == "win32":
        ERROR_ALREADY_EXISTS = 183
        ctypes.windll.kernel32.CreateMutexW(None, False, "photo_sorter_single_instance")
        return ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS
    return False


def unique_path(dest: Path) -> Path:
    """동일 파일명 충돌 시 _1, _2 접미사."""
    if not dest.exists():
        return dest
    for i in range(1, 10000):
        candidate = dest.with_stem(f"{dest.stem}_{i}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"빈 파일명을 찾지 못함: {dest}")


def wait_until_stable(path: Path, interval: float = 1.0, checks: int = 2) -> bool:
    """파일 크기가 interval 간격으로 checks회 연속 동일할 때까지 대기."""
    prev = -1
    same = 0
    for _ in range(120):  # 최대 2분 대기
        try:
            size = path.stat().st_size
        except OSError:
            return False
        if size == prev and size > 0:
            same += 1
            if same >= checks - 1:
                return True
        else:
            same = 0
        prev = size
        time.sleep(interval)
    return False


# ---------------------------------------------------------------- 판별 로직

class FaceAnalyzer:
    """MediaPipe Face Mesh 로 얼굴 bbox + EAR 추출."""

    def __init__(self):
        self._mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True, max_num_faces=5,
            min_detection_confidence=0.5)

    def analyze(self, rgb: np.ndarray) -> list[dict]:
        """얼굴별 {bbox: (x0,y0,x1,y1) px, ear: float} 리스트 반환."""
        h, w = rgb.shape[:2]
        # 대형 이미지는 랜드마크 검출용으로만 축소 (좌표는 정규화되어 무관)
        scale = 1280 / max(h, w)
        det_img = cv2.resize(rgb, (int(w * scale), int(h * scale))) if scale < 1 else rgb
        result = self._mesh.process(det_img)
        faces = []
        if not result.multi_face_landmarks:
            return faces
        for lms in result.multi_face_landmarks:
            xs = [p.x for p in lms.landmark]
            ys = [p.y for p in lms.landmark]
            x0, x1 = max(0, int(min(xs) * w)), min(w, int(max(xs) * w))
            y0, y1 = max(0, int(min(ys) * h)), min(h, int(max(ys) * h))
            ears = []
            for eye in (LEFT_EYE, RIGHT_EYE):
                top, bot = lms.landmark[eye["top"]], lms.landmark[eye["bottom"]]
                lft, rgt = lms.landmark[eye["left"]], lms.landmark[eye["right"]]
                vert = np.hypot((top.x - bot.x) * w, (top.y - bot.y) * h)
                horiz = np.hypot((lft.x - rgt.x) * w, (lft.y - rgt.y) * h)
                if horiz > 0:
                    ears.append(vert / horiz)
            ear = float(np.mean(ears)) if ears else None
            faces.append({"bbox": (x0, y0, x1, y1), "ear": ear})
        return faces


def sharpness(gray_patch: np.ndarray) -> float:
    """패치를 MEASURE_LONG_EDGE 로 정규화 후 Laplacian variance."""
    h, w = gray_patch.shape[:2]
    scale = MEASURE_LONG_EDGE / max(h, w)
    if scale < 1:
        gray_patch = cv2.resize(gray_patch, (max(1, int(w * scale)), max(1, int(h * scale))))
    return float(cv2.Laplacian(gray_patch, cv2.CV_64F).var())


def measure_blur(rgb: np.ndarray, faces: list[dict]) -> float:
    """얼굴이 있으면 얼굴 영역 중 최댓값, 없으면 중앙 60% 영역의 선명도."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    if faces:
        values = []
        for f in faces:
            x0, y0, x1, y1 = f["bbox"]
            if x1 - x0 >= 16 and y1 - y0 >= 16:
                values.append(sharpness(gray[y0:y1, x0:x1]))
        if values:
            return max(values)
    my, mx = int(h * 0.2), int(w * 0.2)
    return sharpness(gray[my:h - my, mx:w - mx])


# ---------------------------------------------------------------- 처리 파이프라인

class PhotoProcessor:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.watch = Path(cfg["watch_folder"])
        self.analyzer = FaceAnalyzer()

    def _resize_and_clean(self, img: Image.Image) -> tuple[Image.Image, Image.Exif]:
        img = ImageOps.exif_transpose(img)
        long_edge = max(img.size)
        if long_edge > self.cfg["max_long_edge"]:
            ratio = self.cfg["max_long_edge"] / long_edge
            img = img.resize((round(img.width * ratio), round(img.height * ratio)),
                             Image.Resampling.LANCZOS)
        exif = img.getexif()
        if self.cfg["strip_gps_exif"] and GPS_IFD_TAG in exif:
            del exif[GPS_IFD_TAG]
        return img, exif

    def process(self, src: Path) -> None:
        if not wait_until_stable(src):
            log.warning("%s: 파일 크기가 안정되지 않아 건너뜀", src.name)
            return
        try:
            with Image.open(src) as im:
                im.load()
                img, exif = self._resize_and_clean(im)
        except Exception as e:
            log.error("%s: 이미지 열기 실패 (%s)", src.name, e)
            return

        rgb = np.asarray(img.convert("RGB"))

        # 2단계: 블러 판별 / 3단계: 눈 감김 판별
        faces = self.analyzer.analyze(rgb)
        blur_value = measure_blur(rgb, faces)
        ears = [f["ear"] for f in faces if f["ear"] is not None]
        min_ear = min(ears) if ears else None

        if blur_value <= self.cfg["blur_threshold"]:
            category = "blur"
        elif min_ear is not None and min_ear <= self.cfg["ear_threshold"]:
            category = "eyes_closed"
        else:
            category = "ok"

        # 저장: HEIC 는 JPEG 로 변환, 나머지는 원래 확장자 유지
        ext = src.suffix.lower()
        out_name = src.with_suffix(".jpg").name if ext == ".heic" else src.name
        dest = unique_path(self.watch / category / out_name)
        save_kwargs = {"exif": exif.tobytes()} if exif else {}
        # ICC 색상 프로파일 보존 (Adobe RGB 등 색공간 유지)
        icc = img.info.get("icc_profile")
        if icc:
            save_kwargs["icc_profile"] = icc
        if dest.suffix.lower() in (".jpg", ".jpeg"):
            img.convert("RGB").save(dest, "JPEG",
                                    quality=self.cfg["jpeg_quality"], **save_kwargs)
        else:
            img.save(dest, **save_kwargs)

        # 원본은 항상 originals/ 로 이동 보관 — 어떤 경우에도 삭제하지 않는다
        orig_dest = unique_path(self.watch / "originals" / src.name)
        shutil.move(str(src), str(orig_dest))

        log.info("%s → %s/  (blur=%.1f, faces=%d, min_EAR=%s)",
                 src.name, category, blur_value, len(faces),
                 f"{min_ear:.3f}" if min_ear is not None else "-")


# ---------------------------------------------------------------- 감시 (1단계)

class NewImageHandler(FileSystemEventHandler):
    def __init__(self, processor: PhotoProcessor):
        self.processor = processor
        self.watch = processor.watch

    def _maybe_process(self, path_str: str) -> None:
        path = Path(path_str)
        # 하위 분류 폴더 안의 파일(우리가 만든 결과물)은 무시
        if path.parent != self.watch or path.suffix.lower() not in IMAGE_EXTS:
            return
        try:
            self.processor.process(path)
        except Exception:
            log.exception("%s: 처리 중 오류", path.name)

    def on_created(self, event):
        if not event.is_directory:
            self._maybe_process(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._maybe_process(event.dest_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true",
                        help="기존 파일만 일괄 처리하고 종료")
    parser.add_argument("--config", default=None, help="config.yaml 경로")
    args = parser.parse_args()

    if already_running():
        if sys.stdout is not None:
            print("photo_sorter 가 이미 실행 중입니다. 종료합니다.")
        return

    config_path = Path(args.config) if args.config else Path(__file__).parent / "config.yaml"
    cfg = load_config(config_path)

    watch = Path(cfg["watch_folder"])
    watch.mkdir(parents=True, exist_ok=True)
    for sub in CATEGORIES:
        (watch / sub).mkdir(exist_ok=True)

    setup_logging(watch)
    log.info("감시 폴더: %s  (HEIC 지원: %s)", watch, HEIC_OK)

    processor = PhotoProcessor(cfg)

    # 시작 시 미처리 파일 일괄 처리
    pending = sorted(p for p in watch.iterdir()
                     if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    if pending:
        log.info("기존 미처리 파일 %d개 일괄 처리 시작", len(pending))
        for p in pending:
            try:
                processor.process(p)
            except Exception:
                log.exception("%s: 처리 중 오류", p.name)

    if args.once:
        log.info("--once 모드: 종료")
        return

    observer = Observer()
    observer.schedule(NewImageHandler(processor), str(watch), recursive=False)
    observer.start()
    log.info("폴더 감시 시작 (Ctrl+C 로 종료)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
