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
# FONT AUTO DOWNLOAD + VALIDATE (HEROKU FIX)
# =========================
FONT_PATH = os.path.join(BASE_DIR, "NotoSansDevanagari-Regular.ttf")
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf"

# Agar font kharab hai (0kb) to delete karo
if os.path.exists(FONT_PATH):
    size = os.path.getsize(FONT_PATH)
    if size < 100000: # 100KB se kam matlab kharab file
        print(f"Font corrupted hai ({size} bytes), delete kar raha hu...")
        try:
            os.remove(FONT_PATH)
        except:
            pass

# Download karo agar nahi hai
if not os.path.exists(FONT_PATH):
    print("Font nahi mila, Heroku pe download kar raha hu...")
    try:
        r = requests.get(FONT_URL, timeout=60)
        r.raise_for_status()
        with open(FONT_PATH, "wb") as f:
            f.write(r.content)
        print(f"FONT DOWNLOADED: {FONT_PATH} - {os.path.getsize(FONT_PATH)} bytes")
    except Exception as e:
        raise FileNotFoundError(f"Font download fail: {e}")

print("FONT FOUND:", FONT_PATH)

# =========================
# TELEGRAM BOT
# =========================
app = Client(
    "english_hindi_pdf_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# =========================
# TEXT CLEAN
# =========================
def clean_text(text):
    if not text:
        return ""
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def split_text(text, max_chars=1500):
    text = text.strip()
    if not text:
        return []
    chunks = []
    while len(text) > max_chars:
        cut = text.rfind("\n", 0, max_chars)
        if cut < 400:
            cut = text.rfind(" ", 0, max_chars)
        if cut < 400:
            cut = max_chars
        chunk = text[:cut].strip()
        if chunk:
            chunks.append(chunk)
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks

# =========================
# TRANSLATION WITH FALLBACK (GOOGLE BLOCK FIX)
# =========================
async def translate_text(text, status_msg):
    chunks = split_text(text)
    result = []
    total = len(chunks)

    for index, chunk in enumerate(chunks, start=1):
        if not chunk.strip():
            continue

        translated = None
        try:
            # Try 1: Google Translator
            translator = GoogleTranslator(source="en", target="hi")
            translated = await asyncio.to_thread(translator.translate, chunk)
        except Exception as e:
            print(f"Google Translator fail {index}/{total}: {repr(e)} - MyMemory try kar raha hu")
            try:
                # Try 2: MyMemory - Heroku pe ye best chalta hai
                translator2 = MyMemoryTranslator(source="en-US", target="hi-IN")
                translated = await asyncio.to_thread(translator2.translate, chunk)
            except Exception as e2:
                print(f"MyMemory bhi fail: {repr(e2)}")
                translated = chunk

        if translated and translated.strip():
            result.append(translated)
        else:
            result.append(chunk)

        # Heroku pe Google block se bachne ke liye 1 sec rukna zaroori
        await asyncio.sleep(1.0)

        if index % 3 == 0:
            try:
                await status_msg.edit_text(f"🌐 Translation ho raha hai...\n{index}/{total}")
            except:
                pass

    return "\n\n".join(result)

# =========================
# CREATE PDF
# =========================
def create_pdf(text, output_path):
    text = clean_text(text)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.add_font("NotoHindi", "", FONT_PATH)
    pdf.set_font("NotoHindi", size=12)

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            pdf.ln(4)
            continue
        try:
            pdf.multi_cell(0, 7, line)
        except Exception as e:
            print("PDF write error:", repr(e))
            safe = line.encode('utf-8', 'ignore').decode('utf-8')
            pdf.multi_cell(0, 7, safe)

    pdf.output(output_path)

# =========================
# START
# =========================
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    await message.reply_text(
        "🇮🇳 **English → Hindi PDF Bot**\n\n"
        "English PDF bhejo.\n\n"
        "Main uska Hindi translated PDF bana kar bhej dunga."
    )

# =========================
# PDF HANDLER
# =========================
@app.on_message(filters.document)
async def pdf_handler(client, message):
    document = message.document
    filename = document.file_name or ""
    if not filename.lower().endswith(".pdf"):
        await message.reply_text("❌ Sirf PDF file bhejo.")
        return

    status = await message.reply_text("📥 PDF download ho rahi hai...")
    input_path = os.path.join(DOWNLOAD_DIR, filename)
    output_name = os.path.splitext(filename)[0] + "_Hindi.pdf"
    output_path = os.path.join(OUTPUT_DIR, output_name)

    try:
        await message.download(file_name=input_path)
        await status.edit_text("📖 PDF read ho rahi hai...")

        doc = fitz.open(input_path)
        all_text = []
        total_pages = len(doc)
        for page_number, page in enumerate(doc, start=1):
            page_text = page.get_text("text")
            if page_text.strip():
                all_text.append(page_text)
            if page_number % 5 == 0:
                try:
                    await status.edit_text(f"📖 Reading pages...\n{page_number}/{total_pages}")
                except:
                    pass
        doc.close()

        original_text = "\n\n".join(all_text)
        original_text = clean_text(original_text)

        if not original_text:
            await status.edit_text("❌ Is PDF me selectable text nahi mila.\nScanned PDF ho sakti hai.")
            return

        await status.edit_text(f"🌐 Translation started...\nTotal {len(original_text)} chars")
        translated_text = await translate_text(original_text, status)

        if not translated_text.strip():
            await status.edit_text("❌ Translation nahi ho paya.")
            return

        await status.edit_text("📝 Hindi PDF ban rahi hai...")
        await asyncio.to_thread(create_pdf, translated_text, output_path)

        await status.edit_text("📤 Hindi PDF upload ho rahi hai...")
        await message.reply_document(
            document=output_path,
            caption="🇮🇳 **English → Hindi PDF**\n\n✅ Translation complete."
        )
        await status.delete()

    except Exception as e:
        print("MAIN ERROR:", repr(e))
        try:
            await status.edit_text(f"❌ Error aa gaya:\n`{str(e)[:3000]}`")
        except:
            pass
    finally:
        for p in [input_path, output_path]:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except:
                pass

print("🇮🇳 English → Hindi PDF Bot Started!")
print("Using font:", FONT_PATH)
app.run()
