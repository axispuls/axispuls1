import asyncio
import edge_tts
from pathlib import Path

test_text = """
ساعَتِ یازدَهِ شَبِه!
فَردا مُمَیِّزیِ مالیاتی داری، و یِهو... سیستِمِ حِسابداریِ شِرکَت بالا نِمیاد!
هاردِت سوخته و کُلِّ اِطّلاعاتِت قُفل شُده!
"""

async def test():
    out = Path(r"f:\send bak\سناریو\شماره_یک\assets\audio\test_diacritics.mp3")
    comm = edge_tts.Communicate(
        text=test_text.strip(),
        voice="fa-IR-FaridNeural",
        rate="+2%",
        pitch="+0Hz"
    )
    await comm.save(str(out))
    print("Saved test_diacritics.mp3, size:", out.stat().st_size)

if __name__ == "__main__":
    asyncio.run(test())
