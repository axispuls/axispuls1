import json
import math
import subprocess
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
import imageio_ffmpeg

BASE_DIR = Path(r"f:\send bak\سناریو\شماره_یک")
PROJECT_ROOT = Path(r"f:\send bak")
FONT_DIR = BASE_DIR / "assets" / "fonts"
AUDIO_DIR = BASE_DIR / "assets" / "audio"
OUTPUT_VIDEO = BASE_DIR / "01_کلیپ_سناریو_اول_مخصوص_صداگذاری.mp4"
COVER_IMAGE = BASE_DIR / "01_کاور_ریلز_اکسیس_پالس.png"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

# Load fonts
def get_font(weight="bold", size=44):
    font_map = {
        "extrabold": FONT_DIR / "Vazirmatn-ExtraBold.ttf",
        "bold": FONT_DIR / "Vazirmatn-Bold.ttf",
        "medium": FONT_DIR / "Vazirmatn-Medium.ttf",
    }
    fpath = font_map.get(weight, font_map["bold"])
    return ImageFont.truetype(str(fpath), size)

FONT_CACHE = {}
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    key = (weight, size)
    if key not in FONT_CACHE:
        FONT_CACHE[key] = get_font(weight, size)
    return FONT_CACHE[key]

def rtl(text: str) -> str:
    if not text:
        return ""
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

def draw_rtl(draw: ImageDraw.ImageDraw, pos: tuple[int, int], text: str, fnt, fill, anchor="mm", stroke_width=0, stroke_fill=(0, 0, 0)):
    shaped = rtl(text)
    if stroke_width > 0:
        draw.text(pos, shaped, font=fnt, fill=fill, anchor=anchor, stroke_width=stroke_width, stroke_fill=stroke_fill)
    else:
        draw.text(pos, shaped, font=fnt, fill=fill, anchor=anchor)

def ease_out_back(x: float) -> float:
    x = max(0.0, min(1.0, x))
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * pow(x - 1, 3) + c1 * pow(x - 1, 2)

def ease_out_cubic(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - pow(1 - x, 3)

LOGO_PATH = PROJECT_ROOT / "logo-original.png"
if LOGO_PATH.exists():
    RAW_LOGO = Image.open(LOGO_PATH).convert("RGBA")
else:
    RAW_LOGO = Image.new("RGBA", (200, 200), (139, 92, 246, 255))

def make_vertical_gradient(top_rgb, mid_rgb, bot_rgb) -> Image.Image:
    arr = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    half = HEIGHT // 2
    for c in range(3):
        arr[:half, :, c] = np.linspace(top_rgb[c], mid_rgb[c], half, dtype=np.uint8)[:, None]
        arr[half:, :, c] = np.linspace(mid_rgb[c], bot_rgb[c], HEIGHT - half, dtype=np.uint8)[:, None]
    arr[::80, :, :] = np.clip(arr[::80, :, :].astype(np.int16) + 10, 0, 255).astype(np.uint8)
    arr[:, ::80, :] = np.clip(arr[:, ::80, :].astype(np.int16) + 10, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="RGB")

BG_DARK_RED = make_vertical_gradient((28, 8, 14), (48, 10, 20), (15, 6, 12))
BG_DARK_CALL = make_vertical_gradient((14, 18, 34), (24, 16, 38), (10, 12, 22))
BG_HERO_BLUE = make_vertical_gradient((12, 20, 46), (22, 36, 78), (10, 18, 38))
BG_BALE_EMERALD = make_vertical_gradient((10, 28, 36), (14, 48, 56), (8, 20, 28))
BG_CTA_ROYAL = make_vertical_gradient((24, 14, 52), (16, 34, 72), (10, 16, 36))

def draw_warning_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, color=(239, 68, 68)):
    pts = [
        (cx, cy - radius),
        (cx - int(radius * 0.92), cy + int(radius * 0.78)),
        (cx + int(radius * 0.92), cy + int(radius * 0.78))
    ]
    draw.polygon(pts, fill=color, outline=(255, 255, 255), width=4)
    draw.rounded_rectangle([cx - 6, cy - int(radius * 0.38), cx + 6, cy + int(radius * 0.22)], radius=5, fill=(255, 255, 255))
    draw.ellipse([cx - 7, cy + int(radius * 0.36), cx + 7, cy + int(radius * 0.50)], fill=(255, 255, 255))

def draw_check_circle(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, bg_color=(16, 185, 129)):
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=bg_color)
    p1 = (cx - int(radius * 0.42), cy + int(radius * 0.02))
    p2 = (cx - int(radius * 0.10), cy + int(radius * 0.36))
    p3 = (cx + int(radius * 0.46), cy - int(radius * 0.32))
    draw.line([p1, p2, p3], fill=(255, 255, 255), width=max(4, radius // 4), joint="curve")

def draw_cross_circle(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, bg_color=(239, 68, 68)):
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=bg_color)
    d = int(radius * 0.36)
    w = max(4, radius // 4)
    draw.line([(cx - d, cy - d), (cx + d, cy + d)], fill=(255, 255, 255), width=w)
    draw.line([(cx - d, cy + d), (cx + d, cy - d)], fill=(255, 255, 255), width=w)

def draw_top_hook_banner(draw: ImageDraw.ImageDraw, text: str, accent_color=(239, 68, 68), pulse=0.0):
    bx1, by1, bx2, by2 = 70, 68, WIDTH - 70, 166
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=49, fill=(15, 23, 42), outline=accent_color, width=4)
    dot_r = int(12 + 4 * math.sin(pulse * 6))
    draw.ellipse([bx2 - 52 - dot_r, 117 - dot_r, bx2 - 52 + dot_r, 117 + dot_r], fill=accent_color)
    draw_rtl(draw, (WIDTH // 2 - 15, 117), text, font("extrabold", 38), (255, 255, 255))

def draw_subtitle_box(draw: ImageDraw.ImageDraw, line1: str, line2: str = "", highlight_color=(250, 204, 21), progress=1.0):
    sx1, sy1, sx2, sy2 = 56, 1475, WIDTH - 56, 1715
    draw.rounded_rectangle([sx1, sy1 + 8, sx2, sy2 + 8], radius=32, fill=(0, 0, 0))
    draw.rounded_rectangle([sx1, sy1, sx2, sy2], radius=32, fill=(15, 23, 42), outline=highlight_color, width=3)

    bar_w = int(260 * ease_out_cubic(progress))
    draw.rounded_rectangle([WIDTH // 2 - bar_w // 2, sy1 - 4, WIDTH // 2 + bar_w // 2, sy1 + 6], radius=5, fill=highlight_color)

    if line2:
        draw_rtl(draw, (WIDTH // 2, sy1 + 78), line1, font("bold", 40), (255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
        draw_rtl(draw, (WIDTH // 2, sy1 + 162), line2, font("extrabold", 44), highlight_color, stroke_width=2, stroke_fill=(0, 0, 0))
    else:
        draw_rtl(draw, (WIDTH // 2, (sy1 + sy2) // 2), line1, font("extrabold", 44), highlight_color, stroke_width=2, stroke_fill=(0, 0, 0))

    draw.rounded_rectangle([320, 1775, WIDTH - 320, 1845], radius=35, fill=(30, 41, 59), outline=(100, 116, 139), width=2)
    draw.text((WIDTH // 2, 1810), "AXIS PULS  •  @AXISPULS", font=font("extrabold", 27), fill=(148, 163, 184), anchor="mm")


def render_scene1_hook(t: float, start_t: float, end_t: float) -> Image.Image:
    local_t = t - start_t
    prog = local_t / (end_t - start_t)
    img = BG_DARK_RED.copy()
    draw = ImageDraw.Draw(img)

    pulse_val = int(140 + 100 * abs(math.sin(t * 7.0)))
    draw.rectangle([0, 0, WIDTH - 1, HEIGHT - 1], outline=(pulse_val, 20, 30), width=14)

    draw_top_hook_banner(draw, "حساب‌های کل امسالمون پرید؟! 😱", accent_color=(239, 68, 68), pulse=t)

    draw.rounded_rectangle([330, 215, WIDTH - 330, 335], radius=24, fill=(45, 12, 22), outline=(239, 68, 68), width=3)
    colon = ":" if int(t * 2) % 2 == 0 else " "
    draw.text((WIDTH // 2, 260), f"23{colon}14 PM", font=font("extrabold", 46), fill=(252, 165, 165), anchor="mm")
    draw_rtl(draw, (WIDTH // 2, 308), "شب قبل از ممیزی مالیاتی", font("medium", 26), (254, 202, 202))

    shake_x, shake_y = 0, 0
    if 1.2 < local_t < 2.8:
        shake_x = int(12 * math.sin(local_t * 55))
        shake_y = int(10 * math.cos(local_t * 48))

    cx1, cy1, cx2, cy2 = 75 + shake_x, 390 + shake_y, WIDTH - 75 + shake_x, 1140 + shake_y
    draw.rounded_rectangle([cx1 + 8, cy1 + 12, cx2 + 8, cy2 + 12], radius=32, fill=(0, 0, 0))
    draw.rounded_rectangle([cx1, cy1, cx2, cy2], radius=32, fill=(24, 15, 28), outline=(239, 68, 68), width=5)

    draw.rounded_rectangle([cx1, cy1, cx2, cy1 + 95], radius=32, fill=(185, 28, 28))
    draw.rectangle([cx1, cy1 + 50, cx2, cy1 + 95], fill=(185, 28, 28))
    draw.text((cx1 + 260, cy1 + 48), "CRITICAL DISK ERROR", font=font("extrabold", 32), fill=(255, 255, 255), anchor="mm")
    for i, col in enumerate([(252, 165, 165), (252, 211, 77), (255, 255, 255)]):
        draw.ellipse([cx2 - 55 - i * 36, cy1 + 36, cx2 - 31 - i * 36, cy1 + 60], fill=col)

    warn_r = int(82 + 8 * math.sin(t * 8))
    draw_warning_icon(draw, WIDTH // 2 + shake_x, cy1 + 235, warn_r, color=(239, 68, 68))

    draw_rtl(draw, (WIDTH // 2 + shake_x, cy1 + 385), "خطای بحرانی هارد دیسک سیستم!", font("extrabold", 48), (255, 255, 255))
    draw_rtl(draw, (WIDTH // 2 + shake_x, cy1 + 455), "دیتابیس نرم‌افزار حسابداری قفل و غیرقابل بازیابی شد", font("bold", 33), (252, 165, 165))

    files = [
        ("Holoo_Database_1405.mdb", "CORRUPTED / قفل شده"),
        ("Sepidar_Financial_DB.bak", "DISK READ ERROR"),
        ("Tax_Audit_Reports.xlsx", "ACCESS DENIED")
    ]
    for idx, (fname, status) in enumerate(files):
        fy = cy1 + 515 + idx * 72
        draw.rounded_rectangle([cx1 + 45, fy, cx2 - 45, fy + 58], radius=14, fill=(45, 20, 32), outline=(153, 27, 27), width=2)
        draw.text((cx1 + 70, fy + 29), fname, font=font("bold", 26), fill=(248, 250, 252), anchor="lm")
        draw_rtl(draw, (cx2 - 70, fy + 29), status, font("extrabold", 24), (248, 113, 113), anchor="rm")

    if local_t > 1.8:
        b_prog = ease_out_back((local_t - 1.8) / 0.5)
        bw = int(430 * b_prog)
        draw.rounded_rectangle([WIDTH // 2 - bw, 1200, WIDTH // 2 + bw, 1390], radius=28, fill=(127, 29, 29), outline=(252, 165, 165), width=3)
        draw_rtl(draw, (WIDTH // 2, 1265), "سیستم حسابداری شرکت بالا نمیاد!", font("extrabold", 42), (254, 240, 138))
        draw_rtl(draw, (WIDTH // 2, 1335), "هارد سوخته و کل اطلاعاتت قفل شده!", font("bold", 36), (255, 255, 255))

    if prog < 0.50:
        draw_subtitle_box(draw, "ساعت ۱۱ شبه و فردا ممیزی مالیاتی داری...", "یهو سیستم حسابداری شرکت بالا نمیاد!", highlight_color=(248, 113, 113), progress=prog * 2)
    else:
        draw_subtitle_box(draw, "هارد سوخته و کل اطلاعاتت قفل شده!", "فاجعه در یک ثانیه!", highlight_color=(250, 204, 21), progress=(prog - 0.50) * 2)

    return img


def render_scene2_call(t: float, start_t: float, end_t: float) -> Image.Image:
    local_t = t - start_t
    prog = local_t / (end_t - start_t)
    img = BG_DARK_CALL.copy()
    draw = ImageDraw.Draw(img)

    is_accountant_speaking = local_t >= 3.6
    accent = (249, 115, 22) if is_accountant_speaking else (56, 189, 248)

    draw_top_hook_banner(draw, "وقتی امنیت شرکت دست حافظه دیگرانه... 🤦‍♂️", accent_color=accent, pulse=t)

    px1, py1, px2, py2 = 85, 220, WIDTH - 85, 930
    draw.rounded_rectangle([px1, py1, px2, py2], radius=44, fill=(15, 23, 42), outline=accent, width=4)

    status_txt = "در حال مکالمه اضطراری..." if is_accountant_speaking else "در حال تماس با حسابدار..."
    draw.rounded_rectangle([320, py1 + 35, WIDTH - 320, py1 + 95], radius=30, fill=(30, 41, 59))
    draw_rtl(draw, (WIDTH // 2, py1 + 65), status_txt, font("bold", 28), accent)

    avx, avy = WIDTH // 2, py1 + 240
    for ring in range(3):
        r_pulse = 85 + ring * 28 + int(10 * math.sin(t * 10 - ring))
        draw.ellipse([avx - r_pulse, avy - r_pulse, avx + r_pulse, avy + r_pulse], outline=accent, width=2)
    draw.ellipse([avx - 82, avy - 82, avx + 82, avy + 82], fill=accent)
    draw_rtl(draw, (avx, avy), "حسابدار", font("extrabold", 36), (15, 23, 42))

    draw_rtl(draw, (WIDTH // 2, py1 + 395), "خانم رضایی (حسابدار شرکت)", font("extrabold", 42), (255, 255, 255))

    num_bars = 24
    bar_w = 14
    gap = 12
    total_w = num_bars * (bar_w + gap)
    start_x = (WIDTH - total_w) // 2
    wy = py1 + 505
    for i in range(num_bars):
        bh = int(18 + 52 * abs(math.sin(t * 12 + i * 0.55)))
        bx = start_x + i * (bar_w + gap)
        draw.rounded_rectangle([bx, wy - bh, bx + bar_w, wy + bh], radius=6, fill=accent)

    # Card 1: Manager Question
    c1_prog = ease_out_back(local_t / 0.45)
    if c1_prog > 0:
        y_off = int((1 - c1_prog) * 60)
        draw.rounded_rectangle([85, 975 + y_off, WIDTH - 85, 1125 + y_off], radius=26, fill=(30, 58, 138), outline=(96, 165, 250), width=3)
        draw_rtl(draw, (WIDTH - 130, 1025 + y_off), "مدیرعامل:", font("bold", 28), (147, 197, 253), anchor="rm")
        draw_rtl(draw, (WIDTH // 2, 1078 + y_off), "«پس فایل بکاپ حسابداری کجاست؟!»", font("extrabold", 38), (255, 255, 255))

    # Card 2: Accountant's Excuse
    if is_accountant_speaking:
        c2_prog = ease_out_back((local_t - 3.6) / 0.45)
        y_off2 = int((1 - c2_prog) * 60)
        draw.rounded_rectangle([85, 1165 + y_off2, WIDTH - 85, 1415 + y_off2], radius=26, fill=(124, 45, 18), outline=(251, 146, 60), width=4)
        draw_cross_circle(draw, 155, 1290 + y_off2, 38, bg_color=(239, 68, 68))
        draw_rtl(draw, (WIDTH - 125, 1225 + y_off2), "پاسخ حسابدار:", font("bold", 30), (253, 186, 116), anchor="rm")
        draw_rtl(draw, (WIDTH - 125, 1290 + y_off2), "«واای آقای مدیر! فلشم ویروسی شده بود...»", font("extrabold", 36), (255, 255, 255), anchor="rm")
        draw_rtl(draw, (WIDTH - 125, 1355 + y_off2), "«این هفته اصلاً یادم رفته بکاپ بگیرم!»", font("extrabold", 38), (254, 240, 138), anchor="rm")

    if not is_accountant_speaking:
        draw_subtitle_box(draw, "با استرس زنگ می‌زنی به حسابدار...", "«پس فایل بکاپ کجاست؟!»", highlight_color=(56, 189, 248))
    else:
        draw_subtitle_box(draw, "«واای آقای مدیر! فلشم ویروسی شده بود...»", "«این هفته اصلاً یادم رفته بکاپ بگیرم!»", highlight_color=(251, 146, 60))

    return img


def render_scene3_twist(t: float, start_t: float, end_t: float) -> Image.Image:
    local_t = t - start_t
    twist_point = 3.0  # 18.0s mark

    if local_t < twist_point:
        img = BG_DARK_RED.copy()
        draw = ImageDraw.Draw(img)
        draw_top_hook_banner(draw, "میلیاردها تومن حساب و کتاب پرید؟!", accent_color=(239, 68, 68), pulse=t)

        scale = ease_out_back(local_t / 0.4)
        w_box = int(440 * scale)
        draw.rounded_rectangle([WIDTH // 2 - w_box, 540, WIDTH // 2 + w_box, 1080], radius=40, fill=(69, 10, 10), outline=(248, 113, 113), width=5)
        draw_warning_icon(draw, WIDTH // 2, 700, 95, color=(239, 68, 68))
        draw_rtl(draw, (WIDTH // 2, 880), "یعنی کل زحمات امسالت", font("extrabold", 52), (255, 255, 255))
        draw_rtl(draw, (WIDTH // 2, 975), "در یک ثانیه دود شد رفت هوا؟!", font("extrabold", 48), (250, 204, 21))

        draw_subtitle_box(draw, "یعنی میلیاردها تومن حساب و کتاب پرید؟!", "صبر کن...!", highlight_color=(250, 204, 21))
        return img

    rel_hero = local_t - twist_point
    img = BG_HERO_BLUE.copy()
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, WIDTH - 1, HEIGHT - 1], outline=(16, 185, 129), width=12)
    draw_top_hook_banner(draw, "برگ برنده مدیران هوشمند 💡", accent_color=(16, 185, 129), pulse=t)

    cx, cy = WIDTH // 2, 540
    for i in range(3):
        r = int(150 + i * 48 + 12 * math.sin(rel_hero * 6 - i))
        col = (16, 185, 129) if i == 2 else (56, 189, 248)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=3)

    draw.ellipse([cx - 145, cy - 145, cx + 145, cy + 145], fill=(255, 255, 255), outline=(56, 189, 248), width=6)
    logo_size = int(210 * min(1.0, ease_out_back(rel_hero / 0.45)))
    if logo_size > 20:
        resized_logo = RAW_LOGO.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
        img.paste(resized_logo, (cx - logo_size // 2, cy - logo_size // 2), resized_logo)

    card_prog = ease_out_back(max(0.0, (rel_hero - 0.15) / 0.45))
    cy_card = int(760 + (1 - card_prog) * 80)
    draw.rounded_rectangle([75, cy_card, WIDTH - 75, cy_card + 620], radius=36, fill=(255, 255, 255), outline=(56, 189, 248), width=5)

    draw_rtl(draw, (WIDTH // 2, cy_card + 85), "سامانه هوشمند اکسیس پالس", font("extrabold", 52), (15, 23, 42))
    draw.text((WIDTH // 2, cy_card + 155), "AXIS PULS  •  SMART BACKUP GUARD", font=font("extrabold", 28), fill=(2, 132, 199), anchor="mm")

    draw.line([(140, cy_card + 200), (WIDTH - 140, cy_card + 200)], fill=(226, 232, 240), width=3)

    pillars = [
        "پایش خودکار و ۲۴ ساعته پوشه بکاپ ویندوز",
        "ارسال آنی و بدون فیلترشکن به پیام‌رسان بله",
        "بدون نیاز به دخالت حسابدار یا فلش مموری!"
    ]
    for idx, p_text in enumerate(pillars):
        py = cy_card + 265 + idx * 110
        draw.rounded_rectangle([115, py - 38, WIDTH - 115, py + 44], radius=20, fill=(241, 245, 249), outline=(203, 213, 225), width=2)
        draw_check_circle(draw, WIDTH - 165, py + 3, 26, bg_color=(16, 185, 129))
        draw_rtl(draw, (WIDTH - 215, py + 3), p_text, font("bold", 33), (15, 23, 42), anchor="rm")

    draw_subtitle_box(draw, "اگه یه مدیر هوشمند باشی استرس نمی‌گیری!", "چون از قبل «اکسیس پالس» رو نصب کردی!", highlight_color=(52, 211, 153))
    return img


def render_scene4_ui_demo(t: float, start_t: float, end_t: float) -> Image.Image:
    local_t = t - start_t
    dur = end_t - start_t
    prog = local_t / dur

    img = BG_HERO_BLUE.copy()
    draw = ImageDraw.Draw(img)

    draw_top_hook_banner(draw, "پایش ۲۴ ساعته و ارسال مستقیم به بله 🚀", accent_color=(56, 189, 248), pulse=t)

    wx1, wy1, wx2, wy2 = 55, 200, WIDTH - 55, 1425
    draw.rounded_rectangle([wx1 + 8, wy1 + 12, wx2 + 8, wy2 + 12], radius=30, fill=(0, 0, 0))
    draw.rounded_rectangle([wx1, wy1, wx2, wy2], radius=30, fill=(241, 245, 249), outline=(56, 189, 248), width=4)

    draw.rounded_rectangle([wx1, wy1, wx2, wy1 + 72], radius=30, fill=(255, 255, 255))
    draw.rectangle([wx1, wy1 + 40, wx2, wy1 + 72], fill=(255, 255, 255))
    draw.line([(wx1, wy1 + 72), (wx2, wy1 + 72)], fill=(203, 213, 225), width=2)
    draw_rtl(draw, (WIDTH // 2, wy1 + 36), "اکسیس پالس (Axis Puls) - سامانه پایش و ارسال هوشمند فایل", font("bold", 25), (15, 23, 42))

    hx1, hy1, hx2, hy2 = wx1 + 24, wy1 + 92, wx2 - 24, wy1 + 310
    draw.rounded_rectangle([hx1, hy1, hx2, hy2], radius=20, fill=(255, 255, 255), outline=(226, 232, 240), width=2)
    small_logo = RAW_LOGO.resize((90, 90), Image.Resampling.LANCZOS)
    img.paste(small_logo, (hx2 - 115, hy1 + 18), small_logo)
    draw_rtl(draw, (hx2 - 130, hy1 + 45), "اکسیس پالس | Axis Puls", font("extrabold", 34), (15, 23, 42), anchor="rm")
    draw_rtl(draw, (hx2 - 130, hy1 + 92), "پایش هوشمند پوشه و ارسال خودکار به پیام‌رسان بله", font("bold", 24), (71, 85, 105), anchor="rm")

    draw.rounded_rectangle([hx1 + 18, hy1 + 132, hx2 - 18, hy2 - 16], radius=14, fill=(248, 250, 252), outline=(226, 232, 240), width=2)
    draw_check_circle(draw, hx2 - 48, hy1 + 167, 16, bg_color=(16, 185, 129))
    draw_rtl(draw, (hx2 - 75, hy1 + 167), "وضعیت: سرویس فعال و در حال پایش", font("extrabold", 24), (16, 185, 129), anchor="rm")
    rem_sec = max(0, 299 - int(local_t * 12))
    draw_rtl(draw, (hx1 + 35, hy1 + 167), f"ارسال بعدی: 04:{rem_sec % 60:02d}  |  مجوز: فعال (365 روز)", font("bold", 22), (2, 132, 199), anchor="lm")

    s1y = hy2 + 20
    draw.rounded_rectangle([hx1, s1y, hx2, s1y + 175], radius=20, fill=(255, 255, 255), outline=(2, 132, 199), width=3)
    draw_rtl(draw, (hx2 - 24, s1y + 38), "۱. پوشه تحت نظارت ۲۴ ساعته:", font("extrabold", 28), (15, 23, 42), anchor="rm")
    draw.rounded_rectangle([hx1 + 24, s1y + 75, hx2 - 24, s1y + 148], radius=14, fill=(248, 250, 252), outline=(148, 163, 184), width=2)
    draw.text((hx1 + 45, s1y + 111), "D:\\Accounting_Backups\\Holoo_Sepidar\\", font=font("extrabold", 27), fill=(2, 132, 199), anchor="lm")

    s2y = s1y + 195
    draw.rounded_rectangle([hx1, s2y, hx2, s2y + 235], radius=20, fill=(255, 255, 255), outline=(226, 232, 240), width=2)
    draw_rtl(draw, (hx2 - 24, s2y + 38), "۲. گیرندگان مجاز در پیام‌رسان بله (بدون فیلترشکن):", font("extrabold", 27), (15, 23, 42), anchor="rm")

    users = [
        ("کاربر اول (مدیرعامل)", "184920314", "متصل"),
        ("کاربر دوم (مدیر مالی)", "295018422", "متصل"),
        ("کاربر سوم (پشتیبان)", "519283740", "متصل")
    ]
    for idx, (u_title, u_id, u_stat) in enumerate(users):
        uy = s2y + 72 + idx * 50
        draw.rounded_rectangle([hx1 + 24, uy, hx2 - 24, uy + 42], radius=10, fill=(241, 245, 249))
        draw_rtl(draw, (hx2 - 40, uy + 21), u_title, font("bold", 23), (51, 65, 85), anchor="rm")
        draw.text((WIDTH // 2 - 40, uy + 21), f"ID: {u_id}", font=font("bold", 22), fill=(2, 132, 199), anchor="mm")
        draw_rtl(draw, (hx1 + 45, uy + 21), u_stat, font("extrabold", 22), (16, 185, 129), anchor="lm")

    s3y = s2y + 255
    btn_colors = [
        ("ذخیره و شروع سرویس", (16, 185, 129)),
        ("گزارش وضعیت فوری", (2, 132, 199)),
        ("تست ارتباط با بله", (99, 102, 241)),
        ("ارسال فایل همین الان", (245, 158, 11))
    ]
    bw = (hx2 - hx1 - 36) // 4
    for i, (btxt, bcol) in enumerate(btn_colors):
        bx = hx2 - (i + 1) * bw - i * 12
        draw.rounded_rectangle([bx, s3y, bx + bw, s3y + 62], radius=14, fill=bcol)
        draw_rtl(draw, (bx + bw // 2, s3y + 31), btxt, font("extrabold", 20), (255, 255, 255))

    ly1 = s3y + 82
    ly2 = wy2 - 22
    draw.rounded_rectangle([hx1, ly1, hx2, ly2], radius=18, fill=(15, 23, 42), outline=(56, 189, 248), width=3)
    draw_rtl(draw, (hx2 - 24, ly1 + 32), "گزارش لحظه‌ای پایش و ارسال خودکار:", font("bold", 23), (56, 189, 248), anchor="rm")

    logs = [
        (0.05, "فایل جدید شناسایی شد: Backup_1405_08.bak (42.5 MB)", (250, 204, 21)),
        (0.28, "فشرده‌سازی و تقسیم خودکار به پارت‌های استاندارد زیپ...", (147, 197, 253)),
        (0.52, "ارسال پارت ۱ و ۲ به پیام‌رسان بله (بدون فیلترشکن)...", (56, 189, 248)),
        (0.72, "تحویل قطعی و تک‌باره به هر ۳ کاربر با موفقیت ثبت شد!", (52, 211, 153)),
    ]
    for idx, (thresh, ltxt, lcol) in enumerate(logs):
        if prog >= thresh:
            ly = ly1 + 72 + idx * 45
            draw_check_circle(draw, hx2 - 38, ly, 13, bg_color=(16, 185, 129))
            draw_rtl(draw, (hx2 - 64, ly), ltxt, font("bold", 23), lcol, anchor="rm")

    if prog < 0.50:
        draw_subtitle_box(draw, "اکسیس پالس مثل یه نگهبان ۲۴ ساعته", "پوشه بکاپ تو رو بی‌وقفه رصد می‌کنه!", highlight_color=(56, 189, 248))
    else:
        draw_subtitle_box(draw, "بدون نیاز به فیلترشکن و کاملاً خودکار", "مستقیم می‌فرسته به گوشیت توی پیام‌رسان بله!", highlight_color=(52, 211, 153))

    return img


def render_scene5_features(t: float, start_t: float, end_t: float) -> Image.Image:
    local_t = t - start_t
    dur = end_t - start_t
    prog = local_t / dur

    img = BG_BALE_EMERALD.copy()
    draw = ImageDraw.Draw(img)

    draw_top_hook_banner(draw, "ارسال فایل‌های سنگین + بیدار ماندن دائمی 📦", accent_color=(52, 211, 153), pulse=t)

    px1, py1, px2, py2 = 95, 205, WIDTH - 95, 1020
    draw.rounded_rectangle([px1 + 8, py1 + 12, px2 + 8, py2 + 12], radius=46, fill=(0, 0, 0))
    draw.rounded_rectangle([px1, py1, px2, py2], radius=46, fill=(240, 253, 244), outline=(16, 185, 129), width=6)

    draw.rounded_rectangle([px1, py1, px2, py1 + 108], radius=46, fill=(5, 150, 105))
    draw.rectangle([px1, py1 + 60, px2, py1 + 108], fill=(5, 150, 105))
    draw_check_circle(draw, px2 - 65, py1 + 54, 30, bg_color=(16, 185, 129))
    draw_rtl(draw, (px2 - 110, py1 + 40), "بازوی رسمی اکسیس پالس (در بله)", font("extrabold", 30), (255, 255, 255), anchor="rm")
    draw_rtl(draw, (px2 - 110, py1 + 78), "آنلاین • ارسال خودکار و تضمینی فایل", font("medium", 22), (209, 250, 229), anchor="rm")

    parts = [
        (0.0, "Holoo_Backup_1405.zip.001", "پارت ۱ از ۲  •  19.0 MB  •  تحویل قطعی"),
        (0.20, "Holoo_Backup_1405.zip.002", "پارت ۲ از ۲  •  15.8 MB  •  تحویل قطعی")
    ]
    for idx, (p_thresh, fname, fdesc) in enumerate(parts):
        if prog >= p_thresh:
            b_prog = ease_out_back((prog - p_thresh) * 4.0)
            by = int(py1 + 132 + idx * 175 + (1 - b_prog) * 40)
            draw.rounded_rectangle([px1 + 35, by, px2 - 35, by + 152], radius=24, fill=(255, 255, 255), outline=(16, 185, 129), width=3)
            draw.rounded_rectangle([px1 + 58, by + 24, px1 + 158, by + 128], radius=18, fill=(5, 150, 105))
            draw.text((px1 + 108, by + 76), "ZIP", font=font("extrabold", 34), fill=(255, 255, 255), anchor="mm")
            draw.text((px1 + 185, by + 52), fname, font=font("extrabold", 30), fill=(15, 23, 42), anchor="lm")
            draw_rtl(draw, (px2 - 58, by + 108), fdesc, font("bold", 25), (5, 150, 105), anchor="rm")

    if prog >= 0.35:
        by3 = py1 + 490
        draw.rounded_rectangle([px1 + 35, by3, px2 - 35, py2 - 28], radius=24, fill=(220, 252, 231), outline=(16, 185, 129), width=2)
        draw_rtl(draw, (px2 - 60, by3 + 45), "دریافت خودکار آخرین فایل بکاپ سیستم", font("extrabold", 29), (6, 95, 70), anchor="rm")
        draw_rtl(draw, (px2 - 60, by3 + 95), "وضعیت: ارسال تک‌باره به ۳ کاربر تکمیل شد (SHA256 OK)", font("bold", 25), (4, 120, 87), anchor="rm")
        draw_rtl(draw, (px2 - 60, by3 + 145), "پشتیبانی و سایت: @AXISPULS", font("extrabold", 25), (2, 132, 199), anchor="rm")

    feats = [
        (0.05, "فشرده‌سازی و پارت‌بندی خودکار بالای ۲۰ مگابایت", (56, 189, 248)),
        (0.32, "ارسال همزمان به ۳ نفر (مدیرعامل، مالی، پشتیبان)", (250, 204, 21)),
        (0.55, "قطع برق یا ری‌استارت ویندوز؟ خودکار بیدار میشه!", (52, 211, 153))
    ]
    for idx, (f_thresh, f_txt, f_col) in enumerate(feats):
        if prog >= f_thresh:
            f_prog = ease_out_back((prog - f_thresh) * 3.5)
            fy = int(1055 + idx * 125 + (1 - f_prog) * 40)
            draw.rounded_rectangle([65, fy, WIDTH - 65, fy + 105], radius=24, fill=(15, 23, 42), outline=f_col, width=3)
            draw_check_circle(draw, WIDTH - 120, fy + 52, 28, bg_color=(16, 185, 129))
            draw_rtl(draw, (WIDTH - 170, fy + 52), f_txt, font("extrabold", 33), (255, 255, 255), anchor="rm")

    if prog < 0.50:
        draw_subtitle_box(draw, "حتی فایلت بالای ۲۰ مگابایت باشه", "خودش فشرده و پارت‌بندی می‌کنه و می‌فرسته!", highlight_color=(56, 189, 248))
    else:
        draw_subtitle_box(draw, "برق بره یا ویندوز ری‌استارت بشه؟", "بازم خودش اتوماتیک تو پس‌زمینه بیدار میشه!", highlight_color=(52, 211, 153))

    return img


def render_scene6_cta(t: float, start_t: float, end_t: float) -> Image.Image:
    local_t = t - start_t
    img = BG_CTA_ROYAL.copy()
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, WIDTH - 1, HEIGHT - 1], outline=(250, 204, 21), width=14)
    draw_top_hook_banner(draw, "امنیت کسب‌وکارت رو به شانس نسپار! ✨", accent_color=(250, 204, 21), pulse=t)

    cx, cy = WIDTH // 2, 370
    draw.ellipse([cx - 120, cy - 120, cx + 120, cy + 120], fill=(255, 255, 255), outline=(56, 189, 248), width=6)
    logo_img = RAW_LOGO.resize((175, 175), Image.Resampling.LANCZOS)
    img.paste(logo_img, (cx - 87, cy - 87), logo_img)

    draw_rtl(draw, (WIDTH // 2, 545), "اکسیس پالس | Axis Puls", font("extrabold", 56), (255, 255, 255))
    draw_rtl(draw, (WIDTH // 2, 620), "تک‌فایل مستقل ویندوز • نصب در ۳ دقیقه • لایسنس ۱ ساله", font("bold", 31), (147, 197, 253))

    pulse_scale = 1.0 + 0.025 * math.sin(local_t * 8.0)
    bw = int(455 * pulse_scale)
    bh = int(205 * pulse_scale)
    cy_cta = 895
    draw.rounded_rectangle([WIDTH // 2 - bw + 8, cy_cta - bh + 12, WIDTH // 2 + bw + 8, cy_cta + bh + 12], radius=42, fill=(0, 0, 0))
    draw.rounded_rectangle([WIDTH // 2 - bw, cy_cta - bh, WIDTH // 2 + bw, cy_cta + bh], radius=42, fill=(16, 185, 129), outline=(254, 240, 138), width=6)

    draw_rtl(draw, (WIDTH // 2, cy_cta - 95), "همین الان زیر این ویدیو کامنت کن:", font("bold", 38), (240, 253, 244))

    draw.rounded_rectangle([WIDTH // 2 - 280, cy_cta - 35, WIDTH // 2 + 280, cy_cta + 95], radius=32, fill=(255, 255, 255), outline=(250, 204, 21), width=5)
    draw_rtl(draw, (WIDTH // 2, cy_cta + 30), "« پالس »", font("extrabold", 74), (15, 23, 42))

    draw_rtl(draw, (WIDTH // 2, cy_cta + 150), "تا لینک دانلود مستقیم برات دایرکت بشه!", font("extrabold", 36), (254, 240, 138))

    draw.rounded_rectangle([95, 1155, WIDTH - 95, 1315], radius=28, fill=(15, 23, 42), outline=(56, 189, 248), width=3)
    draw_rtl(draw, (WIDTH // 2, 1205), "دریافت مستقیم و پشتیبانی در بله و تلگرام:", font("bold", 30), (203, 213, 225))
    draw.text((WIDTH // 2, 1268), "@AXISPULS", font=font("extrabold", 46), fill=(56, 189, 248), anchor="mm")

    arrow_y = 1365 + int(18 * abs(math.sin(local_t * 7.0)))
    draw.polygon([
        (WIDTH // 2 - 35, arrow_y),
        (WIDTH // 2 + 35, arrow_y),
        (WIDTH // 2 + 35, arrow_y + 40),
        (WIDTH // 2 + 65, arrow_y + 40),
        (WIDTH // 2, arrow_y + 92),
        (WIDTH // 2 - 65, arrow_y + 40),
        (WIDTH // 2 - 35, arrow_y + 40)
    ], fill=(250, 204, 21))

    draw_subtitle_box(draw, "همین الان کلمه «پالس» رو کامنت کن", "تا لینک دانلود مستقیم برات دایرکت بشه!", highlight_color=(250, 204, 21))
    return img


def render_full_video():
    meta_path = AUDIO_DIR / "timeline_sfx.json"
    audio_wav = AUDIO_DIR / "sfx_and_music_master.wav"
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    total_duration = meta["total_duration"]
    scenes = meta["scenes"]
    total_frames = int(total_duration * FPS)
    print(f"Rendering {total_frames} frames ({total_duration}s at {FPS} fps)...")

    # Save high-impact Cover Image
    cover_img = render_scene1_hook(2.4, 0.0, 7.2)
    cover_img.save(str(COVER_IMAGE))
    print(f"Saved cover image: {COVER_IMAGE}")

    cmd = [
        FFMPEG_EXE,
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-pix_fmt", "rgb24",
        "-r", str(FPS),
        "-i", "-",
        "-i", str(audio_wav),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(OUTPUT_VIDEO)
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    s1 = scenes[0]
    s2 = scenes[1]
    s3 = scenes[2]
    s4 = scenes[3]
    s5 = scenes[4]
    s6 = scenes[5]

    for frame_idx in range(total_frames):
        t = frame_idx / FPS

        if t < s2["start"]:
            img = render_scene1_hook(t, s1["start"], s2["start"])
        elif t < s3["start"]:
            img = render_scene2_call(t, s2["start"], s3["start"])
        elif t < s4["start"]:
            img = render_scene3_twist(t, s3["start"], s4["start"])
        elif t < s5["start"]:
            img = render_scene4_ui_demo(t, s4["start"], s5["start"])
        elif t < s6["start"]:
            img = render_scene5_features(t, s5["start"], s6["start"])
        else:
            img = render_scene6_cta(t, s6["start"], total_duration)

        proc.stdin.write(img.tobytes())
        if frame_idx % 150 == 0:
            print(f"  Rendered frame {frame_idx}/{total_frames} ({int(frame_idx / total_frames * 100)}%)")

    proc.stdin.close()
    stderr_out = proc.stderr.read().decode("utf-8", errors="ignore")
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg failed with code {proc.returncode}:\n{stderr_out}")

    print(f"SUCCESS! Video ready for voiceover: {OUTPUT_VIDEO}")


if __name__ == "__main__":
    render_full_video()
