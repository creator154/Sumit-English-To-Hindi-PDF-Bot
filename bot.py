import os
import re
import asyncio
import fitz
from pyrogram import Client, filters
from deep_translator import GoogleTranslator
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
# FIND FONT
# =========================
FONT_CANDIDATES = [
    "NotoSansDevanagari-Regular.ttf",
    "NotoSansDevanagari-Regular (6).ttf",
]
FONT_PATH = None
for filename in FONT_CANDIDATES:
    path = os.path.join(BASE_DIR, filename)
    if os.path.isfile(path):
        FONT_PATH = path
        break
if FONT_PATH is None:
    raise FileNotFoundError("NotoSansDevanagari-Regular.ttf font bot.py ke sath wale folder me rakho.")
print("FONT FOUND:", FONT_PATH)

# =========================
# TELEGRAM BOT
# =========================
app = Client("english_hindi_pdf_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# =========================
# TEXT CLEAN
# =========================
def clean_text(text):
    if not text: return ""
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def split_text(text, max_chars=1800):
    text = text.strip()
    if not text: return []
    chunks = []
    while len(text) > max_chars:
        cut = text.rfind("\n", 0, max_chars)
        if cut < 500: cut = text.rfind(" ", 0, max_chars)
        if cut < 500: cut = max_chars
        chunk = text[:cut].strip()
        if chunk: chunks.append(chunk)
        text = text[cut:].strip()
    if text: chunks.append(text)
    return chunks

# =========================
# TRANSLATION - FIXED
# =========================
async def translate_text(text, status_msg):
    chunks = split_text(text)
    result = []
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        if not chunk.strip(): continue
        try:
            # Har baar naya translator banao - block se bachega
            translator = GoogleTranslator(source="en", target="hi")
            translated = await asyncio.to_thread(translator.translate, chunk)
            result.append(translated if translated and translated.strip() else chunk)

            if index % 2 == 0:
                try:
                    await status_msg.edit_text(f"🌐 Translation ho raha hai...\n{index}/{total} chunks")
                except: pass

        except Exception as e:
            print(f"Translation error {index}/{total}:", repr(e))
            result.append(chunk) # fail hua to original hi rakho
        await asyncio.sleep(0.7)
    return "\n\n".join(result)

# =========================
# CREATE PDF - COMPLETELY FIXED
# =========================
def create_pdf(text, output_path):
    text = clean_text(text)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    # fpdf2 me uni=True ki jarurat nahi, direct unicode support hai
    pdf.add_font("NotoHindi", "", FONT_PATH)
    pdf.set_font("NotoHindi", size=12)

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            pdf.ln(4)
            continue
        try:
            # Saara kaam ek hi font se karo, mix logic hata diya
            pdf.multi_cell(0, 7, line)
        except Exception as e:
            print("PDF write error:", repr(e))
            # Agar koi char support na kare to usko hata do
            safe = line.encode('utf-8', 'ignore').decode('utf-8')
            pdf.multi_cell(0, 7, safe)

    pdf.output(output_path)

# =========================
# HANDLERS
# =========================
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    await message.reply_text("🇮🇳 **English → Hindi PDF Bot**\n\nEnglish PDF bhejo.\nMain uska Hindi translated PDF bana kar bhej dunga.")

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
        for i, page in enumerate(doc, start=1):
            page_text = page.get_text("text")
            if page_text.strip(): all_text.append(page_text)
            if i % 5 == 0:
                try: await status.edit_text(f"📖 Reading pages...\n{i}/{total_pages}")
                except: pass
        doc.close()

        original_text = clean_text("\n\n".join(all_text))
        if not original_text:
            await status.edit_text("❌ Is PDF me selectable text nahi mila. Ye scanned PDF ho sakti hai.")
            return

        await status.edit_text(f"🌐 Translation started... {len(original_text)} chars")
        translated_text = await translate_text(original_text, status)

        if not translated_text.strip():
            await status.edit_text("❌ Translation nahi ho paya.")
            return

        await status.edit_text("📝 Hindi PDF ban rahi hai...")
        await asyncio.to_thread(create_pdf, translated_text, output_path)

        await status.edit_text("📤 Hindi PDF upload ho rahi hai...")
        await message.reply_document(document=output_path, caption="🇮🇳 **English → Hindi PDF**\n\n✅ Translation complete.")
        await status.delete()

    except Exception as e:
        print("MAIN ERROR:", repr(e))
        try: await status.edit_text(f"❌ Error aa gaya:\n`{str(e)[:3000]}`")
        except: pass
    finally:
        for p in [input_path, output_path]:
            try:
                if os.path.exists(p): os.remove(p)
            except: pass

print("🇮🇳 English → Hindi PDF Bot Started!")
app.run()
