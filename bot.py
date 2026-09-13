hereimport os
import re
import asyncio

import fitz
from pyrogram import Client, filters
from pyrogram.types import Message
from deep_translator import GoogleTranslator
from fpdf import FPDF


# =========================
# CONFIG
# =========================

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

DOWNLOAD_DIR = "downloads"
OUTPUT_DIR = "output"

FONT_PATH = "NotoSansDevanagari-Regular.ttf"


# =========================
# FOLDERS
# =========================

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# =========================
# BOT
# =========================

app = Client(
    "EnglishHindiPDFBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


# =========================
# START
# =========================

@app.on_message(filters.command("start"))
async def start(client, message: Message):

    await message.reply_text(
        "🇮🇳 **English → Hindi PDF Bot**\n\n"
        "📄 English PDF bhejo.\n"
        "🔄 Main usko Hindi mein translate karunga.\n"
        "📑 Aur Hindi PDF bana kar wapas dunga.\n\n"
        "बस PDF भेजें ✅"
    )


# =========================
# CLEAN TEXT
# =========================

def clean_text(text):

    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# =========================
# SPLIT TEXT
# =========================

def split_text(text, max_length=1800):

    chunks = []

    while len(text) > max_length:

        cut = text.rfind(" ", 0, max_length)

        if cut < 500:
            cut = max_length

        chunks.append(text[:cut].strip())
        text = text[cut:].strip()

    if text:
        chunks.append(text)

    return chunks


# =========================
# TRANSLATE ONE CHUNK
# =========================

async def translate_chunk(chunk):

    for attempt in range(4):

        try:

            translator = GoogleTranslator(
                source="en",
                target="hi"
            )

            result = await asyncio.to_thread(
                translator.translate,
                chunk
            )

            if result and result.strip():

                return result.strip()

        except Exception:

            if attempt < 3:
                await asyncio.sleep(3)

    # Agar translation fail ho
    return chunk


# =========================
# TRANSLATE PAGE
# =========================

async def translate_text(text):

    chunks = split_text(text, 1800)

    translated_parts = []

    for chunk in chunks:

        result = await translate_chunk(chunk)

        translated_parts.append(result)

        # Google rate-limit se bachne ke liye
        await asyncio.sleep(0.8)

    return "\n".join(translated_parts)


# =========================
# CREATE PDF
# =========================

def create_pdf(translated_pages, output_file):

    if not os.path.exists(FONT_PATH):

        raise FileNotFoundError(
            "NotoSansDevanagari-Regular.ttf file nahi mili."
        )

    pdf = FPDF()

    pdf.set_auto_page_break(
        auto=True,
        margin=15
    )

    pdf.add_font(
        "NotoDevanagari",
        "",
        FONT_PATH
    )

    pdf.set_font(
        "NotoDevanagari",
        size=12
    )

    for page_text in translated_pages:

        pdf.add_page()

        for line in page_text.split("\n"):

            line = line.strip()

            if not line:

                pdf.ln(4)
                continue

            pdf.multi_cell(
                0,
                7,
                line
            )

    pdf.output(output_file)


# =========================
# PDF HANDLER
# =========================

@app.on_message(filters.document)
async def pdf_handler(client, message: Message):

    document = message.document

    if not document.file_name.lower().endswith(".pdf"):

        await message.reply_text(
            "❌ Sirf PDF file bhejiye."
        )

        return

    status = await message.reply_text(
        "📥 **PDF received...**\n\n"
        "⏳ Download ho rahi hai..."
    )

    input_file = os.path.join(
        DOWNLOAD_DIR,
        document.file_name
    )

    output_name = (
        os.path.splitext(document.file_name)[0]
        + "_Hindi.pdf"
    )

    output_file = os.path.join(
        OUTPUT_DIR,
        output_name
    )

    try:

        # Download
        await client.download_media(
            message,
            file_name=input_file
        )

        # Open PDF
        doc = fitz.open(input_file)

        total_pages = len(doc)

        translated_pages = []

        for index, page in enumerate(doc):

            await status.edit_text(
                f"🔄 **English → Hindi Translation**\n\n"
                f"📄 Page: **{index + 1}/{total_pages}**"
            )

            text = page.get_text("text")

            text = clean_text(text)

            if not text:

                translated_pages.append(
                    "⚠️ Is page par readable text nahi mila."
                )

                continue

            translated = await translate_text(text)

            translated_pages.append(translated)

        doc.close()

        # Create PDF
        await status.edit_text(
            "📑 **Hindi PDF banayi ja rahi hai...**"
        )

        await asyncio.to_thread(
            create_pdf,
            translated_pages,
            output_file
        )

        # Send
        await message.reply_document(
            document=output_file,
            caption=(
                "🇮🇳 **English → Hindi PDF**\n\n"
                "✅ Translation Complete!"
            )
        )

        await status.delete()

    except Exception as e:

        await status.edit_text(
            "❌ **Error aa gaya:**\n\n"
            f"`{str(e)}`"
        )

    finally:

        if os.path.exists(input_file):

            try:
                os.remove(input_file)
            except:
                pass

        if os.path.exists(output_file):

            try:
                os.remove(output_file)
            except:
                pass


# =========================
# RUN
# =========================

print("🇮🇳 English → Hindi PDF Bot Started!")

app.run()
