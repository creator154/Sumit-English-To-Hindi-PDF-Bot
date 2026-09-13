import os, requests, fitz, re
from pyrogram import Client, filters
from deep_translator import GoogleTranslator
from fpdf import FPDF

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OCR_API_KEY = os.environ.get("OCR_API_KEY", "K87899142388957")

FONT_PATH = "NotoSansDevanagari.ttf"
if not os.path.exists(FONT_PATH):
    url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Regular.ttf"
    open(FONT_PATH,'wb').write(requests.get(url).content)

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def ocr_space(file_path):
    with open(file_path, 'rb') as f:
        r = requests.post("https://api.ocr.space/parse/image",
            data={"apikey": OCR_API_KEY, "language": "eng", "OCREngine": 2, "scale": True},
            files={"file": f}, timeout=120)
        j = r.json()
        try: return j["ParsedResults"][0]["ParsedText"]
        except: return ""

def trans(text):
    try:
        if not text.strip(): return ""
        return GoogleTranslator(source='en', target='hi').translate(text[:4000])
    except Exception as e:
        print(e)
        return text

@app.on_message(filters.command("start"))
async def start(c,m): await m.reply_text("Bot Ready ✅ PDF bhejo")

@app.on_message(filters.document)
async def pdf_handler(c,m):
    if not m.document.file_name.lower().endswith(".pdf"): return
    s = await m.reply_text("📥 Download...")
    path = await m.download()
    doc = fitz.open(path)
    pdf = FPDF(orientation='L', format='A4')
    pdf.add_font("Hindi", "", FONT_PATH, uni=True)

    for i in range(len(doc)):
        await s.edit_text(f"Page {i+1}/{len(doc)} OCR + Hindi...")
        pix = doc[i].get_pixmap(dpi=200)
        img_path = f"page_{i}.png"
        pix.save(img_path)
        eng = ocr_space(img_path)
        hin = trans(eng)
        # A4 landscape 2 column
        pdf.add_page()
        pdf.set_font("Hindi", "", 9)
        pdf.multi_cell(138, 5, eng, border=1)
        pdf.set_xy(148, 10)
        pdf.multi_cell(138, 5, hin, border=1)
        os.remove(img_path)

    out = "Hindi_" + m.document.file_name
    pdf.output(out)
    await m.reply_document(out, caption="Ho gaya - Left Eng | Right Hindi")
    os.remove(path); os.remove(out)
    await s.delete()

app.run()
