import os
import re
import asyncio

import fitz  # PyMuPDF
from pyrogram import Client, filters
from deep_translator import GoogleTranslator
from fpdf import FPDF

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    DOWNLOAD_DIR,
    OUTPUT_DIR,
    FONT_PATH,
)


# =========================
# FOLDERS
# =========================

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# =========================
# CHECK FONT
# =========================

if not os.path.exists(FONT_PATH):
    raise FileNotFoundError(
        f"Font file nahi mili: {FONT_PATH}"
    )

font_size = os.path.getsize(FONT_PATH)

if font_size < 100000:
    raise ValueError(
        "NotoSansDevanagari-Regular.ttf actual font file nahi lag rahi."
    )


# =========================
# BOT
# =========================

app = Client(
    "EnglishHindiPDFBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)


# =========================
# START
# =========================

@app.on_message(filters.command("start"))
async def start(_, message):
    await message.reply_text(
        "🇮🇳 **English → Hindi PDF Bot**\n\n"
        "English PDF bhejiye.\n"
        "Main uska text Hindi me translate karke "
        "nayi PDF bana dunga. 📄➡️🇮🇳"
    )


# =========================
# TEXT CLEAN
# =========================

def clean_text(text):
    if not text:
        return ""

    text = text.replace("\x00", "")
    text = text.replace("\r", "\n")

    # Extra spaces
    text = re.sub(r"[ \t]+", " ", text)

    # Too many blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# =========================
# TRANSLATE
# =========================

def translate_text(text):
    translator = GoogleTranslator(
        source="en",
        target="hi"
    )

    # Paragraph based chunks
    paragraphs = text.split("\n\n")

    translated = []

    for paragraph in paragraphs:

        paragraph = paragraph.strip()

        if not paragraph:
            continue

        # Google translator ke liye chhote chunks
        chunks = []

        while len(paragraph) > 2500:
            cut = paragraph.rfind(" ", 0, 2500)

            if cut < 500:
                cut = 2500

            chunks.append(paragraph[:cut])
            paragraph = paragraph[cut:].strip()

        if paragraph:
            chunks.append(paragraph)

        for chunk in chunks:

            result = None

            for attempt in range(3):

                try:
                    result = translator.translate(chunk)

                    if result:
                        break

                except Exception:
                    awaitable = asyncio.sleep(1)
                    try:
                        asyncio.run(awaitable)
                    except Exception:
                        pass

            if result:
                translated.append(result)
            else:
                translated.append(chunk)

    return "\n\n".join(translated)


# =========================
# SAFE LINE
# =========================

def split_long_line(line, max_chars=90):
    """
    Bahut long URL/word ki wajah se
    FPDF horizontal-space error na aaye.
    """

    if len(line) <= max_chars:
        return [line]

    parts = []

    while len(line) > max_chars:
        parts.append(line[:max_chars])
        line = line[max_chars:]

    if line:
        parts.append(line)

    return parts


# =========================
# CREATE PDF
# =========================

def create_pdf(text, output_file):

    pdf = FPDF()

    pdf.set_auto_page_break(
        auto=True,
        margin=15
    )

    pdf.add_page()

    # Hindi font
    pdf.add_font(
        "Noto",
        "",
        FONT_PATH
    )

    pdf.set_font(
        "Noto",
        size=12
    )

    # Title
    pdf.set_font(
        "Noto",
        size=16
    )

    pdf.multi_cell(
        0,
        10,
        "English to Hindi Translation"
    )

    pdf.ln(4)

    pdf.set_font(
        "Noto",
        size=12
    )

    lines = text.split("\n")

    for line in lines:

        line = line.strip()

        if not line:
            pdf.ln(5)
            continue

        safe_lines = split_long_line(line)

        for safe_line in safe_lines:

            pdf.multi_cell(
                0,
                7,
                safe_line
            )

    pdf.output(output_file)


# =========================
# PDF HANDLER
# =========================

@app.on_message(filters.document)
async def pdf_handler(client, message):

    document = message.document

    if not document.file_name.lower().endswith(".pdf"):
        await message.reply_text(
            "❌ Sirf PDF file bhejiye."
        )
        return

    status = await message.reply_text(
        "📥 PDF download ho rahi hai..."
    )

    input_file = os.path.join(
        DOWNLOAD_DIR,
        f"{message.id}.pdf"
    )

    output_file = os.path.join(
        OUTPUT_DIR,
        f"Hindi_{message.id}.pdf"
    )

    try:

        # =========================
        # DOWNLOAD
        # =========================

        await client.download_media(
            message,
            file_name=input_file
        )

        # =========================
        # READ PDF
        # =========================

        await status.edit_text(
            "📖 PDF ka text read ho raha hai..."
        )

        doc = fitz.open(input_file)

        all_text = []

        total_pages = len(doc)

        for page_number, page in enumerate(doc, start=1):

            text = page.get_text("text")

            text = clean_text(text)

            if text:
                all_text.append(text)

            if page_number % 5 == 0:
                try:
                    await status.edit_text(
                        f"📖 Reading PDF...\n"
                        f"Page: {page_number}/{total_pages}"
                    )
                except Exception:
                    pass

        doc.close()

        original_text = "\n\n".join(all_text)

        if not original_text.strip():

            await status.edit_text(
                "❌ Is PDF me selectable text nahi mila.\n\n"
                "Ye scanned/image PDF ho sakti hai."
            )

            return

        # =========================
        # TRANSLATION
        # =========================

        await status.edit_text(
            "🔄 English → Hindi translation start...\n\n"
            f"📄 Pages: {total_pages}"
        )

        translated_text = await asyncio.to_thread(
            translate_text,
            original_text
        )

        if not translated_text.strip():

            await status.edit_text(
                "❌ Translation se text nahi mila."
            )

            return

        # =========================
        # CREATE PDF
        # =========================

        await status.edit_text(
            "📄 Hindi PDF ban rahi hai..."
        )

        await asyncio.to_thread(
            create_pdf,
            translated_text,
            output_file
        )

        # =========================
        # SEND
        # =========================

        await status.edit_text(
            "📤 Hindi PDF upload ho rahi hai..."
        )

        await message.reply_document(
            output_file,
            caption=(
                "🇮🇳 **English → Hindi PDF**\n\n"
                "✅ Translation Complete\n"
                f"📄 Pages: {total_pages}"
            )
        )

        await status.delete()

    except Exception as e:

        print("ERROR:", repr(e))

        try:
            await status.edit_text(
                "❌ Error aa gaya:\n\n"
                f"`{str(e)[:3000]}`"
            )
        except Exception:
            pass

    finally:

        # =========================
        # CLEAN FILES
        # =========================

        try:
            if os.path.exists(input_file):
                os.remove(input_file)
        except Exception:
            pass

        try:
            if os.path.exists(output_file):
                os.remove(output_file)
        except Exception:
            pass


# =========================
# RUN
# =========================

print("🇮🇳 English → Hindi PDF Bot Started!")

app.run()
