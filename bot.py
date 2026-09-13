import os
import re
import asyncio

import fitz  # PyMuPDF
from pyrogram import Client, filters
from deep_translator import GoogleTranslator
from fpdf import FPDF

from config import API_ID, API_HASH, BOT_TOKEN, DOWNLOAD_DIR, OUTPUT_DIR, FONT_PATH


os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


app = Client(
    "english_hindi_pdf_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


translator = GoogleTranslator(source="en", target="hi")


def split_text(text, max_chars=2500):
    """Text ko safe chunks me divide karta hai."""
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

        chunks.append(text[:cut].strip())
        text = text[cut:].strip()

    if text:
        chunks.append(text)

    return chunks


async def translate_text(text):
    """English text ko Hindi me translate karta hai."""
    chunks = split_text(text)

    result = []

    for chunk in chunks:
        if not chunk.strip():
            continue

        try:
            translated = await asyncio.to_thread(
                translator.translate,
                chunk
            )

            if translated:
                result.append(translated)

        except Exception as e:
            print("Translation error:", e)

            # Agar translation fail ho to original text rakhenge
            result.append(chunk)

        await asyncio.sleep(0.3)

    return "\n\n".join(result)


def clean_text(text):
    """PDF ke liye text clean karta hai."""
    text = text.replace("\x00", "")
    text = text.replace("\r", "\n")

    # Bahut zyada blank lines hatao
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def safe_lines(text, max_len=90):
    """
    Bahut lambi URL/word ko todta hai,
    jisse FPDF horizontal-space error na aaye.
    """
    lines = []

    for line in text.split("\n"):
        line = line.strip()

        if not line:
            lines.append("")
            continue

        while len(line) > max_len:
            lines.append(line[:max_len])
            line = line[max_len:]

        if line:
            lines.append(line)

    return "\n".join(lines)


def create_pdf(text, output_path):
    """Hindi + English compatible PDF banata hai."""

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.add_page()

    # Hindi font
    pdf.add_font(
        "NotoHindi",
        "",
        FONT_PATH
    )

    pdf.set_font("NotoHindi", size=12)

    text = clean_text(text)
    text = safe_lines(text)

    # UTF-8 Hindi text
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            pdf.ln(4)
            continue

        try:
            pdf.multi_cell(
                0,
                7,
                paragraph,
                wrapmode="CHAR"
            )
        except Exception as e:
            print("PDF line error:", e)

            # Character-by-character fallback
            for part in [
                paragraph[i:i + 70]
                for i in range(0, len(paragraph), 70)
            ]:
                pdf.multi_cell(
                    0,
                    7,
                    part,
                    wrapmode="CHAR"
                )

    pdf.output(output_path)


@app.on_message(filters.command("start"))
async def start_handler(client, message):
    await message.reply_text(
        "🇮🇳 **English → Hindi PDF Bot**\n\n"
        "English PDF bhejo.\n"
        "Main uska Hindi translated PDF bana kar bhej dunga."
    )


@app.on_message(filters.document)
async def pdf_handler(client, message):

    document = message.document

    if not document.file_name.lower().endswith(".pdf"):
        await message.reply_text(
            "❌ Sirf PDF file bhejo."
        )
        return

    status = await message.reply_text(
        "📥 PDF download ho rahi hai..."
    )

    input_path = os.path.join(
        DOWNLOAD_DIR,
        document.file_name
    )

    output_name = (
        os.path.splitext(document.file_name)[0]
        + "_Hindi.pdf"
    )

    output_path = os.path.join(
        OUTPUT_DIR,
        output_name
    )

    try:

        await message.download(
            file_name=input_path
        )

        await status.edit_text(
            "📖 PDF read ho rahi hai..."
        )

        # PyMuPDF se text extraction
        doc = fitz.open(input_path)

        all_text = []

        total_pages = len(doc)

        for page_number, page in enumerate(doc, start=1):

            text = page.get_text("text")

            if text.strip():
                all_text.append(text)

            if page_number % 5 == 0:
                await status.edit_text(
                    f"📖 Reading pages...\n"
                    f"{page_number}/{total_pages}"
                )

        doc.close()

        original_text = "\n\n".join(all_text)
        original_text = clean_text(original_text)

        if not original_text:
            await status.edit_text(
                "❌ Is PDF me selectable text nahi mila.\n\n"
                "Ho sakta hai PDF scanned/image based ho."
            )
            return

        await status.edit_text(
            "🌐 English → Hindi translation started..."
        )

        translated_text = await translate_text(
            original_text
        )

        if not translated_text.strip():
            await status.edit_text(
                "❌ Translation nahi ho paya."
            )
            return

        await status.edit_text(
            "📝 Hindi PDF ban rahi hai..."
        )

        create_pdf(
            translated_text,
            output_path
        )

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

        print("MAIN ERROR:", repr(e))

        await status.edit_text(
            f"❌ Error aa gaya:\n\n"
            f"`{str(e)[:3000]}`"
        )

    finally:

        try:
            if os.path.exists(input_path):
                os.remove(input_path)
        except Exception:
            pass

        try:
            if os.path.exists(output_path):
                os.remove(output_path)
        except Exception:
            pass


print("🇮🇳 English → Hindi PDF Bot Started!")

app.run()
