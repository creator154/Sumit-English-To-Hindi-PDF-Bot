import os, re, asyncio, requests, fitz, io
from PIL import Image
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from pyrogram import Client, filters
from deep_translator import GoogleTranslator
from fpdf import FPDF
from config import API_ID, API_HASH, BOT_TOKEN, DOWNLOAD_DIR, OUTPUT_DIR

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, DOWNLOAD_DIR) if not os.path.isabs(DOWNLOAD_DIR) else DOWNLOAD_DIR
OUTPUT_DIR = os.path.join(BASE_DIR, OUTPUT_DIR) if not os.path.isabs(OUTPUT_DIR) else OUTPUT_DIR
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

FONT_PATH = os.path.join(BASE_DIR, "NotoSansDevanagari-Regular.ttf")
if os.path.exists(FONT_PATH) and os.path.getsize(FONT_PATH) < 100000:
    os.remove(FONT_PATH)
if not os.path.exists(FONT_PATH):
    try:
        r = requests.get("https://raw.githubusercontent.com/google/fonts/main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf", timeout=60)
        open(FONT_PATH, "wb").write(r.content)
    except: pass

# OCR Engine
engine = RapidOCR()

app = Client("ocr_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def clean_text(t): return re.sub(r"\n{3,}","\n\n",t.replace("\x00","")).strip()

async def translate_text(text, status_msg):
    chunks = [text[i:i+800] for i in range(0, len(text), 800)]
    out=[]
    for idx,ch in enumerate(chunks):
        try:
            tr = await asyncio.to_thread(GoogleTranslator(source="en", target="hi").translate, ch)
            out.append(tr if tr else ch)
        except: out.append(ch)
        await asyncio.sleep(0.8)
        try: await status_msg.edit_text(f"🌐 Translate: {idx+1}/{len(chunks)}")
        except: pass
    return "\n".join(out)

def extract_with_rapidocr(pdf_path):
    doc = fitz.open(pdf_path)
    full=""
    for page in doc:
        txt = page.get_text("text").strip()
        if len(txt) > 80:
            full+=txt+"\n\n"
        else:
            pix = page.get_pixmap(dpi=250)
            img_bytes = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_bytes))
            result, _ = engine(np.array(img))
            if result:
                page_text = " ".join([line[1] for line in result])
                full+=page_text+"\n\n"
    doc.close()
    return full

def create_pdf(text, output_path):
    pdf=FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.add_font("NotoHindi","",FONT_PATH, uni=True)
    pdf.set_font("NotoHindi", size=11)
    for para in text.split("\n"):
        if not para.strip(): pdf.ln(4); continue
        pdf.multi_cell(0,7,para.strip())
    pdf.output(output_path)

@app.on_message(filters.command("start"))
async def start(c,m): await m.reply_text("🇮🇳 Scanned CLC/NRTS/NEET → Hindi bot ready. PDF bhejo.")

@app.on_message(filters.document)
async def pdf_handler(c,m):
    if not m.document.file_name.lower().endswith(".pdf"): return
    status = await m.reply_text("📥 Download...")
    inp = os.path.join(DOWNLOAD_DIR, m.document.file_name)
    outp = os.path.join(OUTPUT_DIR, "Hindi_"+m.document.file_name)
    try:
        await m.download(inp)
        await status.edit_text("🔍 Scanned OCR padh raha hu...")
        original = await asyncio.to_thread(extract_with_rapidocr, inp)
        original = clean_text(original)
        if len(original)<30:
            await status.edit_text("❌ Text nahi mila"); return
        await status.edit_text(f"📖 {len(original)} chars mile, Hindi translate...")
        hindi = await translate_text(original, status)
        await status.edit_text("📝 PDF bana raha hu...")
        await asyncio.to_thread(create_pdf, hindi, outp)
        await m.reply_document(outp, caption="🇮🇳 Hindi Test Ready ✅")
        await status.delete()
    except Exception as e:
        print(e); await status.edit_text(f"❌ {e}")
    finally:
        for p in [inp,outp]:
            if os.path.exists(p): os.remove(p)

print("Bot Started - RapidOCR")
app.run()
