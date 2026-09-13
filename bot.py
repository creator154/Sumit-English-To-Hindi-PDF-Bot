import os, re, asyncio, requests, fitz, io, base64
import numpy as np
import cv2
from PIL import Image
from pyrogram import Client, filters
from deep_translator import GoogleTranslator
from fpdf import FPDF
from config import API_ID, API_HASH, BOT_TOKEN, DOWNLOAD_DIR, OUTPUT_DIR

# Free OCR.Space API key - tera khud ka https://ocr.space pe free me le sakta hai
OCR_API_KEY = "K87899142388957" # helloworld demo key, limit 500/month

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, DOWNLOAD_DIR) if not os.path.isabs(DOWNLOAD_DIR) else DOWNLOAD_DIR
OUTPUT_DIR = os.path.join(BASE_DIR, OUTPUT_DIR) if not os.path.isabs(OUTPUT_DIR) else OUTPUT_DIR
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
FONT_PATH = os.path.join(BASE_DIR, "NotoSansDevanagari-Regular.ttf")

def ensure_font():
    if os.path.exists(FONT_PATH) and os.path.getsize(FONT_PATH) > 50000: return True
    try:
        r = requests.get("https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf", timeout=90)
        if len(r.content) > 50000:
            open(FONT_PATH, "wb").write(r.content)
            return True
    except: pass
    return False
ensure_font()

app = Client("ocr_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def clean_text(t): return re.sub(r"\n{3,}", "\n\n", t.replace("\x00","")).strip()

async def ocr_space_api(image_bytes):
    try:
        # API call
        def do_ocr():
            resp = requests.post("https://api.ocr.space/parse/image",
                data={"apikey": OCR_API_KEY, "language": "eng", "isOverlayRequired": False, "OCREngine": 2},
                files={"file": ("page.png", image_bytes, "image/png")}, timeout=60)
            j = resp.json()
            if j.get("ParsedResults"):
                return j["ParsedResults"][0].get("ParsedText","")
            return ""
        text = await asyncio.to_thread(do_ocr)
        return text
    except Exception as e:
        print("OCR API fail", e)
        return ""

async def translate_text(text):
    if len(text.strip()) < 10: return ""
    # Formula protect - agar formula jada hai to translate skip
    if len(re.findall(r"[=^°Ωαβμ\d\(\)/]", text)) > len(text)*0.4:
        return text
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    out=[]
    for ch in chunks:
        try:
            tr = await asyncio.to_thread(GoogleTranslator(source="en", target="hi").translate, ch)
            out.append(tr if tr else ch)
        except:
            out.append(ch)
        await asyncio.sleep(0.5)
    return "\n".join(out)

def extract_with_images(pdf_path):
    doc = fitz.open(pdf_path)
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=350) # High DPI for small text
        img_bytes = pix.tobytes("png")
        images.append(img_bytes)
    doc.close()
    return images

def create_side_by_side_pdf(original_pages_bytes, translated_texts, output_path):
    pdf = FPDF(orientation='L', format='A4')
    pdf.set_auto_page_break(auto=False)
    try:
        if os.path.exists(FONT_PATH) and os.path.getsize(FONT_PATH) > 50000:
            pdf.add_font("NotoHindi", "", FONT_PATH, uni=True)
            font = "NotoHindi"
        else: font = "Helvetica"
    except: font = "Helvetica"

    for idx, (orig_bytes, trans_text) in enumerate(zip(original_pages_bytes, translated_texts)):
        pdf.add_page()
        temp_path = f"/tmp/orig_{idx}.png"
        open(temp_path, "wb").write(orig_bytes)

        pdf.image(temp_path, x=5, y=5, w=137, h=195)
        pdf.rect(5, 5, 137, 195)
        pdf.rect(145, 5, 147, 195)
        pdf.set_xy(147, 8)
        pdf.set_font(font, size=9)

        if not trans_text.strip():
            pdf.set_xy(150, 90)
            pdf.multi_cell(140, 6, "Text detect nahi hua")
        else:
            for para in trans_text.split("\n"):
                if pdf.get_y() > 195: break
                if not para.strip(): pdf.ln(2); continue
                pdf.set_x(147)
                try: pdf.multi_cell(143, 5, para.strip())
                except: pdf.multi_cell(143, 5, para.strip().encode('ascii','ignore').decode())

        if os.path.exists(temp_path): os.remove(temp_path)
    pdf.output(output_path)

@app.on_message(filters.command("start"))
async def start(c,m):
    await m.reply_text("Bot Ready ✅ HEROKU VERSION\nLeft Original | Right Hindi\nOCR.Space API se chhota text bhi padhega\nPDF bhejo")

@app.on_message(filters.document)
async def pdf_handler(c,m):
    if not m.document.file_name.lower().endswith(".pdf"): return
    status = await m.reply_text("📥 Download...")
    inp = os.path.join(DOWNLOAD_DIR, m.document.file_name)
    outp = os.path.join(OUTPUT_DIR, "Hindi_" + m.document.file_name)
    try:
        await m.download(inp)
        await status.edit_text("🔍 High-quality OCR (API) se padh raha hu... 30sec lagega")
        orig_bytes_list = await asyncio.to_thread(extract_with_images, inp)

        hindi_texts = []
        for i, img_b in enumerate(orig_bytes_list):
            await status.edit_text(f"📖 Page {i+1}/{len(orig_bytes_list)} OCR...")
            eng_text = await ocr_space_api(img_b)
            eng_text = clean_text(eng_text)
            if len(eng_text) < 10:
                hindi_texts.append("")
                continue
            await status.edit_text(f"🌐 Page {i+1} Translate...")
            ht = await translate_text(eng_text)
            hindi_texts.append(ht)

        await status.edit_text("📄 Side-by-side PDF bana raha hu...")
        await asyncio.to_thread(create_side_by_side_pdf, orig_bytes_list, hindi_texts, outp)
        await m.reply_document(outp, caption="✅ Ho gaya - Heroku pe - Left Original | Right Hindi")
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

print("Bot Started - Heroku OCR.Space")
app.run()
