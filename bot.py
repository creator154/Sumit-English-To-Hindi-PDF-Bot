import os, re, asyncio, requests, fitz, io
import numpy as np
from PIL import Image
from pyrogram import Client, filters
from deep_translator import GoogleTranslator
from fpdf import FPDF
from config import API_ID, API_HASH, BOT_TOKEN, DOWNLOAD_DIR, OUTPUT_DIR

# Try EasyOCR first (Google jaisa), nahi to Tesseract
try:
    import easyocr
    READER = easyocr.Reader(['en','hi'], gpu=False)
    USE_EASY = True
    print("Using EasyOCR")
except:
    import pytesseract
    USE_EASY = False
    print("Using Tesseract fallback")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, DOWNLOAD_DIR) if not os.path.isabs(DOWNLOAD_DIR) else DOWNLOAD_DIR
OUTPUT_DIR = os.path.join(BASE_DIR, OUTPUT_DIR) if not os.path.isabs(OUTPUT_DIR) else OUTPUT_DIR
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

FONT_PATH = os.path.join(BASE_DIR, "NotoSansDevanagari-Regular.ttf")

def ensure_font():
    if os.path.exists(FONT_PATH) and os.path.getsize(FONT_PATH) > 50000:
        return True
    try:
        r = requests.get("https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf", timeout=90)
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
        await asyncio.sleep(0.5)
        try: await status_msg.edit_text(f"Translate {idx+1}/{len(chunks)}")
        except: pass
    return "\n".join(out)

def extract_text_google(pdf_path):
    doc = fitz.open(pdf_path)
    full = ""
    for page in doc:
        # 1. Direct text if available
        txt = page.get_text("text").strip()
        if len(txt) > 100:
            full += txt + "\n\n"
            continue
        
        # 2. OCR for scanned
        pix = page.get_pixmap(dpi=400)
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))
        
        if USE_EASY:
            # EasyOCR - Google jaisa
            results = READER.readtext(np.array(img), detail=0, paragraph=True)
            ocr_txt = "\n".join(results)
        else:
            import cv2, pytesseract
            nparr = np.frombuffer(img_bytes, np.uint8)
            img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            ocr_txt = pytesseract.image_to_string(gray, lang='eng+hin', config='--psm 6')
        
        full += ocr_txt + "\n\n"
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
            pdf.multi_cell(0, 7, para.strip().encode('ascii','ignore').decode())
    pdf.output(output_path)

@app.on_message(filters.command("start"))
async def start(c,m):
    await m.reply_text("Bot Ready ✅ Google jaisa - Koi bhi PDF bhejo")

@app.on_message(filters.document)
async def pdf_handler(c,m):
    if not m.document.file_name.lower().endswith(".pdf"):
        return
    status = await m.reply_text("Download...")
    inp = os.path.join(DOWNLOAD_DIR, m.document.file_name)
    outp = os.path.join(OUTPUT_DIR, "Hindi_" + m.document.file_name)
    try:
        await m.download(inp)
        await status.edit_text("Padh raha hu... (Google OCR)")
        original = await asyncio.to_thread(extract_text_google, inp)
        original = clean_text(original)
        print(f"Extracted {len(original)} chars")
        if len(original) < 20:
            await status.edit_text("❌ Isme text bahut halka hai, fir bhi try kar raha hu...")
        await status.edit_text(f"{len(original)} chars mile, Hindi me badal raha hu...")
        hindi = await translate_text(original, status)
        await status.edit_text("PDF bana raha hu...")
        await asyncio.to_thread(create_pdf, hindi, outp)
        await m.reply_document(outp, caption="✅ Hindi PDF Ready - Google Style")
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

print("Bot Started - Google Style")
app.run()
