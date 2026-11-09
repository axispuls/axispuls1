import os
import shutil
import zipfile
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Tuple

# 20 Megabytes in bytes
MAX_SINGLE_FILE_SIZE = 20 * 1024 * 1024

# 10 Megabytes in bytes (optimized for network stability, preventing upload timeouts on slow connections)
DEFAULT_PART_SIZE = 10 * 1024 * 1024

# Dynamic speed thresholds (0.5 MB/s threshold)
SPEED_THRESHOLD_BYTES = 512 * 1024  # 0.5 MB/s (512 KB/s)
PART_SIZE_SLOW = 10 * 1024 * 1024   # 10 MB parts when upload speed < 0.5 MB/s
PART_SIZE_FAST = 20 * 1024 * 1024   # 20 MB parts when upload speed >= 0.5 MB/s

def get_adaptive_part_size(current_speed_bps: float) -> int:
    """
    Determines optimal part size based on upload speed:
    - Under 0.5 MB/s -> 10 MB parts for network reliability
    - 0.5 MB/s or higher -> 20 MB parts for faster high-throughput delivery
    """
    if current_speed_bps < SPEED_THRESHOLD_BYTES:
        return PART_SIZE_SLOW
    return PART_SIZE_FAST

def format_file_size(size_in_bytes: int) -> str:
    """Formats raw bytes into a human-readable Persian size string."""
    if size_in_bytes < 1024:
        return f"{size_in_bytes} بایت"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.1f} کیلوبایت"
    elif size_in_bytes < 1024 * 1024 * 1024:
        return f"{size_in_bytes / (1024 * 1024):.1f} مگابایت"
    else:
        return f"{size_in_bytes / (1024 * 1024 * 1024):.2f} گیگابایت"

def calculate_sha256(file_path: str) -> str:
    """Calculates SHA256 hash of a file for integrity verification."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()

def create_zip_archive(
    source_file_path: str,
    target_zip_path: str,
    compression_method: str = "deflate_max"
) -> str:
    """
    Creates a high-compression zip archive containing the source file.
    - 'deflate_max': Standard Deflate with Level 9 (100% universal compatibility across all OS/apps).
    - 'lzma_ultra': 7-Zip LZMA compression inside ZIP for maximum byte reduction (WinRAR & 7-Zip).
    """
    file_name = os.path.basename(source_file_path)
    if compression_method == "lzma_ultra":
        with zipfile.ZipFile(target_zip_path, 'w', compression=zipfile.ZIP_LZMA) as zf:
            zf.write(source_file_path, arcname=file_name)
    else:
        with zipfile.ZipFile(target_zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            zf.write(source_file_path, arcname=file_name)
    return target_zip_path

def split_file_into_parts(source_path: str, output_dir: str, part_size: int = DEFAULT_PART_SIZE) -> List[str]:
    """
    Splits any file into sequential parts (.001, .002, .003, ...) of max part_size bytes.
    This format is the universal standard recognized by 7-Zip, WinRAR, and PeaZip.
    """
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.basename(source_path)
    part_paths = []
    part_num = 1

    with open(source_path, "rb") as src:
        while True:
            chunk = src.read(part_size)
            if not chunk:
                break
            part_filename = f"{base_name}.{part_num:03d}"
            part_filepath = os.path.join(output_dir, part_filename)
            with open(part_filepath, "wb") as dst:
                dst.write(chunk)
            part_paths.append(part_filepath)
            part_num += 1

    return part_paths

def reassemble_split_parts(part_paths: List[str], output_path: str) -> str:
    """
    Reassembles split parts back into the original single file.
    Useful for testing, automated verification, or extraction.
    """
    # Sort parts by extension/filename to guarantee order
    sorted_parts = sorted(part_paths)
    with open(output_path, "wb") as dst:
        for part_path in sorted_parts:
            with open(part_path, "rb") as src:
                shutil.copyfileobj(src, dst)
    return output_path

def prepare_file_for_sending(
    file_path: str,
    temp_dir: str,
    max_size: int = MAX_SINGLE_FILE_SIZE,
    part_size: int = DEFAULT_PART_SIZE,
    compression_method: str = "deflate_max",
    auto_compress_all: bool = False
) -> Dict[str, Any]:
    """
    Inspects file size and applies intelligent high-compression:
    - If auto_compress_all is True: Compresses even files <= 20 MB (unless already an archive)
      to drastically reduce upload size and save internet data.
    - If > 20 MB: Creates a high-compression zip (Deflate Level 9 or LZMA Ultra).
      If zip <= 20MB, sends as 1 single zip.
      If zip > 20MB, splits it into multi-part zip archives (.zip.001, .zip.002, ...)
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"فایل یافت نشد: {file_path}")

    orig_size = os.path.getsize(file_path)
    orig_name = os.path.basename(file_path)
    ext = os.path.splitext(file_path)[1].lower()
    is_already_archive = ext in {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.zst'}

    # 1. Handle 0-byte (empty) files:
    if orig_size == 0:
        os.makedirs(temp_dir, exist_ok=True)
        zip_path = os.path.join(temp_dir, f"{orig_name}.zip")
        create_zip_archive(file_path, zip_path, compression_method=compression_method)
        zip_size = os.path.getsize(zip_path)
        return {
            "is_split": False,
            "was_compressed": True,
            "original_name": orig_name,
            "original_size": 0,
            "parts": [{
                "path": zip_path,
                "filename": f"{orig_name}.zip",
                "size": zip_size,
                "readable_size": format_file_size(zip_size),
                "part_number": 1,
                "total_parts": 1,
                "caption_note": "💡 این فایل خالی (۰ بایت) بود؛ جهت تطابق با سرورهای بله در قالب زیپ ارسال شد."
            }]
        }

    # 2. Check if file should be compressed:
    # Files > 20MB are ALWAYS compressed.
    # Files <= 20MB are compressed only if auto_compress_all is enabled and not already an archive.
    should_compress = (orig_size > max_size) or (auto_compress_all and not is_already_archive)

    if not should_compress:
        return {
            "is_split": False,
            "was_compressed": False,
            "original_name": orig_name,
            "original_size": orig_size,
            "parts": [{
                "path": file_path,
                "filename": orig_name,
                "size": orig_size,
                "readable_size": format_file_size(orig_size),
                "part_number": 1,
                "total_parts": 1,
                "caption_note": ""
            }]
        }

    # 3. Create high-compression zip
    os.makedirs(temp_dir, exist_ok=True)
    zip_path = os.path.join(temp_dir, f"{orig_name}.zip")
    create_zip_archive(file_path, zip_path, compression_method=compression_method)
    zip_size = os.path.getsize(zip_path)

    # If compression did not reduce size (e.g. video/already compressed) and original size is <= max_size:
    if zip_size >= orig_size and orig_size <= max_size:
        return {
            "is_split": False,
            "was_compressed": False,
            "original_name": orig_name,
            "original_size": orig_size,
            "parts": [{
                "path": file_path,
                "filename": orig_name,
                "size": orig_size,
                "readable_size": format_file_size(orig_size),
                "part_number": 1,
                "total_parts": 1,
                "caption_note": ""
            }]
        }

    reduction_pct = max(0, int((1 - (zip_size / orig_size)) * 100)) if orig_size > 0 else 0
    mode_title = "حداکثر (Deflate 9)" if compression_method != "lzma_ultra" else "فوق‌العاده (LZMA Ultra)"

    # If compression brought it under max_size, send single zip
    if zip_size <= max_size:
        note_parts = [f"⚡ فایل با الگوریتم {mode_title} فشرده‌سازی شد."]
        if reduction_pct > 0:
            note_parts.append(f"📉 کاهش حجم: {reduction_pct}٪ صرفه‌جویی در مصرف اینترنت و زمان ارسال.")
        return {
            "is_split": False,
            "was_compressed": True,
            "original_name": orig_name,
            "original_size": orig_size,
            "parts": [{
                "path": zip_path,
                "filename": os.path.basename(zip_path),
                "size": zip_size,
                "readable_size": format_file_size(zip_size),
                "part_number": 1,
                "total_parts": 1,
                "caption_note": "\n".join(note_parts)
            }]
        }

    # 4. Zipped file is still > 20 MB: split into multi-part zip
    part_paths = split_file_into_parts(zip_path, temp_dir, part_size=part_size)
    total_parts = len(part_paths)

    parts_list = []
    for idx, p_path in enumerate(part_paths, start=1):
        p_name = os.path.basename(p_path)
        p_size = os.path.getsize(p_path)
        note = (
            f"📦 پارت {idx} از {total_parts} (فایل چندبخشی زیپ با فشرده‌سازی {mode_title})\n"
            f"📉 کاهش حجم کل: {reduction_pct}٪ | حجم اصلی: {format_file_size(orig_size)}\n"
            f"💡 راهنما: برای استخراج، تمام پارت‌ها را در یک پوشه قرار داده و پارت 001 را با WinRAR یا 7-Zip باز کنید."
        )
        parts_list.append({
            "path": p_path,
            "filename": p_name,
            "size": p_size,
            "readable_size": format_file_size(p_size),
            "part_number": idx,
            "total_parts": total_parts,
            "caption_note": note
        })

    return {
        "is_split": True,
        "was_compressed": True,
        "original_name": orig_name,
        "original_size": orig_size,
        "parts": parts_list
    }

def extract_executable_from_zip(zip_path: str, target_dir: str) -> Optional[str]:
    """
    Inspects a zip file and extracts any executable (.exe) inside it to target_dir.
    Returns the full path of the extracted .exe file, or None if none found.
    """
    os.makedirs(target_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            names = zf.namelist()
            exe_names = [n for n in names if n.lower().endswith(".exe")]
            if exe_names:
                target_exe = exe_names[0]
                zf.extract(target_exe, target_dir)
                extracted_path = os.path.join(target_dir, target_exe)
                return extracted_path
    except Exception:
        pass
    return None

