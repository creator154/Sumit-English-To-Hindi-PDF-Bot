import os
import re
import asyncio
import requests

import fitz
from pyrogram import Client, filters
from deep_translator import GoogleTranslator, MyMemoryTranslator
from fpdf import FPDF

from config import API_ID, API_HASH, BOT_TOKEN, DOWNLOAD_DIR, OUTPUT_DIR

# =========================
# DIRECTORIES
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, DOWNLOAD_DIR) if not os.path.isabs(DOWNLOAD_DIR) else DOWNLOAD_DIR
OUTPUT_DIR = os.path.join(BASE_DIR, OUTPUT_DIR) if not os.path.isabs(OUTPUT_DIR) else OUTPUT_DIR
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# =========================
# FONT AUTO DOWNLOAD - FIXED
# =========================
FONT_PATH = os.path.join(BASE_DIR, "NotoSansDevanagari-Regular.ttf")

FONT_URLS = [
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf",
    "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf",
    "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari%5Bwdth%2Cwght%5D.ttf"
]

if os.path.exists(FONT_PATH):
    if os.path.getsize(FONT_PATH) < 100000:
        print(f"Corrupted font delete: {os.path.getsize(FONT_PATH)} bytes")
        try: os.remove(FONT_PATH)
        except: pass

if not os.path.exists(FONT_PATH):
    print("Font download start...")
    ok = False
    for url in FONT_URLS:
        try:
            print(f"Trying: {url}")
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            if len(r.content) < 50000: continue
            with open(FONT_PATH, "wb") as f:
                f.write(r.content)
            print(f"SUCCESS: FONT DOWNLOADED - {os.path.getsize(FONT_PATH)} bytes")
            ok = True
            break
        except Exception as e:
            print(f"Failed {url}: {e}")
            continue
    if not ok:
        raise FileNotFoundError("Font download fail")

print("FONT FOUND:", FONT_PATH)

# =========================
# BOT CLIENT
# =========================
app = Client("english_hindi_pdf_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def clean_text(text):
    if not text: return ""
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def split_text(text, max_chars=1000):
    text = text.strip()
    if not text: return []
    chunks = []
    while len(text) > max_chars:
        cut = text.rfind("\n", 0, max_chars)
        if cut < 300: cut = text.rfind(".", 0, max_chars)
        if cut < 300: cut = text.rfind(" ", 0, max_chars)
        if cut < 300: cut = max_chars
        chunk = text[:cut].strip()
        if chunk: chunks.append(chunk)
        text = text[cut:].strip()
    if text: chunks.append(text)
    return chunks

async def translate_text(text, status_msg):
    chunks = split_text(text)
    result = []
    total = len(chunks)
    print(f"Total chunks: {total}")
    for index, chunk in enumerate(chunks, start=1):
        if not chunk.strip(): continue
        translated = None
        try:
            t = GoogleTranslator(source="en", target="hi")
            translated = await asyncio.to_thread(t.translate, chunk)
        except Exception as e:
            print(f"Google fail {index}: {e}")
            try:
                t2 = MyMemoryTranslator(source="en-US", target="hi-IN")
                translated = await asyncio.to_thread(t2.translate, chunk)
            except Exception as e2:
                print(f"MyMemory fail: {e2}")
                translated = chunk

        if translated and translated.strip():
            result.append(translated)
        else:
            result.append(chunk)

        await asyncio.sleep(1.2)
        if index % 2 == 0:
            try: await status_msg.edit_text(f"🌐 Translate ho raha hai: {index}/{total}")
            except: pass
    return "\n\n".join(result)

# =========================
# CREATE PDF - 1 2 3 BUG FIX
# =========================
def create_pdf(text, output_path):
    text = clean_text(text)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # IMPORTANT FIX: uni=True for Hindi
    pdf.add_font("NotoHindi", "", FONT_PATH, uni=True)
    pdf.set_font("NotoHindi", size=12)

    if len(text) < 20:
        text = "Is PDF me text nahi mila ya translation fail ho gaya. Kripya selectable text wala PDF bheje."

    # Paragraph wise likho
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            pdf.ln(5)
            continue
        pdf.multi_cell(0, 8, para)
        pdf.ln(4)

    pdf.output(output_path)
    print(f"PDF created: {output_path}")

# =========================
# HANDLERS
# =========================
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    await message.reply_text("🇮🇳 **English → Hindi PDF Bot Ready**\n\nEnglish PDF bhejo, mai Hindi me convert kar dunga.")

@app.on_message(filters.document)
async def pdf_handler(client, message):
    filename = message.document.file_name or ""
    if not filename.lower().endswith(".pdf"):
        await message.reply_text("❌ Sirf PDF bhejo.")
        return

    status = await message.reply_text("📥 PDF download...")
    input_path = os.path.join(DOWNLOAD_DIR, filename)
    output_path = os.path.join(OUTPUT_DIR, os.path.splitext(filename)[0] + "_Hindi.pdf")

    try:
        await message.download(file_name=input_path)
        await status.edit_text("📖 PDF padh raha hu...")

        doc = fitz.open(input_path)
        all_text = []
        for page in doc:
            t = page.get_text("text")
            if t and t.strip():
                all_text.append(t)

        doc.close()

        original_text = clean_text("\n\n".join(all_text))
        print(f"Extracted text length: {len(original_text)}")
        print(f"First 200 chars: {original_text[:200]}")

        if len(original_text) < 30:
            await status.edit_text("❌ Is PDF me readable text nahi hai. Ye scanned PDF lagta hai.\nKoi dusra PDF bhejo jisme se text copy hota ho.")
            return

        await status.edit_text(f"🌐 Translation start... {len(original_text)} chars")
        translated_text = await translate_text(original_text, status)

        await status.edit_text("📝 Hindi PDF bana raha hu...")
        await asyncio.to_thread(create_pdf, translated_text, output_path)

        await status.edit_text("📤 Bhej raha hu...")
        await message.reply_document(document=output_path, caption="🇮🇳 **Hindi PDF Ready** ✅")
        await status.delete()

    except Exception as e:
        print("MAIN ERROR:", repr(e))
        try: await status.edit_text(f"❌ Error: {str(e)[:2000]}")
        except: pass
    finally:
        for p in [input_path, output_path]:
            try:
                if os.path.exists(p): os.remove(p)
            except: pass

print("🇮🇳 Bot Started! Font:", FONT_PATH)
app.run()
