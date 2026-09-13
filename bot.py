import os, re, asyncio, requests, fitz, io
import cv2
import numpy as np
from PIL import Image
import pytesseract
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

def ensure_font():
    if os.path.exists(FONT_PATH):
        try:
            if os.path.getsize(FONT_PATH) > 50000:
                return True
        except: pass
    urls = [
        "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf",
    ]
    for url in urls:
        try:
            r = requests.get(url, timeout=90)
            if len(r.content) > 50000:
                open(FONT_PATH, "wb").write(r.content)
                return True
        except: pass
    return False

ensure_font()

app = Client("ocr_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def clean_text(t):
    return re.sub(r"\n{3,}", "\n\n", t.replace("\x00","")).strip()

async def translate_text(text, status_msg):
    chunks = [text[i:i+800] for i in range(0, len(text), 800)]
    out=[]
    for idx,ch in enumerate(chunks):
        try:
            tr = await asyncio.to_thread(GoogleTranslator(source="en", target="hi").translate, ch)
            out.append(tr if tr else ch)
        except:
            out.append(ch)
        await asyncio.sleep(0.8)
        try: await status_msg.edit_text(f"Translate {idx+1}/{len(chunks)}")
        except: pass
    return "\n".join(out)

def extract_text(pdf_path):
    doc = fitz.open(pdf_path)
    full = ""
    for page_num, page in enumerate(doc):
        txt = page.get_text("text").strip()
        if len(txt) > 20:
            full += txt + "\n\n"
        pix = page.get_pixmap(dpi=400)
        img_bytes = pix.tobytes("png")
        nparr = np.frombuffer(img_bytes, np.uint8)
        img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 3)
        try:
            ocr_txt = pytesseract.image_to_string(gray, lang='eng', config='--psm 3')
            if len(ocr_txt.strip()) > 10:
                full += ocr_txt + "\n\n"
        except Exception as e:
            print(f"OCR fail {e}")
    doc.close()
    return full

def create_pdf(text, output_path):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    try:
        if os.path.exists(FONT_PATH) and os.path.getsize(FONT_PATH) > 50000:
            pdf.add_font("NotoHindi", "", FONT_PATH, uni=True)
            pdf.set_font("NotoHindi", size=11)
        else:
            pdf.set_font("Helvetica", size=11)
    except:
        pdf.set_font("Helvetica", size=11)
    for para in text.split("\n"):
        if not para.strip():
            pdf.ln(4)
            continue
        try:
            pdf.multi_cell(0, 7, para.strip())
        except:
            safe = para.strip().encode('ascii','ignore').decode()
            pdf.multi_cell(0, 7, safe)
    pdf.output(output_path)

@app.on_message(filters.command("start"))
async def start(c,m):
    await m.reply_text("Bot Ready ✅ PDF bhejo (Scanned bhi chalega)")

@app.on_message(filters.document)
async def pdf_handler(c,m):
    if not m.document.file_name.lower().endswith(".pdf"):
        return
    status = await m.reply_text("Download...")
    inp = os.path.join(DOWNLOAD_DIR, m.document.file_name)
    outp = os.path.join(OUTPUT_DIR, "Hindi_" + m.document.file_name)
    try:
        await m.download(inp)
        await status.edit_text("PDF padh raha hu...")
        original = await asyncio.to_thread(extract_text, inp)
        original = clean_text(original)
        if len(original) < 20:
            await status.edit_text("❌ Text nahi mila. PDF blank hai ya image bahut kharab hai.")
            return
        await status.edit_text(f"{len(original)} chars mile, Hindi me badal raha hu...")
        hindi = await translate_text(original, status)
        await status.edit_text("Hindi PDF bana raha hu...")
        await asyncio.to_thread(create_pdf, hindi, outp)
        await m.reply_document(outp, caption="✅ Hindi PDF Ready")
        await status.delete()
    except Exception as e:
        print(e)
        try: await status.edit_text(f"Error: {e}")
        except: pass
    finally:
        for p in [inp,outp]:
            if os.path.exists(p):
                try: os.remove(p)
                except: pass

print("Bot Started")
app.run()
