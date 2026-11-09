import json
import wave
from pathlib import Path
import numpy as np

BASE_DIR = Path(r"f:\send bak\سناریو\شماره_یک")
AUDIO_DIR = BASE_DIR / "assets" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_RATE = 44100

# Timing markers for 48-second high-energy Reel
TIMELINE = {
    "total_duration": 48.0,
    "scenes": [
        {
            "id": "scene1_hook",
            "start": 0.0,
            "end": 7.2,
            "title": "ساعت ۱۱ شب و خطای بحرانی هارد",
            "guide_text": "ساعت ۱۱ شبه! فردا ممیزی مالیاتی داری و یهو... سیستم حسابداری شرکت بالا نمیاد! هاردت سوخته و کل اطلاعاتت قفل شده!"
        },
        {
            "id": "scene2_call",
            "start": 7.2,
            "end": 15.0,
            "title": "تماس اضطراری با حسابدار و بهانه‌ها",
            "guide_text": "با استرس زنگ می‌زنی به حسابدار: پس فایل بکاپ کجاست؟! — خانم رضایی: واای آقای مدیر، فلشم ویروسی شده بود، این هفته اصلاً یادم رفته بکاپ بگیرم!"
        },
        {
            "id": "scene3_twist",
            "start": 15.0,
            "end": 22.8,
            "title": "شوک مالی و نقطه عطف: اکسیس پالس",
            "guide_text": "یعنی میلیاردها تومن حساب و کتاب پرید؟! صبر کن! اگه یه مدیر هوشمند باشی اصلاً استرس نمی‌گیری! چون از قبل، اکسیس پالس رو نصب کردی!"
        },
        {
            "id": "scene4_ui_demo",
            "start": 22.8,
            "end": 33.0,
            "title": "نمایش محیط برنامه اکسیس پالس و پایش خودکار",
            "guide_text": "اکسیس پالس مثل یه نگهبان ۲۴ ساعته، پوشه بکاپت رو رصد می‌کنه و به محض ساخت فایل جدید، بدون نیاز به فیلترشکن، مستقیم می‌فرستتش به پیام‌رسان بله!"
        },
        {
            "id": "scene5_features",
            "start": 33.0,
            "end": 41.2,
            "title": "پارت‌بندی بالای ۲۰ مگابایت و فعال ماندن دائمی",
            "guide_text": "حتی اگه فایلت بالای ۲۰ مگابایت باشه، خودکار زیپ و پارت‌بندی می‌کنه و به ۳ نفر همزمان می‌فرسته! برق بره یا ویندوز ری‌استارت بشه؟ بازم خودکار بیدار میشه!"
        },
        {
            "id": "scene6_cta",
            "start": 41.2,
            "end": 48.0,
            "title": "دعوت به اقدام و کامنت کلمه پالس",
            "guide_text": "امنیت کسب‌وکارت رو به شانس نسپار! همین الان کلمه «پالس» رو کامنت کن تا لینک دانلود مستقیم برات دایرکت بشه!"
        }
    ]
}


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


def make_sfx_and_music():
    total_dur = TIMELINE["total_duration"]
    n_samples = int(total_dur * SAMPLE_RATE)
    t = np.linspace(0, total_dur, n_samples, endpoint=False)

    sfx_left = np.zeros(n_samples, dtype=np.float32)
    sfx_right = np.zeros(n_samples, dtype=np.float32)

    def add_stereo(s_left, s_right, at_time, gain=1.0):
        idx = int(at_time * SAMPLE_RATE)
        l_len = len(s_left)
        if idx >= n_samples:
            return
        end_idx = min(n_samples, idx + l_len)
        chunk_len = end_idx - idx
        sfx_left[idx:end_idx] += s_left[:chunk_len] * gain
        sfx_right[idx:end_idx] += s_right[:chunk_len] * gain

    def add_mono(s_mono, at_time, gain=1.0, pan=0.0):
        # pan: -1.0 (full left) to 1.0 (full right)
        g_l = gain * (1.0 - pan) * 0.707
        g_r = gain * (1.0 + pan) * 0.707
        add_stereo(s_mono * g_l, s_mono * g_r, at_time, gain=1.0)

    # 1. Heartbeat thump (Double beat)
    def sfx_heartbeat_single(duration=0.22, freq=58):
        dur_samples = int(duration * SAMPLE_RATE)
        st = np.linspace(0, duration, dur_samples, endpoint=False)
        sub = np.sin(2 * np.pi * freq * st) * np.exp(-16 * st)
        thud = np.sin(2 * np.pi * (freq * 0.5) * st) * np.exp(-12 * st)
        return sub * 0.7 + thud * 0.3

    for hb_time in [0.4, 0.7, 2.0, 2.3, 3.8, 4.1, 5.5, 5.8]:
        hb = sfx_heartbeat_single()
        add_mono(hb, hb_time, gain=0.65)

    # 2. Windows Error / Disk Failure Stinger (0.15s)
    st = np.linspace(0, 0.75, int(0.75 * SAMPLE_RATE), endpoint=False)
    chord = (
        0.4 * np.sin(2 * np.pi * 440 * st) +
        0.4 * np.sin(2 * np.pi * 330 * st) +
        0.2 * np.sin(2 * np.pi * 220 * st)
    ) * np.exp(-4.2 * st)
    add_mono(chord, 0.15, gain=0.85)

    # Glitch buzz (1.8s)
    st_g = np.linspace(0, 0.35, int(0.35 * SAMPLE_RATE), endpoint=False)
    glitch = np.sign(np.sin(2 * np.pi * 180 * st_g)) * (np.sin(2 * np.pi * 60 * st_g) ** 2) * 0.35
    add_mono(glitch, 1.8, gain=0.55, pan=-0.3)

    # 3. Phone Ringing & Click (7.3s)
    st_ring = np.linspace(0, 0.65, int(0.65 * SAMPLE_RATE), endpoint=False)
    ring_sig = (0.28 * np.sin(2 * np.pi * 850 * st_ring) + 0.28 * np.sin(2 * np.pi * 1020 * st_ring)) * (np.sin(2 * np.pi * 22 * st_ring) > 0)
    add_mono(ring_sig, 7.35, gain=0.50, pan=0.3)

    # Phone pick up click / connect beep (8.8s)
    st_clk = np.linspace(0, 0.12, int(0.12 * SAMPLE_RATE), endpoint=False)
    click = np.sin(2 * np.pi * 1200 * st_clk) * np.exp(-45 * st_clk)
    add_mono(click, 8.85, gain=0.45)

    # 4. Wrong Buzzer / Error Thud (11.8s - Accountant says flash had virus)
    st_buzz = np.linspace(0, 0.45, int(0.45 * SAMPLE_RATE), endpoint=False)
    buzzer = (np.sign(np.sin(2 * np.pi * 140 * st_buzz)) * 0.4 + np.sin(2 * np.pi * 90 * st_buzz) * 0.5) * np.exp(-3.5 * st_buzz)
    add_mono(buzzer, 11.8, gain=0.75, pan=-0.2)

    # 5. Sub-bass Drop / Stinger (15.2s - Did billions vanish?)
    st_drop = np.linspace(0, 1.2, int(1.2 * SAMPLE_RATE), endpoint=False)
    freq_sweep = np.linspace(130, 38, len(st_drop))
    sub_drop = np.sin(2 * np.pi * freq_sweep * st_drop) * np.exp(-1.8 * st_drop)
    add_mono(sub_drop, 15.2, gain=0.90)

    # 6. Magic Shimmer / Crystal Chime Arpeggio (18.1s - "صبر کن! اگه مدیر هوشمند باشی...")
    st_chime = np.linspace(0, 1.4, int(1.4 * SAMPLE_RATE), endpoint=False)
    chime_left = np.zeros_like(st_chime)
    chime_right = np.zeros_like(st_chime)
    # Sparkling ascending chord: C5, E5, G5, B5, D6, G6
    chime_freqs = [523.25, 659.25, 783.99, 987.77, 1174.66, 1567.98]
    for idx, f in enumerate(chime_freqs):
        delay = idx * 0.08
        mask = st_chime >= delay
        rel_t = np.maximum(0, st_chime - delay)
        decay = np.exp(-3.2 * rel_t)
        tone = np.sin(2 * np.pi * f * rel_t) * decay
        # Slight stereo panning alternate
        pan_val = -0.5 if idx % 2 == 0 else 0.5
        chime_left += mask * tone * (1.0 - pan_val) * 0.22
        chime_right += mask * tone * (1.0 + pan_val) * 0.22
    add_stereo(chime_left, chime_right, 18.1, gain=1.1)

    # 7. Cyber Whoosh Transition into UI Demo (22.5s)
    st_whoosh = np.linspace(0, 0.45, int(0.45 * SAMPLE_RATE), endpoint=False)
    w_freq = np.linspace(150, 650, len(st_whoosh))
    whoosh = np.sin(2 * np.pi * w_freq * st_whoosh) * (np.sin(np.pi * (st_whoosh / 0.45)) ** 2) * 0.35
    add_mono(whoosh, 22.5, gain=0.65, pan=0.0)

    # 8. Tech interface clicks (24.2s, 27.0s, 30.0s)
    for ck_t, c_pan in [(24.2, -0.4), (27.0, 0.4), (30.0, -0.2)]:
        st_tck = np.linspace(0, 0.08, int(0.08 * SAMPLE_RATE), endpoint=False)
        tech_click = np.sin(2 * np.pi * 1800 * st_tck) * np.exp(-65 * st_tck)
        add_mono(tech_click, ck_t, gain=0.45, pan=c_pan)

    # 9. Bale Messenger Notification Ding 1 & 2 (33.8s & 36.2s)
    def make_bale_ding():
        st_ding = np.linspace(0, 0.55, int(0.55 * SAMPLE_RATE), endpoint=False)
        n1 = (st_ding < 0.10) * np.sin(2 * np.pi * 880 * st_ding) * np.exp(-10 * st_ding)
        rel_t2 = np.maximum(0, st_ding - 0.09)
        n2 = (st_ding >= 0.09) * np.sin(2 * np.pi * 1318.5 * rel_t2) * np.exp(-6 * rel_t2)
        return (n1 + n2) * 0.55

    add_mono(make_bale_ding(), 33.8, gain=0.85, pan=0.25)
    add_mono(make_bale_ding(), 36.2, gain=0.85, pan=-0.25)

    # 10. Success Double Chime (38.8s - 3 users received)
    st_succ = np.linspace(0, 0.65, int(0.65 * SAMPLE_RATE), endpoint=False)
    succ_tone = (
        0.35 * np.sin(2 * np.pi * 659.25 * st_succ) +
        0.35 * np.sin(2 * np.pi * 783.99 * st_succ) +
        0.30 * np.sin(2 * np.pi * 1046.50 * st_succ)
    ) * np.exp(-4.5 * st_succ)
    add_mono(succ_tone, 38.8, gain=0.80)

    # 11. Call-To-Action Impact Hit & Whoosh (41.0s & 43.0s)
    add_mono(whoosh, 41.0, gain=0.70)
    add_mono(make_bale_ding(), 43.2, gain=0.90, pan=0.0)

    # -------------------------------------------------------------
    # Dynamic Background Music (BGM)
    # -------------------------------------------------------------
    bg_left = np.zeros(n_samples, dtype=np.float32)
    bg_right = np.zeros(n_samples, dtype=np.float32)

    twist_time = 18.0

    # Part 1: Suspense dark minor pulse (0s -> 18s)
    mask1 = np.clip((twist_time - t) / 0.5, 0.0, 1.0)
    drone = (
        0.25 * np.sin(2 * np.pi * 110.0 * t) +   # A2
        0.18 * np.sin(2 * np.pi * 130.81 * t) +  # C3
        0.18 * np.sin(2 * np.pi * 164.81 * t)    # E3
    )
    # Slow 1.5 Hz LFO modulation
    lfo = 0.7 + 0.3 * np.sin(2 * np.pi * 1.5 * t)
    pulse_115bpm = (np.sin(2 * np.pi * (115.0 / 60.0) * t) ** 4) * 0.22
    dark_track = mask1 * (drone * lfo + pulse_115bpm) * 0.16

    # Part 2: Upbeat, modern corporate tech beat (18s -> 48s)
    mask2 = np.clip((t - twist_time + 0.3) / 0.6, 0.0, 1.0)

    # 125 BPM House/Lo-Fi Tech Groove
    bpm = 125.0
    beat_freq = bpm / 60.0  # ~2.083 beats per sec
    beat_phase = (t * beat_freq) % 1.0

    # Kick on every beat
    kick_env = np.exp(-18 * beat_phase)
    kick = np.sin(2 * np.pi * (55 + 75 * np.exp(-30 * beat_phase)) * t) * kick_env * 0.32

    # High-hat on offbeats (phase ~0.5)
    hat_phase = (t * beat_freq * 2.0) % 1.0
    hat_noise = (np.random.RandomState(42).uniform(-1, 1, n_samples) * 0.12) * np.exp(-28 * hat_phase)

    # Warm uplifting chord progression (Cmaj9 -> Am9 -> Fmaj7 -> G6)
    c_phase = (t * (beat_freq / 4.0)) % 4.0
    chord_tones = (
        0.20 * np.sin(2 * np.pi * 261.63 * t) +  # C4
        0.18 * np.sin(2 * np.pi * 329.63 * t) +  # E4
        0.16 * np.sin(2 * np.pi * 392.00 * t) +  # G4
        0.14 * np.sin(2 * np.pi * 493.88 * t)    # B4
    )
    sidechain = 0.55 + 0.45 * (beat_phase ** 1.8)

    bright_track = mask2 * (kick + hat_noise + chord_tones * sidechain * 0.25) * 0.22

    # Fade out at the last 1.2s
    fade_end = np.clip((total_dur - t) / 1.2, 0.0, 1.0)

    master_left = (dark_track + bright_track + sfx_left) * fade_end
    master_right = (dark_track + bright_track + sfx_right) * fade_end

    out_sfx_music = AUDIO_DIR / "sfx_and_music_master.wav"
    write_wav_stereo(out_sfx_music, master_left, master_right)
    print(f"Generated complete SFX & Music soundtrack: {out_sfx_music}")

    # Write timeline json
    meta_path = AUDIO_DIR / "timeline_sfx.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(TIMELINE, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    make_sfx_and_music()
