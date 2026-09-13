import os
import re
import asyncio
import urllib.request

from pyrogram import Client, filters
from pyrogram.types import Message
from pypdf import PdfReader
from deep_translator import GoogleTranslator
from fpdf import FPDF


# ================= CONFIG =================

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

DOWNLOAD_DIR = "downloads"
OUTPUT_DIR = "output"

FONT_URL = (
    "https://github.com/notofonts/devanagari/raw/main/"
    "NotoSansDevanagari/googlefonts/ttf/"
    "NotoSansDevanagari-Regular.ttf"
)

FONT_PATH = "NotoSansDevanagari-Regular.ttf"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ================= BOT =================

app = Client(
    "english_hindi_pdf_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


# ================= FONT =================

def download_font():
    if not os.path.exists(FONT_PATH):
        urllib.request.urlretrieve(FONT_URL, FONT_PATH)


# ================= TEXT CLEANING =================

def clean_text(text):
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ================= TRANSLATION =================

def translate_text(text):
    translator = GoogleTranslator(
        source="en",
        target="hi"
    )

    # Google Translate has text-length limitations.
    chunks = []

    words = text.split()
    current = ""

    for word in words:
        if len(current) + len(word) + 1 > 3500:
            chunks.append(current)
            current = word
        else:
            current += " " + word

    if current:
        chunks.append(current)

    translated = []

    for chunk in chunks:
        try:
            result = translator.translate(chunk)
            translated.append(result)
        except Exception:
            translated.append(chunk)

    return "\n\n".join(translated)


# ================= PDF CREATOR =================

def create_hindi_pdf(text, output_file):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.add_page()

    pdf.add_font(
        "NotoDevanagari",
        "",
        FONT_PATH
    )

    pdf.set_font(
        "NotoDevanagari",
        size=13
    )

    lines = text.split("\n")

    for line in lines:
        line = line.strip()

        if not line:
            pdf.ln(5)
            continue

        pdf.multi_cell(
            0,
            8,
            line
        )

    pdf.output(output_file)


# ================= START =================

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):

    await message.reply_text(
        "🇮🇳 **English → Hindi PDF Bot**\n\n"
        "📄 Mujhe English PDF bhejo.\n"
        "🔄 Main automatically English ko Hindi mein translate karunga.\n"
        "📑 Aur Hindi PDF bana kar wapas dunga.\n\n"
        "बस PDF भेजें ✅"
    )


# ================= PDF =================

@app.on_message(filters.document)
async def pdf_handler(client: Client, message: Message):

    file_name = message.document.file_name or ""

    if not file_name.lower().endswith(".pdf"):
        await message.reply_text(
            "❌ Sirf **PDF file** bhejo."
        )
        return

    status = await message.reply_text(
        "📥 **PDF received...**\n\n"
        "⏳ Download ho rahi hai..."
    )

    input_path = None
    output_path = None

    try:

        input_path = os.path.join(
            DOWNLOAD_DIR,
            file_name
        )

        await message.download(
            file_name=input_path
        )

        await status.edit_text(
            "📖 **PDF read ho rahi hai...**"
        )

        reader = PdfReader(input_path)

        all_text = []

        for page in reader.pages:
            page_text = page.extract_text()

            if page_text:
                all_text.append(page_text)

        english_text = "\n\n".join(all_text)

        if not english_text.strip():

            await status.edit_text(
                "❌ Is PDF se text nahi mil paya.\n\n"
                "Ye scanned/image PDF ho sakti hai."
            )
            return

        await status.edit_text(
            "🔄 **English → Hindi translation...**\n\n"
            "⏳ Thoda time lagega."
        )

        hindi_text = await asyncio.to_thread(
            translate_text,
            clean_text(english_text)
        )

        await status.edit_text(
            "📑 **Hindi PDF ban rahi hai...**"
        )

        download_font()

        base_name = os.path.splitext(file_name)[0]

        output_path = os.path.join(
            OUTPUT_DIR,
            f"{base_name}_Hindi.pdf"
        )

        await asyncio.to_thread(
            create_hindi_pdf,
            hindi_text,
            output_path
        )

        await status.edit_text(
            "✅ **Translation complete!**\n\n"
            "📤 Hindi PDF bhej raha hoon..."
        )

        await message.reply_document(
            document=output_path,
            caption=(
                "🇮🇳 **Hindi PDF तैयार है!**\n\n"
                "English → Hindi ✅"
            )
        )

        await status.delete()

    except Exception as e:

        await status.edit_text(
            "❌ **Error aa gaya:**\n\n"
            f"`{str(e)[:3000]}`"
        )

    finally:

        try:
            if input_path and os.path.exists(input_path):
                os.remove(input_path)

            if output_path and os.path.exists(output_path):
                os.remove(output_path)

        except Exception:
            pass


print("🇮🇳 English → Hindi PDF Bot Started!")

app.run()
