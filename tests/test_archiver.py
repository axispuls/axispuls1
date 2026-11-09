import os
import shutil
import zipfile
import pytest
from pathlib import Path
from core.archiver import (
    prepare_file_for_sending,
    create_zip_archive,
    split_file_into_parts,
    reassemble_split_parts,
    calculate_sha256,
    MAX_SINGLE_FILE_SIZE
)

@pytest.fixture
def temp_test_env(tmp_path):
    src_dir = tmp_path / "source"
    src_dir.mkdir()
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    return src_dir, out_dir

def test_file_under_20mb_not_split(temp_test_env):
    """Files <= 20 MB must not be split and sent directly."""
    src_dir, out_dir = temp_test_env
    test_file = src_dir / "small_doc.pdf"
    test_file.write_bytes(b"A" * (1024 * 500))  # 500 KB

    result = prepare_file_for_sending(str(test_file), str(out_dir))
    assert result["is_split"] is False
    assert result["was_compressed"] is False
    assert len(result["parts"]) == 1
    assert result["parts"][0]["path"] == str(test_file)
    assert result["parts"][0]["size"] == 1024 * 500

def test_file_over_20mb_split_and_reassembly(temp_test_env):
    """
    Files > 20 MB must be compressed and split into sequential parts (.001, .002).
    Reassembling parts must yield the exact zip with identical hash.
    """
    src_dir, out_dir = temp_test_env
    test_file = src_dir / "large_backup.bin"
    
    # Generate random-like non-compressible data to guarantee size remains > 20MB after compression
    data = os.urandom(22 * 1024 * 1024)  # 22 MB
    test_file.write_bytes(data)
    original_sha256 = calculate_sha256(str(test_file))

    # Split using small custom part size for fast, thorough test (e.g. 5 MB)
    custom_max = 10 * 1024 * 1024       # 10 MB limit for test
    custom_part = 5 * 1024 * 1024       # 5 MB parts

    result = prepare_file_for_sending(
        str(test_file),
        str(out_dir),
        max_size=custom_max,
        part_size=custom_part
    )

    assert result["is_split"] is True
    assert result["was_compressed"] is True
    parts = result["parts"]
    assert len(parts) >= 2

    # Check naming conventions (.001, .002, ...)
    for idx, p in enumerate(parts, start=1):
        assert p["filename"].endswith(f".{idx:03d}")
        assert os.path.exists(p["path"])
        assert p["size"] <= custom_part

    # Reassemble parts
    reassembled_zip = out_dir / "reassembled.zip"
    part_paths = [p["path"] for p in parts]
    reassemble_split_parts(part_paths, str(reassembled_zip))
    assert reassembled_zip.exists()

    # Extract reassembled zip and check original file contents
    extract_dir = out_dir / "extracted"
    extract_dir.mkdir()
    with zipfile.ZipFile(str(reassembled_zip), "r") as zf:
        zf.extractall(str(extract_dir))

    extracted_file = extract_dir / "large_backup.bin"
    assert extracted_file.exists()
    assert calculate_sha256(str(extracted_file)) == original_sha256

def test_boundary_exact_20mb(temp_test_env):
    """A file of exactly 20 MB (20 * 1024 * 1024 bytes) must not be split."""
    src_dir, out_dir = temp_test_env
    test_file = src_dir / "exact_20mb.dat"
    test_file.write_bytes(b"B" * 1024)

    # Test with exact max limit
    result = prepare_file_for_sending(str(test_file), str(out_dir), max_size=1024)
    assert result["is_split"] is False

    # Now 1025 bytes (1 byte over)
    test_file_over = src_dir / "over_limit.dat"
    test_file_over.write_bytes(b"C" * 1025)
    result_over = prepare_file_for_sending(str(test_file_over), str(out_dir), max_size=1024, part_size=600)
    # Since compressible data of 1025 bytes zips to < 100 bytes, was_compressed becomes True
    assert result_over["was_compressed"] is True

def test_nonexistent_file_raises_error(temp_test_env):
    """Attempting to prepare a nonexistent file must raise FileNotFoundError."""
    src_dir, out_dir = temp_test_env
    non_file = src_dir / "ghost_file.txt"
    with pytest.raises(FileNotFoundError):
        prepare_file_for_sending(str(non_file), str(out_dir))

def test_empty_0byte_file_zipped(temp_test_env):
    """0-byte files must be packaged into a zip so Bale does not reject them with 413."""
    src_dir, out_dir = temp_test_env
    empty_file = src_dir / "empty.txt"
    empty_file.write_bytes(b"")

    result = prepare_file_for_sending(str(empty_file), str(out_dir))
    assert result["is_split"] is False
    assert result["was_compressed"] is True
    assert len(result["parts"]) == 1
    part = result["parts"][0]
    assert part["filename"].endswith(".zip")
    assert part["size"] > 0
    assert os.path.exists(part["path"])

def test_lzma_ultra_compression(temp_test_env):
    """Verifies that LZMA ultra compression produces a valid archive with extreme reduction."""
    src_dir, out_dir = temp_test_env
    large_doc = src_dir / "database_export.sql"
    large_doc.write_bytes(b"INSERT INTO records VALUES ('Alice', 100);\n" * 5000)

    zip_lzma = out_dir / "compressed_lzma.zip"
    create_zip_archive(str(large_doc), str(zip_lzma), compression_method="lzma_ultra")
    assert zip_lzma.exists()
    assert os.path.getsize(str(zip_lzma)) < os.path.getsize(str(large_doc)) * 0.1  # More than 90% reduction

    # Verify integrity by extracting
    with zipfile.ZipFile(str(zip_lzma), "r") as zf:
        extracted_content = zf.read("database_export.sql")
        assert extracted_content == large_doc.read_bytes()

def test_auto_compress_all_small_file(temp_test_env):
    """When auto_compress_all=True, even small files under 20MB are compressed to save data."""
    src_dir, out_dir = temp_test_env
    small_doc = src_dir / "financials.csv"
    small_doc.write_bytes(b"Year,Q1,Q2,Q3,Q4\n2026,100,200,300,400\n" * 200)

    result = prepare_file_for_sending(
        str(small_doc),
        str(out_dir),
        auto_compress_all=True
    )
    assert result["was_compressed"] is True
    assert result["parts"][0]["filename"] == "financials.csv.zip"
    assert result["parts"][0]["size"] < os.path.getsize(str(small_doc))

def test_adaptive_part_size_thresholds():
    """
    Tests speed-based dynamic part sizing:
    - Speed < 0.5 MB/s (512 KB/s) -> 10 MB parts
    - Speed >= 0.5 MB/s -> 20 MB parts
    """
    from core.archiver import get_adaptive_part_size, PART_SIZE_SLOW, PART_SIZE_FAST

    # Slow connection: 300 KB/s (< 0.5 MB/s)
    slow_speed = 300 * 1024
    assert get_adaptive_part_size(slow_speed) == PART_SIZE_SLOW
    assert get_adaptive_part_size(slow_speed) == 10 * 1024 * 1024

    # Borderline 0.49 MB/s
    assert get_adaptive_part_size(500 * 1024) == PART_SIZE_SLOW

    # Fast connection: 0.5 MB/s exactly (512 KB/s)
    fast_speed_min = 512 * 1024
    assert get_adaptive_part_size(fast_speed_min) == PART_SIZE_FAST
    assert get_adaptive_part_size(fast_speed_min) == 20 * 1024 * 1024

    # High-speed connection: 5 MB/s
    high_speed = 5 * 1024 * 1024
    assert get_adaptive_part_size(high_speed) == PART_SIZE_FAST

