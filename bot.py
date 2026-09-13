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
        await asyncio.sleep(0.3)
    return "\n".join(out)

def extract_with_images(pdf_path):
    doc = fitz.open(pdf_path)
    original_images = []
    texts_per_page = []
    for page in doc:
        pix = page.get_pixmap(dpi=250)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        original_images.append(img)
        
        txt = page.get_text("text").strip()
        if len(txt) < 50:
            img_bytes = pix.tobytes("png")
            nparr = np.frombuffer(img_bytes, np.uint8)
            img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            img_cv = cv2.resize(img_cv, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            gray = cv2.medianBlur(gray, 3)
            _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            try:
                txt = pytesseract.image_to_string(gray, lang='eng+hin', config='--psm 6 --oem 3')
            except:
                txt = ""
        texts_per_page.append(txt)
    doc.close()
    return original_images, texts_per_page

def create_pdf(original_pages, translated_texts, output_path):
    pdf = FPDF(orientation='L', format='A4')
    pdf.set_auto_page_break(auto=False)
    try:
        if os.path.exists(FONT_PATH) and os.path.getsize(FONT_PATH) > 50000:
            pdf.add_font("NotoHindi", "", FONT_PATH, uni=True)
            font = "NotoHindi"
        else:
            font = "Helvetica"
    except:
        font = "Helvetica"

    for idx, (orig_img, trans_text) in enumerate(zip(original_pages, translated_texts)):
        pdf.add_page()
        temp_path = f"/tmp/orig_{idx}.png"
        orig_img.save(temp_path)
        pdf.image(temp_path, x=5, y=5, w=140, h=190)
        pdf.rect(5, 5, 140, 200)
        pdf.rect(148, 5, 144, 200)
        pdf.set_xy(150, 10)
        pdf.set_font(font, size=10)
        for para in trans_text.split("\n"):
            if not para.strip():
                pdf.ln(3)
                continue
            if pdf.get_y() > 190:
                break
            try:
                pdf.multi_cell(140, 6, para.strip())
            except:
                pdf.multi_cell(140, 6, para.strip().encode('ascii','ignore').decode())
            pdf.set_x(150)
        if os.path.exists(temp_path):
            os.remove(temp_path)
    pdf.output(output_path)

@app.on_message(filters.command("start"))
async def start(c,m):
    await m.reply_text("Bot Ready ✅\nLeft Original | Right Hindi jaisa us repo me hai\nKoi bhi PDF bhejo")

@app.on_message(filters.document)
async def pdf_handler(c,m):
    if not m.document.file_name.lower().endswith(".pdf"):
        return
    status = await m.reply_text("Download...")
    inp = os.path.join(DOWNLOAD_DIR, m.document.file_name)
    outp = os.path.join(OUTPUT_DIR, "Hindi_" + m.document.file_name)
    try:
        await m.download(inp)
        await status.edit_text("Padh raha hu...")
        orig_imgs, texts = await asyncio.to_thread(extract_with_images, inp)
        hindi_texts = []
        for i, t in enumerate(texts):
            t = clean_text(t)
            if len(t) < 10:
                hindi_texts.append("")
                continue
            await status.edit_text(f"Page {i+1}/{len(texts)} translate...")
            ht = await translate_text(t, status)
            hindi_texts.append(ht)
        
        await status.edit_text("Side-by-side PDF bana raha hu...")
        await asyncio.to_thread(create_pdf, orig_imgs, hindi_texts, outp)
        await m.reply_document(outp, caption="✅ Left Original | Right Hindi")
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

print("Bot Started - Side by Side")
app.run()
