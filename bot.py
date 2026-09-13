import os
import re
import cv2
import fitz
import shutil
import tempfile
import pytesseract
import numpy as np

from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator
from pyrogram import Client, filters
from pyrogram.types import Message


# =========================
# CONFIG
# =========================

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

app = Client(
    "english_hindi_visual_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


# =========================
# TESSERACT SETUP
# =========================

def setup_tesseract():
    """
    Automatically find Tesseract and tessdata.
    Works better on Heroku/Linux.
    """

    possible_tesseract = [
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract"
    ]

    for path in possible_tesseract:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            break

    possible_tessdata = [
        "/usr/share/tesseract-ocr/5/tessdata",
        "/usr/share/tesseract-ocr/4.00/tessdata",
        "/usr/share/tessdata",
        "/usr/local/share/tessdata"
    ]

    for path in possible_tessdata:
        eng_file = os.path.join(path, "eng.traineddata")

        if os.path.exists(eng_file):
            os.environ["TESSDATA_PREFIX"] = path
            break


setup_tesseract()


# =========================
# FONT
# =========================

FONT_FILES = [
    "NotoSansDevanagari-Regular.ttf",
    "NotoSansDevanagari-Regular (6).ttf"
]


def get_font_path():
    for font in FONT_FILES:
        if os.path.exists(font):
            return font

    return None


FONT_PATH = get_font_path()


# =========================
# HELPERS
# =========================

def clean_text(text):
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text


def is_useful_text(text):
    text = clean_text(text)

    if not text:
        return False

    # At least one English alphabet
    if not re.search(r"[A-Za-z]", text):
        return False

    # Ignore very small OCR fragments
    if len(text) < 2:
        return False

    return True


def translate_text(text):
    try:
        translator = GoogleTranslator(
            source="en",
            target="hi"
        )

        result = translator.translate(text)

        if result:
            return clean_text(result)

    except Exception as e:
        print("TRANSLATION ERROR:", e)

    return text


# =========================
# FONT SIZE
# =========================

def get_font(size):
    if FONT_PATH and os.path.exists(FONT_PATH):
        return ImageFont.truetype(FONT_PATH, size)

    # Fallback
    return ImageFont.load_default()


def fit_text(draw, text, box_width, box_height):
    """
    Find a Hindi font size that fits inside OCR box.
    """

    max_size = max(12, min(60, int(box_height * 0.90)))

    for size in range(max_size, 7, -1):

        font = get_font(size)

        bbox = draw.multiline_textbbox(
            (0, 0),
            text,
            font=font,
            spacing=2
        )

        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]

        if width <= box_width and height <= box_height:
            return font

    return get_font(10)


# =========================
# OCR
# =========================

def detect_text(image):
    """
    Detect English text using Tesseract.
    Returns:
        [(x, y, w, h, text, confidence), ...]
    """

    data = pytesseract.image_to_data(
        image,
        lang="eng",
        config="--oem 3 --psm 6",
        output_type=pytesseract.Output.DICT
    )

    results = []

    total = len(data["text"])

    for i in range(total):

        text = clean_text(data["text"][i])

        try:
            confidence = float(data["conf"][i])
        except Exception:
            confidence = 0

        if confidence < 35:
            continue

        if not is_useful_text(text):
            continue

        x = int(data["left"][i])
        y = int(data["top"][i])
        w = int(data["width"][i])
        h = int(data["height"][i])

        if w <= 2 or h <= 2:
            continue

        results.append(
            (x, y, w, h, text, confidence)
        )

    return results


# =========================
# REMOVE OLD TEXT
# =========================

def remove_original_text(image, boxes):
    """
    Remove detected English text using OpenCV inpainting.
    """

    mask = np.zeros(
        image.shape[:2],
        dtype=np.uint8
    )

    for x, y, w, h, text, confidence in boxes:

        # Slight padding around text
        pad_x = max(2, int(w * 0.08))
        pad_y = max(2, int(h * 0.20))

        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_y)

        x2 = min(
            image.shape[1],
            x + w + pad_x
        )

        y2 = min(
            image.shape[0],
            y + h + pad_y
        )

        cv2.rectangle(
            mask,
            (x1, y1),
            (x2, y2),
            255,
            -1
        )

    if np.any(mask):
        image = cv2.inpaint(
            image,
            mask,
            3,
            cv2.INPAINT_TELEA
        )

    return image


# =========================
# DRAW HINDI
# =========================

def draw_translations(image, boxes):
    """
    Put Hindi translation approximately
    where English text was.
    """

    pil_image = Image.fromarray(
        cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    )

    draw = ImageDraw.Draw(pil_image)

    for x, y, w, h, english, confidence in boxes:

        hindi = translate_text(english)

        if not hindi:
            continue

        # Slightly bigger area for Hindi
        box_width = max(w, 40)
        box_height = max(h, 20)

        font = fit_text(
            draw,
            hindi,
            box_width,
            box_height
        )

        # Calculate text dimensions
        bbox = draw.multiline_textbbox(
            (0, 0),
            hindi,
            font=font,
            spacing=2
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Keep inside image
        draw_x = x

        if draw_x + text_width > pil_image.width:
            draw_x = max(
                0,
                pil_image.width - text_width - 2
            )

        draw_y = y

        if draw_y + text_height > pil_image.height:
            draw_y = max(
                0,
                pil_image.height - text_height - 2
            )

        # White/light background behind Hindi text
        # to make translation readable.
        padding = 2

        draw.rectangle(
            [
                draw_x - padding,
                draw_y - padding,
                min(
                    pil_image.width,
                    draw_x + text_width + padding
                ),
                min(
                    pil_image.height,
                    draw_y + text_height + padding
                )
            ],
            fill="white"
        )

        draw.multiline_text(
            (draw_x, draw_y),
            hindi,
            font=font,
            fill="black",
            spacing=2
        )

    result = cv2.cvtColor(
        np.array(pil_image),
        cv2.COLOR_RGB2BGR
    )

    return result


# =========================
# IMAGE TRANSLATOR
# =========================

def translate_image(input_file, output_file):
    """
    English Image
        ↓
    OCR
        ↓
    English text boxes
        ↓
    Hindi translation
        ↓
    Remove English
        ↓
    Put Hindi in same area
    """

    image = cv2.imread(input_file)

    if image is None:
        raise Exception("Image open nahi ho paayi.")

    print("OCR STARTED")

    boxes = detect_text(image)

    print("TEXT BOXES:", len(boxes))

    if not boxes:
        # No text detected
        cv2.imwrite(output_file, image)
        return

    print("REMOVING ORIGINAL TEXT")

    image = remove_original_text(
        image,
        boxes
    )

    print("ADDING HINDI TRANSLATION")

    image = draw_translations(
        image,
        boxes
    )

    cv2.imwrite(
        output_file,
        image,
        [cv2.IMWRITE_JPEG_QUALITY, 95]
    )


# =========================
# PDF → IMAGES
# =========================

def pdf_to_images(pdf_file, output_dir):
    """
    Render PDF pages into high quality images.
    """

    doc = fitz.open(pdf_file)

    pages = []

    for page_number, page in enumerate(doc):

        matrix = fitz.Matrix(
            2.0,
            2.0
        )

        pix = page.get_pixmap(
            matrix=matrix,
            alpha=False
        )

        image_path = os.path.join(
            output_dir,
            f"page_{page_number + 1}.jpg"
        )

        pix.save(image_path)

        pages.append(image_path)

    doc.close()

    return pages


# =========================
# IMAGES → PDF
# =========================

def images_to_pdf(
    image_files,
    output_pdf
):

    images = []

    for file in image_files:

        image = Image.open(file)

        if image.mode != "RGB":
            image = image.convert("RGB")

        images.append(image)

    if not images:
        raise Exception("PDF ke liye pages nahi mile.")

    first = images[0]

    if len(images) > 1:

        first.save(
            output_pdf,
            save_all=True,
            append_images=images[1:],
            resolution=150
        )

    else:

        first.save(
            output_pdf,
            resolution=150
        )

    for image in images:
        image.close()


# =========================
# PDF TRANSLATOR
# =========================

def translate_pdf(
    input_pdf,
    output_pdf
):

    work_dir = tempfile.mkdtemp(
        prefix="translator_"
    )

    try:

        print("PDF → IMAGES")

        original_pages = pdf_to_images(
            input_pdf,
            work_dir
        )

        translated_pages = []

        print(
            "TOTAL PAGES:",
            len(original_pages)
        )

        for index, page in enumerate(
            original_pages,
            start=1
        ):

            output_image = os.path.join(
                work_dir,
                f"translated_{index}.jpg"
            )

            print(
                f"PROCESSING PAGE {index}"
            )

            translate_image(
                page,
                output_image
            )

            translated_pages.append(
                output_image
            )

        print("IMAGES → PDF")

        images_to_pdf(
            translated_pages,
            output_pdf
        )

    finally:

        shutil.rmtree(
            work_dir,
            ignore_errors=True
        )


# =========================
# START COMMAND
# =========================

@app.on_message(filters.command("start"))
async def start_command(
    client: Client,
    message: Message
):

    await message.reply_text(
        "🇮🇳 **English → Hindi Visual Translator**\n\n"
        "📄 PDF ya Image bhejo.\n\n"
        "Bot English text ko detect karke "
        "Hindi me translate karega aur "
        "translation ko original text ki "
        "jagah par place karega.\n\n"
        "✅ PDF\n"
        "✅ JPG\n"
        "✅ JPEG\n"
        "✅ PNG\n"
        "✅ WEBP"
    )


# =========================
# DOCUMENT HANDLER
# =========================

@app.on_message(
    filters.document
)
async def document_handler(
    client: Client,
    message: Message
):

    document = message.document

    if not document:
        return

    file_name = document.file_name or "file"

    extension = os.path.splitext(
        file_name
    )[1].lower()

    allowed = [
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp"
    ]

    if extension not in allowed:

        await message.reply_text(
            "❌ Sirf PDF, JPG, JPEG, PNG "
            "ya WEBP file bhejo."
        )

        return

    status = await message.reply_text(
        "⏳ Processing started...\n"
        "Please wait."
    )

    temp_dir = tempfile.mkdtemp(
        prefix="bot_"
    )

    input_file = os.path.join(
        temp_dir,
        file_name
    )

    try:

        await message.download(
            file_name=input_file
        )

        # =====================
        # PDF
        # =====================

        if extension == ".pdf":

            output_file = os.path.join(
                temp_dir,
                "Hindi_Translated.pdf"
            )

            await status.edit_text(
                "🔍 PDF pages process ho rahe hain..."
            )

            translate_pdf(
                input_file,
                output_file
            )

            await message.reply_document(
                document=output_file,
                caption=(
                    "🇮🇳 **English → Hindi Visual Translation**\n\n"
                    "✅ Translation complete."
                )
            )

        # =====================
        # IMAGE
        # =====================

        else:

            output_file = os.path.join(
                temp_dir,
                "Hindi_Translated.jpg"
            )

            await status.edit_text(
                "🔍 Image ka text detect ho raha hai..."
            )

            translate_image(
                input_file,
                output_file
            )

            await message.reply_photo(
                photo=output_file,
                caption=(
                    "🇮🇳 **English → Hindi Visual Translation**\n\n"
                    "✅ Translation complete."
                )
            )

        await status.delete()

    except Exception as e:

        print(
            "PROCESS ERROR:",
            repr(e)
        )

        await status.edit_text(
            "❌ Processing में error आया.\n\n"
            f"`{str(e)[:3500]}`"
        )

    finally:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )


# =========================
# DIRECT PHOTO HANDLER
# =========================

@app.on_message(
    filters.photo
)
async def photo_handler(
    client: Client,
    message: Message
):

    status = await message.reply_text(
        "⏳ Image process ho rahi hai..."
    )

    temp_dir = tempfile.mkdtemp(
        prefix="photo_"
    )

    input_file = os.path.join(
        temp_dir,
        "input.jpg"
    )

    output_file = os.path.join(
        temp_dir,
        "Hindi_Translated.jpg"
    )

    try:

        await message.download(
            file_name=input_file
        )

        translate_image(
            input_file,
            output_file
        )

        await message.reply_photo(
            photo=output_file,
            caption=(
                "🇮🇳 **English → Hindi Visual Translation**\n\n"
                "✅ Translation complete."
            )
        )

        await status.delete()

    except Exception as e:

        print(
            "PHOTO ERROR:",
            repr(e)
        )

        await status.edit_text(
            "❌ Processing में error आया.\n\n"
            f"`{str(e)[:3500]}`"
        )

    finally:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )


# =========================
# RUN BOT
# =========================

if __name__ == "__main__":

    print(
        "🇮🇳 English → Hindi Visual Translator Started!"
    )

    app.run()
