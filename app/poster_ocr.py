"""Hardened tour poster upload, magic-byte & Pillow CDR sanitization, sample poster generator, and Vision OCR."""

from __future__ import annotations

import base64
import datetime
import io
import logging
import os
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.parser import SHANGHAI_TZ
from app.security import safe_https_request

logger = logging.getLogger("concert_tracker.poster_ocr")

_RAPIDOCR_LOCK = threading.Lock()
_RAPIDOCR_ENGINE: Any = None
_RAPIDOCR_IMPORT_CHECKED = False
_RAPIDOCR_AVAILABLE = False

# Auto-discover optional isolated local OCR directory (<project>/.ocr_libs) if present
_LOCAL_OCR_LIBS = Path(__file__).resolve().parent.parent / ".ocr_libs"
if _LOCAL_OCR_LIBS.is_dir() and str(_LOCAL_OCR_LIBS) not in sys.path:
    sys.path.append(str(_LOCAL_OCR_LIBS))

# Decompression bomb protection (max 25 megapixels)
Image.MAX_IMAGE_PIXELS = 25_000_000
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB strict ceiling
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# TODO(security): Integrate an enterprise antivirus / sandbox malware scanner (e.g., ClamAV daemon) before
# persisting uploaded files in multi-tenant cloud deployments. Active content/EXIF is already stripped via
# pixel-level Content Disarm & Reconstruction (CDR) re-encoding below.


def _detect_magic_format(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def validate_and_sanitize_poster_upload(
    filename: str,
    raw_bytes: bytes,
    uploads_dir: Path,
) -> dict[str, Any]:
    """Validates extension, size, magic bytes, and Pillow structure; performs CDR pixel re-encode outside web root."""
    if not raw_bytes:
        raise ValueError("上传的图片内容为空。")
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError("海报图片大小超过 5MB 安全上限，请压缩后再上传。")

    ext = Path(os.path.basename(filename or "poster.png")).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("仅允许上传 PNG、JPG/JPEG 或 WEBP 格式的官宣海报。")

    magic_fmt = _detect_magic_format(raw_bytes)
    if not magic_fmt:
        raise ValueError("文件头魔数校验失败：该文件不是合法的 PNG/JPEG/WEBP 图像。")

    # Structural verification pass
    try:
        with Image.open(io.BytesIO(raw_bytes)) as probe_img:
            probe_img.verify()
    except Exception as exc:
        raise ValueError("图像结构损坏或格式异常，拒绝处理。") from exc

    # Second pass: decode pixels, read optional sample-poster text hint, and CDR re-encode clean RGB PNG
    embedded_schedule_hint = ""
    try:
        with Image.open(io.BytesIO(raw_bytes)) as src_img:
            if src_img.width > 5000 or src_img.height > 12000:
                raise ValueError("长图海报尺寸超出允许范围（最大 5000x12000 像素）。")
            raw_hint = src_img.info.get("liveecho_schedule", "")
            if isinstance(raw_hint, str) and len(raw_hint) <= 4000:
                embedded_schedule_hint = raw_hint

            rgb = src_img.convert("RGB")
            # Resize overly wide posters gently while preserving readability for long vertical posters
            if rgb.width > 1600:
                new_h = int(rgb.height * (1600 / rgb.width))
                rgb = rgb.resize((1600, max(1, new_h)), Image.Resampling.LANCZOS)

            # Construct brand-new clean image from raw RGB pixel bytes (strips 100% of EXIF, GPS, XMP, ICC, and polyglot trailers)
            clean_img = Image.frombytes("RGB", rgb.size, rgb.tobytes())

            clean_buf = io.BytesIO()
            clean_img.save(clean_buf, format="PNG", optimize=True)
            sanitized_png = clean_buf.getvalue()
            width, height = clean_img.size
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("图像像素重编码失败。") from exc

    uploads_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(uploads_dir, 0o700)
    except OSError:
        pass

    poster_uuid = uuid.uuid4().hex
    stored_name = f"{poster_uuid}.png"
    dest_path = (uploads_dir / stored_name).resolve()
    if not str(dest_path).startswith(str(uploads_dir.resolve()) + os.sep):
        raise ValueError("Invalid upload destination boundary.")

    fd = os.open(str(dest_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(sanitized_png)

    return {
        "poster_uuid": poster_uuid,
        "stored_filename": stored_name,
        "original_name": os.path.basename(filename or "poster.png")[:80],
        "sanitized_bytes": sanitized_png,
        "width": width,
        "height": height,
        "embedded_schedule_hint": embedded_schedule_hint,
    }


def extract_poster_text_via_gemini(sanitized_png: bytes, api_key: str) -> str:
    """Calls Gemini Vision over HTTPS using x-goog-api-key header (never URL query params) to transcribe tour posters."""
    clean_key = (api_key or "").strip()
    if not clean_key:
        return ""

    b64_img = base64.b64encode(sanitized_png).decode("ascii")
    prompt = (
        "请完整、准确地识别这张中国演唱会或音乐节官宣海报中的文字信息，并按纯文本逐行输出：\n"
        "1. 艺人/乐队名称与巡演或音乐节标题\n"
        "2. 每一站的城市、演出日期时间（如 2026年12月19日 19:30）、演出场馆\n"
        "3. 票价区间\n"
        "4. 优先购/一开/二开抢票时间与票务平台（大麦/猫眼/秀动/纷玩岛等）\n"
        "5. 阶梯退票截止时间规则（如有）\n"
        "只输出识别到的事实文本，不要添加额外寒暄。"
    )
    resp = safe_https_request(
        "POST",
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        headers={"x-goog-api-key": clean_key},
        json_body={
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/png", "data": b64_img}},
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1200},
        },
        timeout=15.0,
    )
    if resp.status_code >= 400:
        raise ValueError(f"Vision OCR 接口返回 HTTP {resp.status_code}，请检查 Vision API Key 是否有效。")
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    return "\n".join(str(p.get("text") or "") for p in parts if p.get("text")).strip()


def _load_cjk_or_default_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    font_candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for fp in font_candidates:
        if os.path.isfile(fp):
            try:
                return ImageFont.truetype(fp, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def generate_sample_tour_poster_png() -> bytes:
    """Generates a sample Chinese long tour poster PNG for zero-key instant testing of the poster upload pipeline."""
    from PIL.PngImagePlugin import PngInfo

    schedule_text = (
        "万能青年旅店 2026「冀西南林路行」冬季剧场巡演\n"
        "票价：¥380 / 580 / 780元\n"
        "优先购开启：2026年11月24日 11:18（秀动）\n"
        "正式开票时间：2026年11月25日 12:18（大麦）\n"
        "退票规则：2026年11月27日 12:18前无条件退票（0%手续费）\n"
        "退票规则：2026年12月05日 12:18前退票收取20%手续费\n"
        "2026年12月12日 19:30 石家庄 河北省艺术中心大剧院\n"
        "2026年12月19日 19:30 南京 江苏大剧院综艺厅\n"
        "2026年12月26日 19:30 广州 中山纪念堂\n"
        "https://www.showstart.com/"
    )

    img = Image.new("RGB", (680, 920), color=(246, 243, 236))
    draw = ImageDraw.Draw(img)

    # Editorial poster border & vermilion header block
    draw.rectangle([28, 28, 652, 892], outline=(25, 24, 22), width=3)
    draw.rectangle([28, 28, 652, 190], fill=(200, 55, 34))

    f_title = _load_cjk_or_default_font(28)
    f_sub = _load_cjk_or_default_font(19)
    f_body = _load_cjk_or_default_font(16)

    draw.text((52, 58), "LIVE ECHO POSTER SAMPLE", fill=(255, 245, 238), font=f_sub)
    draw.text((52, 102), "万能青年旅店 · 2026 冬季剧场巡演", fill=(255, 255, 255), font=f_title)

    y = 225
    for line in schedule_text.splitlines():
        draw.text((52, y), line, fill=(25, 24, 22), font=f_body)
        y += 52
        draw.line([(52, y - 14), (628, y - 14)], fill=(222, 215, 201), width=1)

    meta = PngInfo()
    meta.add_text("liveecho_schedule", schedule_text, zip=False)

    buf = io.BytesIO()
    img.save(buf, format="PNG", pnginfo=meta)
    return buf.getvalue()


_ALLOWED_TESSERACT_PATHS: tuple[str, ...] = ("/usr/bin/tesseract", "/usr/local/bin/tesseract")


def sanitize_festival_photo_in_memory(filename: str, raw_bytes: bytes) -> dict[str, Any]:
    """Validates and pixel-level CDR-sanitizes an uploaded festival timetable photo purely in memory (zero disk writes)."""
    if not raw_bytes:
        raise ValueError("上传的图片内容为空。")
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError("时刻表图片大小超过 5MB 安全上限，请压缩后再上传。")

    safe_name = os.path.basename(filename or "timetable.png")[:80]
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("仅允许上传 PNG、JPG/JPEG 或 WEBP 格式的时刻表照片。")

    magic_fmt = _detect_magic_format(raw_bytes)
    if not magic_fmt:
        raise ValueError("文件头魔数校验失败：该文件不是合法的 PNG/JPEG/WEBP 图像。")

    try:
        with Image.open(io.BytesIO(raw_bytes)) as probe_img:
            probe_img.verify()
    except Exception as exc:
        raise ValueError("图像结构损坏或格式异常，拒绝处理。") from exc

    embedded_schedule_hint = ""
    try:
        with Image.open(io.BytesIO(raw_bytes)) as src_img:
            if src_img.width > 5000 or src_img.height > 12000:
                raise ValueError("图片尺寸超出允许范围（最大 5000x12000 像素）。")
            raw_hint = src_img.info.get("liveecho_schedule", "")
            if isinstance(raw_hint, str) and len(raw_hint) <= 4000:
                embedded_schedule_hint = raw_hint

            rgb = src_img.convert("RGB")
            if rgb.width > 1600:
                new_h = int(rgb.height * (1600 / rgb.width))
                rgb = rgb.resize((1600, max(1, new_h)), Image.Resampling.LANCZOS)

            # Pixel-level CDR: strips 100% of EXIF, GPS, XMP, ICC, and polyglot trailers
            clean_img = Image.frombytes("RGB", rgb.size, rgb.tobytes())
            clean_buf = io.BytesIO()
            clean_img.save(clean_buf, format="PNG", optimize=True)
            sanitized_png = clean_buf.getvalue()
            width, height = clean_img.size
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("图像像素重编码失败。") from exc

    return {
        "original_name": safe_name,
        "sanitized_bytes": sanitized_png,
        "width": width,
        "height": height,
        "embedded_schedule_hint": embedded_schedule_hint,
    }


def extract_festival_timetable_via_gemini(
    sanitized_png: bytes,
    api_key: str,
    festival_name: str = "",
    default_date: str = "",
    known_bands: list[str] | None = None,
) -> str:
    """Calls Gemini Vision (x-goog-api-key header, never URL params) to extract stage-by-stage festival set times."""
    clean_key = (api_key or "").strip()
    if not clean_key:
        return ""

    b64_img = base64.b64encode(sanitized_png).decode("ascii")
    safe_fest = re.sub(r"[\r\n]+", " ", (festival_name or "").strip())[:80]
    safe_date = (default_date or "").strip()[:10]
    band_hints = [re.sub(r"[\r\n|]+", " ", str(b).strip())[:40] for b in (known_bands or [])[:40] if str(b).strip()]
    hint_block = (
        f"已知参考音乐节：{safe_fest or '音乐节'}；默认日期：{safe_date or '以图中日期为准'}。\n"
        + (f"该场已知参演艺人参考名单（请优先对齐准确拼写）：{'、'.join(band_hints)}\n" if band_hints else "")
    )
    prompt = (
        "你是一个严谨的中国音乐节演出时刻表识别助手。请从这张照片/海报中提取所有真实可见的「分舞台演出时刻表」。\n"
        + hint_block
        + "严格要求：\n"
        "1. 每组演出输出独立一行，格式必须为：YYYY-MM-DD | 舞台名 | 乐队或艺人名 | HH:MM-HH:MM\n"
        "2. 如果图中只写了月日（如 11月28日 / 11.28），请结合默认年份补全为 YYYY-MM-DD；如未标舞台名，请写 主舞台。\n"
        "3. 只输出图片中真实可见的文字与时间，严禁编造、补全或猜测图片里看不清/不存在的时段。\n"
        "4. 如果图片里没有具体的演出起止时间（例如只有阵容名单），请只输出：NO_TIMETABLE\n"
        "5. 不要输出 Markdown 代码块、解释或寒暄，直接逐行输出数据。"
    )

    resp = safe_https_request(
        "POST",
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        headers={"x-goog-api-key": clean_key},
        json_body={
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/png", "data": b64_img}},
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1800},
        },
        timeout=20.0,
    )
    if resp.status_code >= 400:
        raise ValueError(f"Vision OCR 接口返回 HTTP {resp.status_code}，请检查 Gemini Vision API Key 是否有效。")
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    return "\n".join(str(p.get("text") or "") for p in parts if p.get("text")).strip()


def try_local_tesseract_ocr(sanitized_png: bytes) -> str:
    """Optional offline OCR fallback using strictly allow-listed local tesseract binary paths (no shell)."""
    bin_path = next((p for p in _ALLOWED_TESSERACT_PATHS if os.path.isfile(p) and os.access(p, os.X_OK)), "")
    if not bin_path:
        return ""
    try:
        proc = subprocess.run(
            [bin_path, "stdin", "stdout", "--psm", "6", "-l", "chi_sim+eng"],
            input=sanitized_png,
            capture_output=True,
            timeout=12,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.decode("utf-8", errors="ignore").strip()
    except Exception:
        logger.warning("Local tesseract OCR invocation failed.")
    return ""


def parse_festival_timetable_lines(raw_text: str, default_date: str = "") -> list[dict[str, str]]:
    """Parses structured or semi-structured festival stage timetable lines into validated clash-ready slots."""
    clean_text = (raw_text or "").strip()
    if not clean_text or "NO_TIMETABLE" in clean_text.upper():
        return []

    fallback_date = (
        default_date
        if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", (default_date or "").strip())
        else datetime.datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d")
    )
    default_year = fallback_date[:4]
    current_date = fallback_date
    current_stage = "主舞台"
    slots: list[dict[str, str]] = []
    seen_keys: set[str] = set()

    for raw_line in clean_text.splitlines():
        line = raw_line.strip().strip("`")
        if not line:
            continue

        # Structured pipe format: YYYY-MM-DD | 舞台名 | 乐队 | HH:MM-HH:MM
        if line.count("|") >= 3:
            parts = [p.strip() for p in line.split("|")]
            dm = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", parts[0])
            tm = re.search(r"(\d{1,2})[:：](\d{2})\s*[-~—–至]\s*(\d{1,2})[:：](\d{2})", parts[3])
            if tm and parts[2]:
                d_str = (
                    f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
                    if dm
                    else current_date
                )
                current_date = d_str
                st = f"{int(tm.group(1)):02d}:{tm.group(2)}"
                en = f"{int(tm.group(3)):02d}:{tm.group(4)}"
                stage = (parts[1] or "主舞台")[:28]
                artist = parts[2][:48]
                dedup = f"{d_str}|{stage.lower()}|{artist.lower()}|{st}"
                if dedup not in seen_keys:
                    seen_keys.add(dedup)
                    slots.append(
                        {"artist": artist, "stage": stage, "day_date": d_str, "set_start": st, "set_end": en}
                    )
                continue

        # Flexible line format (date markers, stage headers, or free-form stage/artist/time)
        full_dm = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?", line)
        if full_dm:
            current_date = f"{full_dm.group(1)}-{int(full_dm.group(2)):02d}-{int(full_dm.group(3)):02d}"
        else:
            md_m = re.search(r"(?:^|\s|\[|【)(\d{1,2})(?:月|[./])(\d{1,2})日?(?:\s|\]|】|$)", line)
            if md_m:
                mo, dy = int(md_m.group(1)), int(md_m.group(2))
                if 1 <= mo <= 12 and 1 <= dy <= 31:
                    current_date = f"{default_year}-{mo:02d}-{dy:02d}"

        tm = re.search(r"(\d{1,2})[:：](\d{2})\s*[-~—–至]\s*(\d{1,2})[:：](\d{2})", line)
        if not tm:
            stage_hdr = re.search(r"([\u4e00-\u9fa5A-Za-z0-9·\s]{1,18}(?:舞台|STAGE|Stage|区|厅))", line)
            if stage_hdr:
                current_stage = re.sub(r"[【】\[\]：:]", "", stage_hdr.group(1)).strip()[:28] or current_stage
            continue

        st = f"{int(tm.group(1)):02d}:{tm.group(2)}"
        en = f"{int(tm.group(3)):02d}:{tm.group(4)}"
        rest = line.replace(tm.group(0), " ")
        rest = re.sub(r"20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?", " ", rest)
        rest = re.sub(r"(?:^|\s|\[|【)\d{1,2}(?:月|[./])\d{1,2}日?(?:\s|\]|】|$)", " ", rest)

        stage = current_stage
        inline_st = re.search(r"[【\[]?([\u4e00-\u9fa5A-Za-z0-9·]{1,16}(?:舞台|STAGE|Stage))[】\]：:]?", rest)
        if inline_st:
            stage = inline_st.group(1).strip()[:28]
            rest = rest.replace(inline_st.group(0), " ")

        artist = re.sub(r"\s+", " ", re.sub(r"^[|｜·•\-—:：\s]+|[|｜·•\-—:：\s]+$", "", rest)).strip()[:48]
        if not artist:
            continue
        dedup = f"{current_date}|{stage.lower()}|{artist.lower()}|{st}"
        if dedup not in seen_keys:
            seen_keys.add(dedup)
            slots.append(
                {"artist": artist, "stage": stage or "主舞台", "day_date": current_date, "set_start": st, "set_end": en}
            )
        if len(slots) >= 80:
            break

    return slots


def _get_rapidocr_engine() -> Any:
    """Lazy-loads local free RapidOCR (PP-OCRv6 ONNX) engine once per process if installed."""
    global _RAPIDOCR_ENGINE, _RAPIDOCR_IMPORT_CHECKED, _RAPIDOCR_AVAILABLE
    with _RAPIDOCR_LOCK:
        if _RAPIDOCR_ENGINE is not None:
            return _RAPIDOCR_ENGINE
        if _RAPIDOCR_IMPORT_CHECKED and not _RAPIDOCR_AVAILABLE:
            return None
        _RAPIDOCR_IMPORT_CHECKED = True
        try:
            from rapidocr import RapidOCR  # type: ignore[import-not-found]

            _RAPIDOCR_ENGINE = RapidOCR()
            _RAPIDOCR_AVAILABLE = True
            logger.info("Initialized local free RapidOCR engine successfully.")
            return _RAPIDOCR_ENGINE
        except Exception as exc:
            _RAPIDOCR_AVAILABLE = False
            logger.info("Local RapidOCR not installed or unavailable: %s", type(exc).__name__)
            return None


def is_local_ocr_available() -> bool:
    """Returns True if zero-key local OCR (RapidOCR or allow-listed Tesseract) is installed."""
    if _RAPIDOCR_AVAILABLE:
        return True
    try:
        import importlib.util

        if importlib.util.find_spec("rapidocr") is not None:
            return True
    except Exception:
        pass
    return any(os.path.isfile(p) and os.access(p, os.X_OK) for p in _ALLOWED_TESSERACT_PATHS)


def _run_rapidocr_boxes(sanitized_png: bytes) -> list[dict[str, Any]]:
    engine = _get_rapidocr_engine()
    if engine is None:
        return []
    try:
        with _RAPIDOCR_LOCK:
            res = engine(sanitized_png)
    except Exception as exc:
        logger.warning("Local RapidOCR inference error: %s", type(exc).__name__)
        return []

    boxes = getattr(res, "boxes", None)
    txts = getattr(res, "txts", None)
    scores = getattr(res, "scores", None)
    if boxes is None or txts is None:
        return []

    items: list[dict[str, Any]] = []
    for box, txt, sc in zip(boxes, txts, scores if scores is not None else [1.0] * len(txts)):
        clean = str(txt or "").strip()
        if not clean or float(sc) < 0.45:
            continue
        xs = [float(pt[0]) for pt in box]
        ys = [float(pt[1]) for pt in box]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        items.append(
            {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "cx": (x1 + x2) / 2.0,
                "cy": (y1 + y2) / 2.0,
                "h": max(8.0, y2 - y1),
                "text": clean,
                "score": float(sc),
            }
        )
    return items


def extract_general_text_via_rapidocr(sanitized_png: bytes) -> str:
    """Extracts reading-order lines from general concert tour posters using free local RapidOCR."""
    items = _run_rapidocr_boxes(sanitized_png)
    if not items:
        return ""
    items.sort(key=lambda it: (round(it["cy"] / 18.0), it["x1"]))
    lines: list[str] = []
    cur_y: float | None = None
    cur_row: list[dict[str, Any]] = []
    for it in items:
        if cur_y is None or abs(it["cy"] - cur_y) <= max(14.0, it["h"] * 0.65):
            cur_row.append(it)
            cur_y = it["cy"] if cur_y is None else (cur_y + it["cy"]) / 2.0
        else:
            cur_row.sort(key=lambda r: r["x1"])
            lines.append(" ".join(r["text"] for r in cur_row))
            cur_row = [it]
            cur_y = it["cy"]
    if cur_row:
        cur_row.sort(key=lambda r: r["x1"])
        lines.append(" ".join(r["text"] for r in cur_row))
    return "\n".join(lines).strip()


def _normalize_band_match_key(name: str) -> str:
    return re.sub(r"[\s\(\)（）【】\[\]·•\-—_:：/\\+★✓]+", "", (name or "").lower())


def _match_known_band(candidate: str, known_bands: list[str]) -> str:
    clean = (candidate or "").strip()
    if not clean or not known_bands:
        return clean
    ck = _normalize_band_match_key(clean)
    if not ck:
        return clean
    for kb in known_bands:
        kk = _normalize_band_match_key(kb)
        if kk and (ck == kk or (len(ck) >= 2 and (ck in kk or kk in ck))):
            return kb
    return clean


def extract_festival_timetable_via_rapidocr(
    sanitized_png: bytes,
    default_date: str = "",
    known_bands: list[str] | None = None,
) -> str:
    """2D spatial column/row parser on top of free local RapidOCR for multi-stage festival timetable posters."""
    items = _run_rapidocr_boxes(sanitized_png)
    if not items:
        return ""

    fallback_date = (
        default_date
        if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", (default_date or "").strip())
        else datetime.datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d")
    )
    default_year = fallback_date[:4]
    bands_ref = [str(b).strip() for b in (known_bands or []) if str(b).strip()]

    time_re = re.compile(r"(\d{1,2})[:：](\d{2})\s*[-~—–至]\s*(\d{1,2})[:：](\d{2})")
    stage_re = re.compile(r"([【\[]?[\u4e00-\u9fa5A-Za-z0-9·]{1,16}(?:舞台|STAGE|Stage|区|厅)[】\]]?)")
    full_date_re = re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?")
    md_date_re = re.compile(r"(?:^|\D)(\d{1,2})(?:月|[./])(\d{1,2})日?(?:\D|$)")

    date_boxes: list[dict[str, Any]] = []
    stage_boxes: list[dict[str, Any]] = []
    time_boxes: list[dict[str, Any]] = []
    other_boxes: list[dict[str, Any]] = []

    for it in items:
        txt = it["text"]
        has_time = bool(time_re.search(txt))
        fm = full_date_re.search(txt)
        mm = None if fm else md_date_re.search(txt)
        parsed_date = ""
        if fm:
            parsed_date = f"{fm.group(1)}-{int(fm.group(2)):02d}-{int(fm.group(3)):02d}"
        elif mm:
            mo, dy = int(mm.group(1)), int(mm.group(2))
            if 1 <= mo <= 12 and 1 <= dy <= 31:
                parsed_date = f"{default_year}-{mo:02d}-{dy:02d}"

        if parsed_date and not has_time:
            date_boxes.append({**it, "parsed_date": parsed_date})

        if has_time:
            time_boxes.append(it)
            continue

        st_m = stage_re.search(txt)
        if st_m and len(txt) <= 22:
            stage_name = re.sub(r"[【】\[\]：:\s]+", "", st_m.group(1))
            if stage_name:
                stage_boxes.append({**it, "stage_name": stage_name})
                continue

        if not parsed_date:
            other_boxes.append(it)

    structured_lines: list[str] = []
    used_other_ids: set[int] = set()

    for tb in sorted(time_boxes, key=lambda b: (b["cy"], b["cx"])):
        txt = tb["text"]
        tm = time_re.search(txt)
        if not tm:
            continue
        st_str = f"{int(tm.group(1)):02d}:{tm.group(2)}"
        en_str = f"{int(tm.group(3)):02d}:{tm.group(4)}"

        # 1) Active date: closest date header above (preferring horizontally aligned)
        day_date = fallback_date
        above_dates = [db for db in date_boxes if db["cy"] <= tb["cy"] + tb["h"]]
        if above_dates:
            best_d = min(above_dates, key=lambda db: abs(db["cx"] - tb["cx"]) * 0.6 + max(0.0, tb["cy"] - db["cy"]))
            day_date = best_d["parsed_date"]

        # 2) Stage & inline artist inside same OCR box
        rest = txt.replace(tm.group(0), " ")
        rest = full_date_re.sub(" ", rest)
        stage_name = ""
        inline_st = re.search(r"[【\[]?([\u4e00-\u9fa5A-Za-z0-9·]{1,16}(?:舞台|STAGE|Stage))[】\]：:]?", rest)
        if inline_st:
            stage_name = inline_st.group(1).strip()
            rest = rest.replace(inline_st.group(0), " ")

        if not stage_name:
            above_stages = [sb for sb in stage_boxes if sb["cy"] < tb["cy"] + 5]
            if above_stages:
                best_s = min(
                    above_stages,
                    key=lambda sb: abs(sb["cx"] - tb["cx"]) * 2.2 + max(0.0, tb["cy"] - sb["cy"]) * 0.25,
                )
                stage_name = best_s["stage_name"]
        if not stage_name:
            stage_name = "主舞台"

        artist = re.sub(r"\s+", " ", re.sub(r"^[|｜·•\-—:：\s]+|[|｜·•\-—:：\s]+$", "", rest)).strip()

        # 3) If artist wasn't inside the time box, pair nearest neighbor box in same row or same stage column
        if not artist:
            best_idx = -1
            best_dist = 1e9
            for idx, ob in enumerate(other_boxes):
                if idx in used_other_ids:
                    continue
                dy = abs(ob["cy"] - tb["cy"])
                dx_center = abs(ob["cx"] - tb["cx"])
                h_tol = max(tb["h"], ob["h"])
                # Same-row neighbor (right or left of time)
                horiz_gap = max(0.0, ob["x1"] - tb["x2"], tb["x1"] - ob["x2"])
                if dy <= h_tol * 0.95 and horiz_gap <= 260:
                    dist = dy * 2.0 + horiz_gap
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = idx
                # Stacked directly above/below in same column
                elif dx_center <= 150 and dy <= h_tol * 2.6:
                    dist = dy * 1.4 + dx_center * 0.8 + 40.0
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = idx
            if best_idx >= 0:
                used_other_ids.add(best_idx)
                artist = other_boxes[best_idx]["text"].strip()

        artist = _match_known_band(artist, bands_ref)
        if artist and not re.search(r"客服热线|检票|入场|退票|须知", artist):
            structured_lines.append(f"{day_date} | {stage_name} | {artist} | {st_str}-{en_str}")

    if structured_lines:
        return "\n".join(structured_lines)
    return extract_general_text_via_rapidocr(sanitized_png)
