import asyncio
import os
import subprocess
import json
import wave
import requests
import numpy as np
from pathlib import Path
import edge_tts
import imageio_ffmpeg
from dotenv import load_dotenv

# Load .env if present
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(r"f:\send bak\.env"))

BASE_DIR = Path(r"f:\send bak\سناریو\شماره_یک")
AUDIO_DIR = BASE_DIR / "assets" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
SAMPLE_RATE = 44100

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()

# Full Persian Diacritics (اعراب‌گذاری دقیق کلمه به کلمه جهت ادای آواشناسی صحیح و رفع رباتیک بودن)
SEGMENTS = [
    {
        "id": "seg1_hook",
        "voice_edge": "fa-IR-FaridNeural",
        "voice_eleven": "pNInz6obpgDQGcFmaJgB",  # Adam / Deep authoritative
        "rate": "+2%",
        "pitch": "-1Hz",
        "text": "ساعَتِ یازدَهِ شَبِه! فَردا مُمَیِّزیِ مالیاتی داری، و یِهو... سیستِمِ حِسابداریِ شِرکَت بالا نِمیاد! هاردِت سوخته و کُلِّ اِطّلاعاتِت قُفل شُده!",
        "pause_after": 0.22
    },
    {
        "id": "seg2_call",
        "voice_edge": "fa-IR-FaridNeural",
        "voice_eleven": "pNInz6obpgDQGcFmaJgB",
        "rate": "+3%",
        "pitch": "+0Hz",
        "text": "با اِستِرس زَنگ می‌زَنی بِه حِسابدار و می‌پُرسی: پَس فایْلِ بَک‌آپ کُجاست؟!",
        "pause_after": 0.15
    },
    {
        "id": "seg3_accountant",
        "voice_edge": "fa-IR-DilaraNeural",
        "voice_eleven": "21m00Tcm4TlvDq8ikWAM",  # Rachel / Female
        "rate": "+3%",
        "pitch": "+3Hz",
        "text": "وااای آقایِ مُدیر! فِلَشَم ویروسی شُده بود، این هَفته اصلاً یادَم رَفته بَک‌آپ بِگیرَم!",
        "pause_after": 0.22
    },
    {
        "id": "seg4a_question",
        "voice_edge": "fa-IR-FaridNeural",
        "voice_eleven": "pNInz6obpgDQGcFmaJgB",
        "rate": "+2%",
        "pitch": "-1Hz",
        "text": "یَعنی میلیاردها تومَن حِساب‌و‌کِتاب، دود شُد رَفت هَوا؟!",
        "pause_after": 0.20
    },
    {
        "id": "seg4b_hero",
        "voice_edge": "fa-IR-FaridNeural",
        "voice_eleven": "pNInz6obpgDQGcFmaJgB",
        "rate": "+2%",
        "pitch": "+1Hz",
        "text": "صَبر کُن! اَگِه یِه مُدیرِ هوشمَند باشی، اصلاً اِستِرس نِمی‌گیری! چون اَز قَبل، نَرم‌افزارِ اَکسیس پالْس رو رویِ سیستِمِت نَصب کَردی!",
        "pause_after": 0.25
    },
    {
        "id": "seg5_ui_demo",
        "voice_edge": "fa-IR-FaridNeural",
        "voice_eleven": "pNInz6obpgDQGcFmaJgB",
        "rate": "+3%",
        "pitch": "+0Hz",
        "text": "اَکسیس پالْس مِثلِ یِه نِگَهبانِ بیست و چهار ساعَته، پوشِه‌یِ بَک‌آپِ تو رو رَصَد می‌کُنه. بِه‌مَحضِ اینکه فایْلِ جَدید ساخته بِشه، بِدونِ نیاز بِه فیلتِرشِکَن و کاملاً خودکار، مُستَقیم می‌فرِستَتِش بِه گوشیِ خودِت، تویِ پَیام‌رَسانِ بَله!",
        "pause_after": 0.25
    },
    {
        "id": "seg6_features",
        "voice_edge": "fa-IR-FaridNeural",
        "voice_eleven": "pNInz6obpgDQGcFmaJgB",
        "rate": "+3%",
        "pitch": "+0Hz",
        "text": "حَتّی اَگه فایْلِت بالایِ بیست مِگابایْت باشه، خودِش فِشُرده و پارْت‌بَندی می‌کُنه و بِه سِه نَفَر هَم‌زَمان می‌فرِسته! بَرق برِه یا ویندوز ری‌استارْت بِشه؟ بازم خودِش اِتوماتیک بیدار میشه!",
        "pause_after": 0.25
    },
    {
        "id": "seg7_cta",
        "voice_edge": "fa-IR-FaridNeural",
        "voice_eleven": "pNInz6obpgDQGcFmaJgB",
        "rate": "+1%",
        "pitch": "+1Hz",
        "text": "اَمنیَّتِ کُلِّ کَسب‌وکارِت رو بِه شانس نَسْپار! هَمین الان کَلِمه‌یِ پالْس رو کامِنت کُن، تا لینکِ دانلُودِ مُستَقیمِ نَرم‌افزار بَرات دایرِکت بِشه!",
        "pause_after": 0.60
    }
]


def synthesize_elevenlabs(text: str, voice_id: str, out_wav: Path) -> bool:
    """Synthesizes text using ElevenLabs REST API with eleven_multilingual_v2."""
    if not ELEVENLABS_API_KEY:
        return False
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg"
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.58,
            "similarity_boost": 0.82,
            "style": 0.25,
            "use_speaker_boost": True
        }
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        if resp.status_code == 200:
            temp_mp3 = out_wav.with_suffix(".temp.mp3")
            temp_mp3.write_bytes(resp.content)
            subprocess.run([
                FFMPEG_EXE, "-y", "-i", str(temp_mp3),
                "-af", "silenceremove=start_periods=1:start_duration=0.03:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_duration=0.03:start_threshold=-45dB,areverse",
                "-ar", str(SAMPLE_RATE), "-ac", "1", str(out_wav)
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if temp_mp3.exists():
                temp_mp3.unlink()
            return True
        else:
            print(f"ElevenLabs API error ({resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        print(f"ElevenLabs request failed: {e}")
        return False


async def generate_tts_segments():
    use_eleven = bool(ELEVENLABS_API_KEY)
    if use_eleven:
        print("🌟 Using ElevenLabs Multilingual V2 Engine for Voiceover...")
    else:
        print("⚡ Using Edge-TTS Enhanced Natural Diacritics Engine...")

    for seg in SEGMENTS:
        wav_path = AUDIO_DIR / f"{seg['id']}.wav"
        success = False

        if use_eleven:
            success = synthesize_elevenlabs(seg["text"], seg["voice_eleven"], wav_path)

        if not success:
            mp3_path = AUDIO_DIR / f"{seg['id']}.mp3"
            communicate = edge_tts.Communicate(
                text=seg["text"],
                voice=seg["voice_edge"],
                rate=seg["rate"],
                pitch=seg["pitch"]
            )
            await communicate.save(str(mp3_path))
            subprocess.run([
                FFMPEG_EXE, "-y", "-i", str(mp3_path),
                "-af", "silenceremove=start_periods=1:start_duration=0.03:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_duration=0.03:start_threshold=-45dB,areverse",
                "-ar", str(SAMPLE_RATE), "-ac", "1", str(wav_path)
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        print(f"Generated {seg['id']}.wav (size: {wav_path.stat().st_size} bytes)")


def read_wav_mono(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        return data


def write_wav_stereo(path: Path, left: np.ndarray, right: np.ndarray):
    left_clip = np.clip(left, -0.98, 0.98)
    right_clip = np.clip(right, -0.98, 0.98)
    interleaved = np.empty((left_clip.size + right_clip.size,), dtype=np.int16)
    interleaved[0::2] = (left_clip * 32767).astype(np.int16)
    interleaved[1::2] = (right_clip * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(interleaved.tobytes())


def synth_error_alarm(duration=0.7) -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    tone = 0.35 * np.sin(2 * np.pi * 440 * t) + 0.35 * np.sin(2 * np.pi * 330 * t)
    env = np.exp(-3.5 * t)
    return tone * env


def synth_heartbeat(duration=3.5) -> np.ndarray:
    n = int(SAMPLE_RATE * duration)
    out = np.zeros(n, dtype=np.float32)
    beat_times = [0.1, 0.35, 1.1, 1.35, 2.1, 2.35, 3.0, 3.25]
    for bt in beat_times:
        start = int(bt * SAMPLE_RATE)
        blen = int(0.18 * SAMPLE_RATE)
        if start + blen < n:
            t = np.linspace(0, 0.18, blen, endpoint=False)
            thump = np.sin(2 * np.pi * 55 * t) * np.exp(-18 * t)
            out[start:start+blen] += 0.45 * thump
    return out


def synth_phone_ring(duration=0.6) -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    mod = np.sin(2 * np.pi * 20 * t) > 0
    ring = (0.25 * np.sin(2 * np.pi * 850 * t) + 0.25 * np.sin(2 * np.pi * 1020 * t)) * mod
    env = np.exp(-2.0 * t)
    return ring * env


def synth_magic_reveal(duration=1.1) -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    freqs = [523.25, 659.25, 783.99, 1046.50]
    out = np.zeros_like(t)
    for i, f in enumerate(freqs):
        delay = i * 0.08
        mask = t >= delay
        t_rel = np.maximum(0, t - delay)
        out += mask * 0.22 * np.sin(2 * np.pi * f * t_rel) * np.exp(-3.2 * t_rel)
    return out


def synth_bale_ding(duration=0.55) -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    n1 = (t < 0.12) * np.sin(2 * np.pi * 784 * t) * np.exp(-8 * t)
    t2 = np.maximum(0, t - 0.10)
    n2 = (t >= 0.10) * np.sin(2 * np.pi * 1174.66 * t2) * np.exp(-5.5 * t2)
    return 0.40 * (n1 + n2)


def synth_whoosh(duration=0.35) -> np.ndarray:
    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    sweep = np.sin(2 * np.pi * (180 + 400 * (t / duration)) * t)
    env = np.sin(np.pi * (t / duration)) ** 2
    return 0.22 * sweep * env


def synth_background_music(total_duration: float, twist_time: float) -> tuple[np.ndarray, np.ndarray]:
    n = int(SAMPLE_RATE * total_duration)
    t = np.linspace(0, total_duration, n, endpoint=False)

    mask_dark = np.clip((twist_time - t) / 0.4, 0.0, 1.0)
    pad_dark = (
        0.35 * np.sin(2 * np.pi * 110.0 * t) +
        0.25 * np.sin(2 * np.pi * 130.81 * t) +
        0.25 * np.sin(2 * np.pi * 164.81 * t)
    ) * (0.6 + 0.4 * np.sin(2 * np.pi * 2.0 * t))

    mask_bright = np.clip((t - twist_time + 0.2) / 0.5, 0.0, 1.0)
    pad_bright = (
        0.32 * np.sin(2 * np.pi * 130.81 * t) +
        0.25 * np.sin(2 * np.pi * 196.00 * t) +
        0.22 * np.sin(2 * np.pi * 246.94 * t) +
        0.20 * np.sin(2 * np.pi * 329.63 * t)
    )
    beat_pulse = 0.65 + 0.35 * (np.sin(2 * np.pi * 2.0 * t) ** 2)
    arp_freqs = [523.25, 659.25, 783.99, 987.77]
    step_idx = (np.floor(t * 4).astype(int)) % 4
    step_phase = (t * 4) % 1.0
    arp_freq = np.choose(step_idx, arp_freqs)
    arp = 0.14 * np.sin(2 * np.pi * arp_freq * t) * np.exp(-6.0 * step_phase)

    left = mask_dark * pad_dark * 0.075 + mask_bright * (pad_bright * beat_pulse + arp) * 0.08
    right = mask_dark * pad_dark * 0.075 + mask_bright * (pad_bright * beat_pulse + arp * 0.8) * 0.08

    fade_out = np.clip((total_duration - t) / 0.7, 0.0, 1.0)
    return left * fade_out, right * fade_out


def build_master_audio():
    asyncio.run(generate_tts_segments())

    timeline = []
    current_time = 0.25

    seg_arrays = []
    for seg in SEGMENTS:
        wav_path = AUDIO_DIR / f"{seg['id']}.wav"
        arr = read_wav_mono(wav_path)
        peak = np.max(np.abs(arr))
        if peak > 0:
            arr = arr / peak * 0.89
        dur = len(arr) / SAMPLE_RATE
        start_t = current_time
        end_t = start_t + dur
        timeline.append({
            "id": seg["id"],
            "text": seg["text"],
            "start": round(start_t, 3),
            "end": round(end_t, 3),
            "duration": round(dur, 3)
        })
        seg_arrays.append((start_t, arr))
        current_time = end_t + seg["pause_after"]

    total_duration = round(current_time + 0.4, 2)
    total_samples = int(total_duration * SAMPLE_RATE)

    voice_track = np.zeros(total_samples, dtype=np.float32)
    for start_t, arr in seg_arrays:
        idx = int(start_t * SAMPLE_RATE)
        end_idx = min(total_samples, idx + len(arr))
        voice_track[idx:end_idx] += arr[:end_idx - idx]

    seg4b_info = next(item for item in timeline if item["id"] == "seg4b_hero")
    twist_time = seg4b_info["start"]

    bg_left, bg_right = synth_background_music(total_duration, twist_time)
    sfx_track = np.zeros(total_samples, dtype=np.float32)

    def add_sfx(sfx_arr: np.ndarray, at_sec: float, gain: float = 1.0):
        idx = int(at_sec * SAMPLE_RATE)
        if idx < 0 or idx >= total_samples:
            return
        end_idx = min(total_samples, idx + len(sfx_arr))
        sfx_track[idx:end_idx] += sfx_arr[:end_idx - idx] * gain

    add_sfx(synth_error_alarm(0.7), 0.05, 0.45)
    add_sfx(synth_heartbeat(3.8), 0.4, 0.38)
    seg2_info = next(item for item in timeline if item["id"] == "seg2_call")
    add_sfx(synth_phone_ring(0.55), seg2_info["start"] + 0.05, 0.30)
    add_sfx(synth_magic_reveal(1.1), twist_time - 0.05, 0.58)
    seg5_info = next(item for item in timeline if item["id"] == "seg5_ui_demo")
    add_sfx(synth_whoosh(0.35), seg5_info["start"] - 0.12, 0.50)
    add_sfx(synth_bale_ding(0.55), seg5_info["end"] - 1.1, 0.65)
    seg6_info = next(item for item in timeline if item["id"] == "seg6_features")
    add_sfx(synth_bale_ding(0.55), seg6_info["start"] + 1.8, 0.55)
    seg7_info = next(item for item in timeline if item["id"] == "seg7_cta")
    add_sfx(synth_whoosh(0.35), seg7_info["start"] - 0.12, 0.50)
    add_sfx(synth_bale_ding(0.55), seg7_info["start"] + 1.9, 0.60)

    master_left = voice_track + bg_left + sfx_track * 0.45
    master_right = voice_track + bg_right + sfx_track * 0.45

    master_wav = AUDIO_DIR / "master_audio.wav"
    write_wav_stereo(master_wav, master_left, master_right)

    meta = {
        "total_duration": total_duration,
        "twist_time": round(twist_time, 3),
        "segments": timeline
    }
    meta_path = AUDIO_DIR / "timeline.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"Master audio built successfully! Total duration: {total_duration}s")
    for item in timeline:
        print(f"  {item['id']}: {item['start']}s -> {item['end']}s ({item['duration']}s)")


if __name__ == "__main__":
    build_master_audio()
