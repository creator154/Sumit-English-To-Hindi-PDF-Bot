import os
import re
import asyncio

import fitz
from pyrogram import Client, filters
from deep_translator import GoogleTranslator
from fpdf import FPDF

from config import API_ID, API_HASH, BOT_TOKEN, DOWNLOAD_DIR, OUTPUT_DIR


# =========================
# DIRECTORIES
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DOWNLOAD_DIR = os.path.join(BASE_DIR, DOWNLOAD_DIR)
OUTPUT_DIR = os.path.join(BASE_DIR, OUTPUT_DIR)

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# =========================
# FIND FONT
# =========================

FONT_CANDIDATES = [
    "NotoSansDevanagari-Regular.ttf",
    "NotoSansDevanagari-Regular (6).ttf",
]

FONT_PATH = None

for filename in FONT_CANDIDATES:
    path = os.path.join(BASE_DIR, filename)

    if os.path.isfile(path):
        FONT_PATH = path
        break


if FONT_PATH is None:
    raise FileNotFoundError(
        "NotoSansDevanagari-Regular.ttf font repo me nahi mila."
    )


print("FONT FOUND:", FONT_PATH)


# =========================
# TELEGRAM BOT
# =========================

app = Client(
    "english_hindi_pdf_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


translator = GoogleTranslator(
    source="en",
    target="hi"
)


# =========================
# TEXT CLEAN
# =========================

def clean_text(text):
    if not text:
        return ""

    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# =========================
# SPLIT TRANSLATION
# =========================

def split_text(text, max_chars=1800):

    text = text.strip()

    if not text:
        return []

    chunks = []

    while len(text) > max_chars:

        cut = text.rfind("\n", 0, max_chars)

        if cut < 500:
            cut = text.rfind(" ", 0, max_chars)

        if cut < 500:
            cut = max_chars

        chunk = text[:cut].strip()

        if chunk:
            chunks.append(chunk)

        text = text[cut:].strip()

    if text:
        chunks.append(text)

    return chunks


# =========================
# TRANSLATION
# =========================

async def translate_text(text):

    chunks = split_text(text)

    result = []

    total = len(chunks)

    for index, chunk in enumerate(chunks, start=1):

        if not chunk.strip():
            continue

        try:

            translated = await asyncio.to_thread(
                translator.translate,
                chunk
            )

            if translated and translated.strip():
                result.append(translated)

            else:
                result.append(chunk)

        except Exception as e:

            print(
                f"Translation error {index}/{total}:",
                repr(e)
            )

            # Translation fail ho to original text rakho
            result.append(chunk)

        await asyncio.sleep(0.5)

    return "\n\n".join(result)


# =========================
# BREAK LONG WORDS
# =========================

def safe_lines(text, max_len=80):

    output = []

    for line in text.split("\n"):

        line = line.strip()

        if not line:
            output.append("")
            continue

        while len(line) > max_len:

            output.append(line[:max_len])

            line = line[max_len:]

        if line:
            output.append(line)

    return "\n".join(output)


# =========================
# CHECK HINDI CHARACTER
# =========================

def is_devanagari(char):

    code = ord(char)

    return (
        0x0900 <= code <= 0x097F
        or
        0xA8E0 <= code <= 0xA8FF
    )


# =========================
# CREATE PDF
# =========================

def create_pdf(text, output_path):

    text = clean_text(text)
    text = safe_lines(text)

    pdf = FPDF()

    pdf.set_auto_page_break(
        auto=True,
        margin=15
    )

    pdf.add_page()

    # Hindi font
    pdf.add_font(
        "NotoHindi",
        "",
        FONT_PATH
    )

    # Hindi font
    pdf.set_font(
        "NotoHindi",
        size=12
    )

    usable_width = (
        pdf.w - pdf.l_margin - pdf.r_margin
    )

    line_height = 7

    for line in text.split("\n"):

        if not line.strip():

            pdf.ln(4)

            continue

        # Split Hindi / English / numbers
        runs = []

        current = ""
        current_type = None

        for char in line:

            char_type = (
                "hindi"
                if is_devanagari(char)
                else "normal"
            )

            if current_type is None:

                current_type = char_type
                current = char

            elif char_type == current_type:

                current += char

            else:

                runs.append(
                    (current_type, current)
                )

                current_type = char_type
                current = char

        if current:
            runs.append(
                (current_type, current)
            )

        # If line contains only Hindi
        if all(
            item[0] == "hindi"
            for item in runs
        ):

            pdf.set_font(
                "NotoHindi",
                size=12
            )

            pdf.multi_cell(
                0,
                line_height,
                line,
                wrapmode="CHAR"
            )

            continue

        # Mixed text
        #
        # We render Hindi with Noto.
        # English/numbers with Helvetica.

        for run_type, run_text in runs:

            if run_type == "hindi":

                pdf.set_font(
                    "NotoHindi",
                    size=12
                )

            else:

                pdf.set_font(
                    "Helvetica",
                    size=12
                )

            # Break extremely long pieces
            pieces = []

            while len(run_text) > 60:

                pieces.append(
                    run_text[:60]
                )

                run_text = run_text[60:]

            if run_text:
                pieces.append(run_text)

            for piece in pieces:

                try:

                    pdf.write(
                        line_height,
                        piece
                    )

                except Exception as e:

                    print(
                        "PDF write error:",
                        repr(e)
                    )

        pdf.ln(line_height)

    pdf.output(output_path)


# =========================
# START
# =========================

@app.on_message(filters.command("start"))
async def start_handler(client, message):

    await message.reply_text(
        "🇮🇳 **English → Hindi PDF Bot**\n\n"
        "English PDF bhejo.\n\n"
        "Main uska Hindi translated PDF "
        "bana kar bhej dunga."
    )


# =========================
# PDF HANDLER
# =========================

@app.on_message(filters.document)
async def pdf_handler(client, message):

    document = message.document

    filename = document.file_name or ""

    if not filename.lower().endswith(".pdf"):

        await message.reply_text(
            "❌ Sirf PDF file bhejo."
        )

        return

    status = await message.reply_text(
        "📥 PDF download ho rahi hai..."
    )

    input_path = os.path.join(
        DOWNLOAD_DIR,
        filename
    )

    output_name = (
        os.path.splitext(filename)[0]
        + "_Hindi.pdf"
    )

    output_path = os.path.join(
        OUTPUT_DIR,
        output_name
    )

    try:

        # -------------------------
        # DOWNLOAD
        # -------------------------

        await message.download(
            file_name=input_path
        )

        await status.edit_text(
            "📖 PDF read ho rahi hai..."
        )

        # -------------------------
        # READ PDF
        # -------------------------

        doc = fitz.open(input_path)

        all_text = []

        total_pages = len(doc)

        for page_number, page in enumerate(
            doc,
            start=1
        ):

            page_text = page.get_text(
                "text"
            )

            if page_text.strip():

                all_text.append(
                    page_text
                )

            if page_number % 5 == 0:

                await status.edit_text(
                    "📖 Reading pages...\n"
                    f"{page_number}/{total_pages}"
                )

        doc.close()

        original_text = "\n\n".join(
            all_text
        )

        original_text = clean_text(
            original_text
        )

        if not original_text:

            await status.edit_text(
                "❌ Is PDF me selectable "
                "text nahi mila.\n\n"
                "Ho sakta hai PDF "
                "scanned/image based ho."
            )

            return

        # -------------------------
        # TRANSLATE
        # -------------------------

        await status.edit_text(
            "🌐 English → Hindi\n"
            "Translation started..."
        )

        translated_text = await translate_text(
            original_text
        )

        if not translated_text.strip():

            await status.edit_text(
                "❌ Translation nahi ho paya."
            )

            return

        # -------------------------
        # CREATE PDF
        # -------------------------

        await status.edit_text(
            "📝 Hindi PDF ban rahi hai..."
        )

        create_pdf(
            translated_text,
            output_path
        )

        # -------------------------
        # SEND PDF
        # -------------------------

        await status.edit_text(
            "📤 Hindi PDF upload ho rahi hai..."
        )

        await message.reply_document(
            document=output_path,
            caption=(
                "🇮🇳 **English → Hindi PDF**\n\n"
                "✅ Translation complete."
            )
        )

        await status.delete()

    except Exception as e:

        print(
            "MAIN ERROR:",
            repr(e)
        )

        try:

            await status.edit_text(
                "❌ Error aa gaya:\n\n"
                f"`{str(e)[:3000]}`"
            )

        except Exception:

            pass

    finally:

        # Delete downloaded PDF
        try:

            if os.path.exists(input_path):

                os.remove(input_path)

        except Exception:

            pass

        # Delete generated PDF
        try:

            if os.path.exists(output_path):

                os.remove(output_path)

        except Exception:

            pass


# =========================
# RUN
# =========================

print(
    "🇮🇳 English → Hindi PDF Bot Started!"
)

print(
    "Using font:",
    FONT_PATH
)

app.run()
