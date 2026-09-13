import os,re,asyncio,requests,fitz,io
from PIL import Image
import pytesseract
from pyrogram import Client,filters
from deep_translator import GoogleTranslator
from fpdf import FPDF
from config import API_ID,API_HASH,BOT_TOKEN,DOWNLOAD_DIR,OUTPUT_DIR
BASE_DIR=os.path.dirname(os.path.abspath(__file__))
FONT_PATH=os.path.join(BASE_DIR,"NotoSansDevanagari-Regular.ttf")
def ensure_font():
 try:
  if os.path.exists(FONT_PATH) and os.path.getsize(FONT_PATH)>50000:return True
 except:pass
 for url in ["https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf"]:
  try:
   r=requests.get(url,timeout=60)
   if len(r.content)>50000:open(FONT_PATH,"wb").write(r.content);return True
  except:pass
 return False
ensure_font()
app=Client("ocr_bot",api_id=API_ID,api_hash=API_HASH,bot_token=BOT_TOKEN)
def clean_text(t):return re.sub(r"\n{3,}", "\n\n", t).strip()
async def translate_text(text,msg):
 chs=[text[i:i+800] for i in range(0,len(text),800)];out=[]
 for idx,ch in enumerate(chs):
  try:out.append(await asyncio.to_thread(GoogleTranslator(source="en",target="hi").translate,ch))
  except:out.append(ch)
  await asyncio.sleep(0.5)
 return "\n".join(out)
def extract_text(pdf_path):
 doc=fitz.open(pdf_path);full=""
 for page in doc:
  txt=page.get_text("text").strip()
  if len(txt)>50:full+=txt+"\n\n"
  else:
   pix=page.get_pixmap(dpi=300);img=Image.open(io.BytesIO(pix.tobytes("png")))
   try:full+=pytesseract.image_to_string(img,lang='eng')+"\n\n"
   except:pass
 doc.close();return full
def create_pdf(text,output_path):
 pdf=FPDF();pdf.set_auto_page_break(auto=True,margin=15);pdf.add_page()
 try:
  if os.path.exists(FONT_PATH):pdf.add_font("NotoHindi","",FONT_PATH,uni=True);pdf.set_font("NotoHindi",size=11)
  else:pdf.set_font("Helvetica",size=11)
 except:pdf.set_font("Helvetica",size=11)
 for para in text.split("\n"):
  if not para.strip():pdf.ln(4);continue
  try:pdf.multi_cell(0,7,para.strip())
  except:pdf.multi_cell(0,7,para.strip().encode('ascii','ignore').decode())
 pdf.output(output_path)
@app.on_message(filters.command("start"))
async def start(c,m):await m.reply_text("Bot Ready PDF bhejo")
@app.on_message(filters.document)
async def pdf_handler(c,m):
 if not m.document.file_name.lower().endswith(".pdf"):return
 status=await m.reply_text("Download...")
 inp=os.path.join(DOWNLOAD_DIR,m.document.file_name);outp=os.path.join(OUTPUT_DIR,"Hindi_"+m.document.file_name)
 try:
  await m.download(inp);await status.edit_text("Padh raha hu...")
  original=await asyncio.to_thread(extract_text,inp);original=clean_text(original)
  if len(original)<20:await status.edit_text("Text nahi mila");return
  await status.edit_text("Translate...");hindi=await translate_text(original,status)
  await status.edit_text("PDF bana raha hu...");await asyncio.to_thread(create_pdf,hindi,outp)
  await m.reply_document(outp,caption="Hindi Ready");await status.delete()
 except Exception as e:print(e);await status.edit_text(f"Error {e}")
 finally:
  for p in [inp,outp]:
   if os.path.exists(p):
    try:os.remove(p)
    except:pass
print("Bot Started");app.run()
