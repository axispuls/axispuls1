import os
import sys
import subprocess
from pathlib import Path
import imageio_ffmpeg

BASE_DIR = Path(r"f:\send bak\سناریو\شماره_یک")
AUDIO_DIR = BASE_DIR / "assets" / "audio"
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

VIDEO_INPUT = BASE_DIR / "01_کلیپ_سناریو_اول_مخصوص_صداگذاری.mp4"
SFX_MUSIC_TRACK = AUDIO_DIR / "sfx_and_music_master.wav"
FINAL_OUTPUT = BASE_DIR / "01_کلیپ_نهایی_با_صدای_شما.mp4"

def find_user_voice_file() -> Path | None:
    # 1. Check command-line argument if passed
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        if p.exists():
            return p

    # 2. Search common voice recording names in folder
    candidates = [
        "my_voice.mp3", "my_voice.wav", "my_voice.m4a", "my_voice.ogg",
        "voice.mp3", "voice.wav", "voice.m4a", "voice.ogg",
        "record.mp3", "record.wav", "record.m4a",
        "صدای_من.mp3", "صدای_من.wav", "صدای_من.m4a"
    ]
    for c in candidates:
        target = BASE_DIR / c
        if target.exists():
            return target

    # 3. Check any audio file in folder that isn't the master files
    for f in BASE_DIR.glob("*.*"):
        if f.suffix.lower() in [".mp3", ".wav", ".m4a", ".aac", ".ogg"] and not f.name.startswith("01_"):
            return f

    return None

def merge():
    print("=" * 60)
    print("🎬 ابزار هوشمند ترکیب صدای ضبط‌شده شما با کلیپ اکسیس پالس")
    print("=" * 60)

    voice_path = find_user_voice_file()
    if not voice_path:
        print("\n❌ هیچ فایل صوتی ضبط‌شده‌ای در پوشه پیدا نشد!")
        print("💡 راهنما:")
        print("۱. ویس ضبط‌شده خودتان با موبایل یا میکروفون را با نام my_voice.mp3 در پوشه زیر بگذارید:")
        print(f"   {BASE_DIR}")
        print("۲. سپس مجدداً این دستور را اجرا کنید:")
        print("   python merge_voice.py")
        print("   یا نام فایل را مستقیم به دستور بدهید: python merge_voice.py your_audio.m4a\n")
        return

    print(f"✅ فایل صدای شما شناسایی شد: {voice_path.name}")
    print("⏳ در حال نرمال‌سازی صدا، اعمال داکینگ موزیک (Ducking) و رندر ویدیوی نهایی...")

    # FFmpeg complex filter:
    # [1:a] loudnorm -> normalized clear human voice
    # [2:a] sfx_music -> sidechain compressed by voice (ducks 5dB when you talk)
    # amix -> balanced stereo master
    filter_complex = (
        "[1:a]loudnorm=I=-15:LRA=7:tp=-1.0[voice_norm];"
        "[2:a][voice_norm]sidechaincompress=threshold=0.08:ratio=4:attack=20:release=250[bg_ducked];"
        "[voice_norm][bg_ducked]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )

    cmd = [
        FFMPEG_EXE, "-y",
        "-i", str(VIDEO_INPUT),
        "-i", str(voice_path),
        "-i", str(SFX_MUSIC_TRACK),
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "256k",
        "-shortest",
        str(FINAL_OUTPUT)
    ]

    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if res.returncode == 0:
        print("\n" + "🎉" * 25)
        print(f"✅ ویدیوی نهایی با صدای شما با موفقیت ساخته شد!")
        print(f"📁 مسیر فایل آماده انتشار:")
        print(f"   {FINAL_OUTPUT}")
        print("🎉" * 25 + "\n")
    else:
        err = res.stderr.decode("utf-8", errors="ignore")
        print(f"❌ خطا در ترکیب صدا:\n{err}")

if __name__ == "__main__":
    merge()
