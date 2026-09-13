import os
import re
import asyncio

import fitz  # PyMuPDF
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
        "📄 Mujhe English PDF bhejo.\n"
        "🔄 Main automatically English ko Hindi mein translate karunga.\n"
        "📑 Aur Hindi PDF bana kar wapas dunga.\n\n"
        "बस PDF भेजें ✅"
    )


# =========================
# TEXT CLEANING
# =========================

def clean_text(text):
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# =========================
# TRANSLATE
# =========================

async def translate_text(text):

    translator = GoogleTranslator(
        source="en",
        target="hi"
    )

    # छोटे chunks में translation
    chunks = []

    while len(text) > 3500:
        cut = text.rfind(" ", 0, 3500)

        if cut == -1:
            cut = 3500

        chunks.append(text[:cut])
        text = text[cut:]

    if text:
        chunks.append(text)

    translated_parts = []

    for chunk in chunks:

        for attempt in range(3):

            try:
                result = await asyncio.to_thread(
                    translator.translate,
                    chunk
                )

                translated_parts.append(result)
                break

            except Exception as e:

                if attempt == 2:
                    raise e

                await asyncio.sleep(2)

    return "\n".join(translated_parts)


# =========================
# CREATE HINDI PDF
# =========================

def create_pdf(translated_pages, output_file):

    if not os.path.exists(FONT_PATH):
        raise FileNotFoundError(
            "NotoSansDevanagari-Regular.ttf repo mein nahi mili."
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

    for page_number, page_text in enumerate(translated_pages):

        pdf.add_page()

        lines = page_text.split("\n")

        for line in lines:

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

        # =========================
        # DOWNLOAD
        # =========================

        await client.download_media(
            message,
            file_name=input_file
        )

        await status.edit_text(
            "📥 **PDF received...**\n\n"
            "🔄 English → Hindi translation start..."
        )

        # =========================
        # OPEN PDF
        # =========================

        doc = fitz.open(input_file)

        translated_pages = []

        total_pages = len(doc)

        for index, page in enumerate(doc):

            text = page.get_text("text")

            text = clean_text(text)

            if not text:

                translated_pages.append(
                    "⚠️ Is page par readable text nahi mila."
                )

                continue

            translated = await translate_text(text)

            translated_pages.append(translated)

            await status.edit_text(
                f"🔄 **English → Hindi translation...**\n\n"
                f"📄 Page: **{index + 1}/{total_pages}**"
            )

        doc.close()

        # =========================
        # CREATE PDF
        # =========================

        await status.edit_text(
            "📑 **Hindi PDF banayi ja rahi hai...**"
        )

        await asyncio.to_thread(
            create_pdf,
            translated_pages,
            output_file
        )

        # =========================
        # SEND PDF
        # =========================

        await message.reply_document(
            document=output_file,
            caption=(
                "🇮🇳 **English → Hindi PDF**\n\n"
                "✅ Translation complete!"
            )
        )

        await status.delete()

    except Exception as e:

        await status.edit_text(
            "❌ **Error aa gaya:**\n\n"
            f"`{str(e)}`"
        )

    finally:

        # Temporary input PDF delete
        if os.path.exists(input_file):

            try:
                os.remove(input_file)
            except:
                pass

        # Output PDF delete after sending
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
