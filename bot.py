import os
import re
import asyncio
import requests
import fitz
from PIL import Image
import pytesseract
import io

from pyrogram import Client, filters
from deep_translator import GoogleTranslator
from fpdf import FPDF
from config import API_ID, API_HASH, BOT_TOKEN, DOWNLOAD_DIR, OUTPUT_DIR

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, DOWNLOAD_DIR) if not os.path.isabs(DOWNLOAD_DIR) else DOWNLOAD_DIR
OUTPUT_DIR = os.path.join(BASE_DIR, OUTPUT_DIR) if not os.path.isabs(OUTPUT_DIR) else OUTPUT_DIR
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# FONT DOWNLOAD
FONT_PATH = os.path.join(BASE_DIR, "NotoSansDevanagari-Regular.ttf")
FONT_URLS = [
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf",
    "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf"
]
if os.path.exists(FONT_PATH) and os.path.getsize(FONT_PATH) < 100000:
    os.remove(FONT_PATH)
if not os.path.exists(FONT_PATH):
    for url in FONT_URLS:
        try:
            r = requests.get(url, timeout=60)
            if len(r.content) > 50000:
                open(FONT_PATH, "wb").write(r.content)
                print(f"FONT OK {os.path.getsize(FONT_PATH)}")
                break
        except: continue

app = Client("ocr_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def clean_text(text):
    return re.sub(r"\n{3,}", "\n\n", text.replace("\x00","")).strip()

async def translate_text(text, status_msg):
    # 800 chars ke chunk me translate
    chunks = [text[i:i+800] for i in range(0, len(text), 800)]
    out = []
    for idx, ch in enumerate(chunks):
        try:
            tr = await asyncio.to_thread(GoogleTranslator(source="en", target="hi").translate, ch)
            out.append(tr if tr else ch)
        except:
            out.append(ch)
        await asyncio.sleep(1)
        if idx % 3 == 0:
            try: await status_msg.edit_text(f"🌐 Translate: {idx+1}/{len(chunks)}")
            except: pass
    return "\n".join(out)

def extract_with_ocr(pdf_path, status_msg_sync=None):
    """Scanned PDF se OCR se English nikalega"""
    doc = fitz.open(pdf_path)
    full_text = ""
    print(f"Total pages: {len(doc)}")
    for page_num in range(len(doc)):
        page = doc[page_num]
        # Pehle normal text try
        txt = page.get_text("text").strip()
        if len(txt) > 100: # Agar normal text mil gaya to OCR skip
            full_text += txt + "\n\n"
            print(f"Page {page_num} normal text {len(txt)}")
        else:
            # Scanned hai to OCR
            print(f"Page {page_num} scanned, OCR kar raha hu...")
            pix = page.get_pixmap(dpi=300)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            # English OCR
            ocr_text = pytesseract.image_to_string(img, lang='eng')
            full_text += ocr_text + "\n\n"
    doc.close()
    return full_text

def create_pdf(text, output_path):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.add_font("NotoHindi", "", FONT_PATH, uni=True)
    pdf.set_font("NotoHindi", size=11)
    for para in text.split("\n"):
        if not para.strip():
            pdf.ln(4)
            continue
        pdf.multi_cell(0, 7, para.strip())
    pdf.output(output_path)

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("🇮🇳 **Scanned Test PDF → Hindi Bot**\n\nCLC / NRTS / NEET ka English test bhejo, chahe scanned ho, main Hindi bana dunga.")

@app.on_message(filters.document)
async def pdf_handler(client, message):
    if not message.document.file_name.lower().endswith(".pdf"):
        return
    status = await message.reply_text("📥 Download...")
    input_path = os.path.join(DOWNLOAD_DIR, message.document.file_name)
    output_path = os.path.join(OUTPUT_DIR, "Hindi_" + message.document.file_name)
    try:
        await message.download(input_path)
        await status.edit_text("🔍 Scanned check + OCR padh raha hu... (1-2 min lagega)")

        original_text = await asyncio.to_thread(extract_with_ocr, input_path)
        original_text = clean_text(original_text)

        if len(original_text) < 50:
            await status.edit_text("❌ Isme text bilkul nahi mila, PDF khali hai")
            return

        await status.edit_text(f"📖 Total {len(original_text)} chars mile. Ab Hindi me translate...")

        translated = await translate_text(original_text, status)

        await status.edit_text("📝 Hindi PDF bana raha hu...")
        await asyncio.to_thread(create_pdf, translated, output_path)

        await message.reply_document(output_path, caption="🇮🇳 Hindi Test Ready ✅")
        await status.delete()
    except Exception as e:
        print(e)
        await status.edit_text(f"❌ Error: {e}")
    finally:
        for p in [input_path, output_path]:
            if os.path.exists(p): os.remove(p)

print("Bot Started with OCR")
app.run()
