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

from config import API_ID, API_HASH, BOT_TOKEN


# =========================================================
# CONFIG
# =========================================================

FONT_CANDIDATES = [
    "NotoSansDevanagari-Regular.ttf",
    "NotoSansDevanagari-Regular (6).ttf",
]

MAX_TRANSLATE_CHARS = 450


# =========================================================
# FIND FONT
# =========================================================

def find_font():
    base = os.path.dirname(os.path.abspath(__file__))

    for name in FONT_CANDIDATES:
        path = os.path.join(base, name)
        if os.path.exists(path):
            return path

    return None


FONT_PATH = find_font()


# =========================================================
# TRANSLATION
# =========================================================

translator = GoogleTranslator(
    source="en",
    target="hi"
)


def translate_text(text):
    text = text.strip()

    if not text:
        return ""

    # बहुत छोटे/irrelevant OCR results को छोड़ना
    if len(text) <= 1:
        return text

    try:
        # Translation API को बहुत बड़ा text न दें
        if len(text) <= MAX_TRANSLATE_CHARS:
            result = translator.translate(text)
            return result if result else text

        parts = []

        words = text.split()
        current = ""

        for word in words:
            if len(current) + len(word) + 1 <= MAX_TRANSLATE_CHARS:
                current += (" " if current else "") + word
            else:
                if current:
                    parts.append(current)
                current = word

        if current:
            parts.append(current)

        translated = []

        for part in parts:
            try:
                value = translator.translate(part)
                translated.append(value if value else part)
            except Exception:
                translated.append(part)

        return " ".join(translated)

    except Exception:
        return text


# =========================================================
# TEXT CHECK
# =========================================================

def contains_english(text):
    return bool(re.search(r"[A-Za-z]", text))


def clean_ocr_text(text):
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# =========================================================
# OCR
# =========================================================

def detect_text(image_path):
    """
    Image se English text ke bounding boxes detect karta hai.
    """

    image = cv2.imread(image_path)

    if image is None:
        return []

    # OCR ke liye slightly enlarged image
    scale = 1.5

    resized = cv2.resize(
        image,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_CUBIC
    )

    data = pytesseract.image_to_data(
        resized,
        lang="eng",
        config="--oem 3 --psm 6",
        output_type=pytesseract.Output.DICT
    )

    results = []

    count = len(data["text"])

    for i in range(count):

        raw_text = data["text"][i]
        text = clean_ocr_text(raw_text)

        if not text:
            continue

        if not contains_english(text):
            continue

        try:
            confidence = float(data["conf"][i])
        except Exception:
            confidence = 0

        if confidence < 35:
            continue

        x = int(data["left"][i] / scale)
        y = int(data["top"][i] / scale)
        w = int(data["width"][i] / scale)
        h = int(data["height"][i] / scale)

        if w < 3 or h < 3:
            continue

        results.append({
            "text": text,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "confidence": confidence
        })

    return results


# =========================================================
# FONT SIZE
# =========================================================

def get_fitting_font(draw, text, max_width, max_height):

    if not FONT_PATH:
        return None

    # बड़ा font पहले
    start_size = max(10, min(80, int(max_height * 0.90)))

    for size in range(start_size, 7, -1):

        try:
            font = ImageFont.truetype(
                FONT_PATH,
                size
            )
        except Exception:
            return None

        bbox = draw.textbbox(
            (0, 0),
            text,
            font=font
        )

        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]

        if width <= max_width and height <= max_height:
            return font

    return ImageFont.truetype(
        FONT_PATH,
        8
    )


# =========================================================
# DRAW HINDI
# =========================================================

def draw_hindi_text(
    image,
    translated,
    x,
    y,
    w,
    h
):

    if not translated:
        return

    draw = ImageDraw.Draw(image)

    # थोड़ी padding
    padding = max(2, int(min(w, h) * 0.08))

    max_width = max(10, w - padding * 2)
    max_height = max(10, h - padding * 2)

    font = get_fitting_font(
        draw,
        translated,
        max_width,
        max_height
    )

    if font is None:
        return

    # Hindi text ko box ke andar fit karne ki कोशिश
    words = translated.split()

    lines = []
    current = ""

    for word in words:

        test = word if not current else current + " " + word

        bbox = draw.textbbox(
            (0, 0),
            test,
            font=font
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = test
        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    # Agar multiple lines hain to height check
    line_height = max(
        10,
        int(font.size * 1.15)
    )

    max_lines = max(
        1,
        int(max_height / line_height)
    )

    lines = lines[:max_lines]

    text_height = len(lines) * line_height

    start_y = y + max(
        0,
        (h - text_height) // 2
    )

    for line in lines:

        bbox = draw.textbbox(
            (0, 0),
            line,
            font=font
        )

        line_width = bbox[2] - bbox[0]

        start_x = x + max(
            padding,
            (w - line_width) // 2
        )

        draw.text(
            (start_x, start_y),
            line,
            font=font,
            fill=(0, 0, 0)
        )

        start_y += line_height


# =========================================================
# REMOVE ORIGINAL TEXT
# =========================================================

def remove_original_text(image_path, boxes):
    """
    OCR boxes ko mask karke OpenCV inpainting se
    original English text remove karta hai.
    """

    image = cv2.imread(image_path)

    if image is None:
        return

    mask = np.zeros(
        image.shape[:2],
        dtype=np.uint8
    )

    for item in boxes:

        x = item["x"]
        y = item["y"]
        w = item["w"]
        h = item["h"]

        # थोड़ा extra area ताकि English पूरा हटे
        pad_x = max(2, int(w * 0.04))
        pad_y = max(2, int(h * 0.18))

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

    # Inpainting
    repaired = cv2.inpaint(
        image,
        mask,
        3,
        cv2.INPAINT_TELEA
    )

    cv2.imwrite(
        image_path,
        repaired
    )


# =========================================================
# TRANSLATE ONE IMAGE
# =========================================================

def translate_image(
    input_path,
    output_path
):

    boxes = detect_text(input_path)

    if not boxes:
        shutil.copy2(
            input_path,
            output_path
        )
        return

    # पहले English हटाओ
    remove_original_text(
        input_path,
        boxes
    )

    image = Image.open(input_path).convert("RGB")

    for item in boxes:

        english = item["text"]

        # सिर्फ meaningful English
        if len(english.strip()) < 2:
            continue

        hindi = translate_text(english)

        if not hindi:
            continue

        draw_hindi_text(
            image,
            hindi,
            item["x"],
            item["y"],
            item["w"],
            item["h"]
        )

    image.save(
        output_path,
        "JPEG",
        quality=95
    )


# =========================================================
# PDF -> IMAGES
# =========================================================

def pdf_to_images(
    pdf_path,
    output_dir
):

    document = fitz.open(pdf_path)

    image_paths = []

    for page_number, page in enumerate(document):

        # 2x quality
        matrix = fitz.Matrix(
            2.0,
            2.0
        )

        pix = page.get_pixmap(
            matrix=matrix,
            alpha=False
        )

        path = os.path.join(
            output_dir,
            f"page_{page_number + 1}.jpg"
        )

        pix.save(path)

        image_paths.append(path)

    document.close()

    return image_paths


# =========================================================
# IMAGES -> PDF
# =========================================================

def images_to_pdf(
    image_paths,
    output_pdf
):

    images = []

    for path in image_paths:

        image = Image.open(path).convert(
            "RGB"
        )

        images.append(image)

    if not images:
        return False

    first = images[0]

    if len(images) == 1:

        first.save(
            output_pdf,
            "PDF",
            resolution=150.0
        )

    else:

        first.save(
            output_pdf,
            "PDF",
            resolution=150.0,
            save_all=True,
            append_images=images[1:]
        )

    for image in images:
        image.close()

    return True


# =========================================================
# PDF TRANSLATOR
# =========================================================

def translate_pdf(
    pdf_path,
    output_pdf
):

    work_dir = tempfile.mkdtemp(
        prefix="translator_"
    )

    try:

        images_dir = os.path.join(
            work_dir,
            "pages"
        )

        os.makedirs(
            images_dir,
            exist_ok=True
        )

        page_paths = pdf_to_images(
            pdf_path,
            images_dir
        )

        translated_paths = []

        for index, page_path in enumerate(page_paths):

            output_image = os.path.join(
                images_dir,
                f"translated_{index + 1}.jpg"
            )

            translate_image(
                page_path,
                output_image
            )

            translated_paths.append(
                output_image
            )

        images_to_pdf(
            translated_paths,
            output_pdf
        )

    finally:

        shutil.rmtree(
            work_dir,
            ignore_errors=True
        )


# =========================================================
# IMAGE PROCESSOR
# =========================================================

def translate_single_image(
    image_path,
    output_path
):

    translate_image(
        image_path,
        output_path
    )


# =========================================================
# TELEGRAM BOT
# =========================================================

app = Client(
    "english_hindi_pdf_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


# =========================================================
# START
# =========================================================

@app.on_message(
    filters.command("start")
)
async def start_handler(
    client,
    message: Message
):

    await message.reply_text(
        "🇮🇳 **English → Hindi Translator**\n\n"
        "📄 English PDF भेजो\n"
        "🖼️ English image भेजो\n\n"
        "मैं text को detect करके Hindi में "
        "उसी जगह translate करने की कोशिश करूँगा।"
    )


# =========================================================
# DOCUMENT HANDLER
# =========================================================

@app.on_message(
    filters.document
)
async def document_handler(
    client,
    message: Message
):

    document = message.document

    file_name = document.file_name or "input"

    lower_name = file_name.lower()

    if not (
        lower_name.endswith(".pdf")
        or lower_name.endswith(".jpg")
        or lower_name.endswith(".jpeg")
        or lower_name.endswith(".png")
        or lower_name.endswith(".webp")
    ):
        await message.reply_text(
            "❌ Sirf PDF/JPG/PNG/WEBP file bhejo."
        )
        return

    status = await message.reply_text(
        "⏳ File receive ho gayi.\n"
        "🔍 Text detect + Hindi translation chal raha hai..."
    )

    temp_dir = tempfile.mkdtemp(
        prefix="telegram_"
    )

    try:

        input_path = os.path.join(
            temp_dir,
            file_name
        )

        await message.download(
            file_name=input_path
        )

        if lower_name.endswith(".pdf"):

            output_path = os.path.join(
                temp_dir,
                "Hindi_Translated.pdf"
            )

            translate_pdf(
                input_path,
                output_path
            )

            await message.reply_document(
                document=output_path,
                caption="🇮🇳 **Hindi translated PDF ready!**"
            )

        else:

            output_path = os.path.join(
                temp_dir,
                "Hindi_Translated.jpg"
            )

            translate_single_image(
                input_path,
                output_path
            )

            await message.reply_photo(
                photo=output_path,
                caption="🇮🇳 **Hindi translated image ready!**"
            )

        await status.delete()

    except Exception as e:

        print(
            "PROCESS ERROR:",
            repr(e)
        )

        await status.edit_text(
            "❌ Processing में error आया.\n\n"
            f"`{str(e)[:1000]}`"
        )

    finally:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )


# =========================================================
# DIRECT PHOTO HANDLER
# =========================================================

@app.on_message(
    filters.photo
)
async def photo_handler(
    client,
    message: Message
):

    status = await message.reply_text(
        "⏳ Image process हो रही है..."
    )

    temp_dir = tempfile.mkdtemp(
        prefix="photo_"
    )

    try:

        input_path = os.path.join(
            temp_dir,
            "input.jpg"
        )

        output_path = os.path.join(
            temp_dir,
            "Hindi_Translated.jpg"
        )

        await message.download(
            file_name=input_path
        )

        translate_single_image(
            input_path,
            output_path
        )

        await message.reply_photo(
            photo=output_path,
            caption="🇮🇳 **Hindi translated image ready!**"
        )

        await status.delete()

    except Exception as e:

        print(
            "PHOTO ERROR:",
            repr(e)
        )

        await status.edit_text(
            "❌ Image process नहीं हो सकी.\n\n"
            f"`{str(e)[:1000]}`"
        )

    finally:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )


# =========================================================
# RUN
# =========================================================

print(
    "🇮🇳 English → Hindi Visual Translator Started!"
)

app.run()
