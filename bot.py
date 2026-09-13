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


# =========================================================
# CONFIG
# =========================================================

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

app = Client(
    "english_hindi_visual_translator",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


# =========================================================
# PATHS
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

LOCAL_TESSDATA = os.path.join(
    BASE_DIR,
    "tessdata"
)

LOCAL_ENG_DATA = os.path.join(
    LOCAL_TESSDATA,
    "eng.traineddata"
)


# =========================================================
# TESSERACT SETUP
# =========================================================

def setup_tesseract():

    # Find tesseract executable
    possible_paths = [
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract"
    ]

    for path in possible_paths:

        if os.path.exists(path):

            pytesseract.pytesseract.tesseract_cmd = path

            print(
                "Tesseract:",
                path
            )

            break

    # Use local tessdata if available
    if os.path.exists(LOCAL_ENG_DATA):

        os.environ["TESSDATA_PREFIX"] = (
            LOCAL_TESSDATA + os.sep
        )

        print(
            "Local English data found:"
        )

        print(
            LOCAL_ENG_DATA
        )

    else:

        print(
            "WARNING: Local eng.traineddata not found."
        )

        print(
            "Expected:",
            LOCAL_ENG_DATA
        )


setup_tesseract()


# =========================================================
# FONT
# =========================================================

FONT_PATH = None

possible_fonts = [

    os.path.join(
        BASE_DIR,
        "NotoSansDevanagari-Regular.ttf"
    ),

    os.path.join(
        BASE_DIR,
        "NotoSansDevanagari-Regular (6).ttf"
    )
]


for font_path in possible_fonts:

    if os.path.exists(font_path):

        FONT_PATH = font_path

        print(
            "Hindi font:",
            FONT_PATH
        )

        break


# =========================================================
# FONT FUNCTION
# =========================================================

def get_font(size):

    if FONT_PATH:

        return ImageFont.truetype(
            FONT_PATH,
            size
        )

    return ImageFont.load_default()


# =========================================================
# TEXT CLEAN
# =========================================================

def clean_text(text):

    if not text:
        return ""

    text = text.strip()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text


# =========================================================
# CHECK TEXT
# =========================================================

def useful_text(text):

    text = clean_text(text)

    if len(text) < 2:
        return False

    if not re.search(
        r"[A-Za-z]",
        text
    ):
        return False

    return True


# =========================================================
# TRANSLATION
# =========================================================

def translate_text(text):

    text = clean_text(text)

    if not text:
        return ""

    try:

        result = GoogleTranslator(
            source="en",
            target="hi"
        ).translate(text)

        if result:

            return clean_text(
                result
            )

    except Exception as e:

        print(
            "TRANSLATION ERROR:",
            repr(e)
        )

    return text


# =========================================================
# OCR
# =========================================================

def detect_text(image):

    # Check trained data first
    if not os.path.exists(
        LOCAL_ENG_DATA
    ):

        raise Exception(
            "eng.traineddata missing. "
            "GitHub repo me tessdata/eng.traineddata "
            "file add karo."
        )

    print(
        "Running Tesseract OCR..."
    )

    try:

        data = pytesseract.image_to_data(
            image,
            lang="eng",
            config="--oem 3 --psm 6",
            output_type=pytesseract.Output.DICT
        )

    except Exception as e:

        raise Exception(
            "Tesseract OCR failed: "
            + str(e)
        )

    results = []

    count = len(
        data["text"]
    )

    for i in range(count):

        text = clean_text(
            data["text"][i]
        )

        try:

            confidence = float(
                data["conf"][i]
            )

        except Exception:

            confidence = 0

        if confidence < 35:
            continue

        if not useful_text(text):
            continue

        try:

            x = int(
                data["left"][i]
            )

            y = int(
                data["top"][i]
            )

            w = int(
                data["width"][i]
            )

            h = int(
                data["height"][i]
            )

        except Exception:

            continue

        if w < 3 or h < 3:
            continue

        results.append(
            (
                x,
                y,
                w,
                h,
                text,
                confidence
            )
        )

    print(
        "Detected text:",
        len(results)
    )

    return results


# =========================================================
# REMOVE ORIGINAL TEXT
# =========================================================

def remove_original_text(
    image,
    boxes
):

    mask = np.zeros(
        image.shape[:2],
        dtype=np.uint8
    )

    for (
        x,
        y,
        w,
        h,
        text,
        confidence
    ) in boxes:

        padding_x = max(
            2,
            int(w * 0.08)
        )

        padding_y = max(
            2,
            int(h * 0.25)
        )

        x1 = max(
            0,
            x - padding_x
        )

        y1 = max(
            0,
            y - padding_y
        )

        x2 = min(
            image.shape[1],
            x + w + padding_x
        )

        y2 = min(
            image.shape[0],
            y + h + padding_y
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


# =========================================================
# FIT HINDI TEXT
# =========================================================

def fit_font(
    draw,
    text,
    width,
    height
):

    max_size = max(
        12,
        min(
            60,
            int(height * 0.95)
        )
    )

    for size in range(
        max_size,
        7,
        -1
    ):

        font = get_font(
            size
        )

        bbox = draw.textbbox(
            (0, 0),
            text,
            font=font
        )

        text_width = (
            bbox[2] - bbox[0]
        )

        text_height = (
            bbox[3] - bbox[1]
        )

        if (
            text_width <= width
            and
            text_height <= height
        ):

            return font

    return get_font(10)


# =========================================================
# DRAW HINDI
# =========================================================

def draw_hindi(
    image,
    boxes
):

    pil_image = Image.fromarray(
        cv2.cvtColor(
            image,
            cv2.COLOR_BGR2RGB
        )
    )

    draw = ImageDraw.Draw(
        pil_image
    )

    for (
        x,
        y,
        w,
        h,
        english,
        confidence
    ) in boxes:

        print(
            "Translating:",
            english
        )

        hindi = translate_text(
            english
        )

        if not hindi:
            continue

        font = fit_font(
            draw,
            hindi,
            max(w, 30),
            max(h, 20)
        )

        bbox = draw.textbbox(
            (0, 0),
            hindi,
            font=font
        )

        text_width = (
            bbox[2] - bbox[0]
        )

        text_height = (
            bbox[3] - bbox[1]
        )

        draw_x = x
        draw_y = y

        # Keep text inside image

        if (
            draw_x + text_width
            > pil_image.width
        ):

            draw_x = max(
                0,
                pil_image.width
                - text_width
                - 2
            )

        if (
            draw_y + text_height
            > pil_image.height
        ):

            draw_y = max(
                0,
                pil_image.height
                - text_height
                - 2
            )

        # Small white background
        # for readability

        pad = 2

        draw.rectangle(
            [
                max(
                    0,
                    draw_x - pad
                ),

                max(
                    0,
                    draw_y - pad
                ),

                min(
                    pil_image.width,
                    draw_x
                    + text_width
                    + pad
                ),

                min(
                    pil_image.height,
                    draw_y
                    + text_height
                    + pad
                )
            ],
            fill="white"
        )

        draw.text(
            (
                draw_x,
                draw_y
            ),
            hindi,
            font=font,
            fill="black"
        )

    return cv2.cvtColor(
        np.array(pil_image),
        cv2.COLOR_RGB2BGR
    )


# =========================================================
# IMAGE TRANSLATOR
# =========================================================

def translate_image(
    input_file,
    output_file
):

    print(
        "Opening image..."
    )

    image = cv2.imread(
        input_file
    )

    if image is None:

        raise Exception(
            "Image open nahi ho paayi."
        )

    boxes = detect_text(
        image
    )

    if not boxes:

        print(
            "No English text detected."
        )

        cv2.imwrite(
            output_file,
            image
        )

        return

    print(
        "Removing English text..."
    )

    image = remove_original_text(
        image,
        boxes
    )

    print(
        "Adding Hindi..."
    )

    image = draw_hindi(
        image,
        boxes
    )

    success = cv2.imwrite(
        output_file,
        image,
        [
            cv2.IMWRITE_JPEG_QUALITY,
            95
        ]
    )

    if not success:

        raise Exception(
            "Output image save nahi ho paayi."
        )


# =========================================================
# PDF → IMAGES
# =========================================================

def pdf_to_images(
    pdf_file,
    output_dir
):

    doc = fitz.open(
        pdf_file
    )

    pages = []

    try:

        for number, page in enumerate(
            doc
        ):

            matrix = fitz.Matrix(
                2,
                2
            )

            pix = page.get_pixmap(
                matrix=matrix,
                alpha=False
            )

            output = os.path.join(
                output_dir,
                f"page_{number + 1}.jpg"
            )

            pix.save(
                output
            )

            pages.append(
                output
            )

    finally:

        doc.close()

    return pages


# =========================================================
# IMAGES → PDF
# =========================================================

def images_to_pdf(
    images,
    output_pdf
):

    if not images:

        raise Exception(
            "Translated pages nahi mile."
        )

    pil_images = []

    for file in images:

        img = Image.open(
            file
        )

        if img.mode != "RGB":

            img = img.convert(
                "RGB"
            )

        pil_images.append(
            img
        )

    first = pil_images[0]

    if len(pil_images) > 1:

        first.save(
            output_pdf,
            "PDF",
            save_all=True,
            append_images=pil_images[1:],
            resolution=150
        )

    else:

        first.save(
            output_pdf,
            "PDF",
            resolution=150
        )

    for img in pil_images:

        img.close()


# =========================================================
# PDF TRANSLATOR
# =========================================================

def translate_pdf(
    input_pdf,
    output_pdf
):

    work_dir = tempfile.mkdtemp(
        prefix="pdf_translate_"
    )

    try:

        print(
            "PDF pages rendering..."
        )

        pages = pdf_to_images(
            input_pdf,
            work_dir
        )

        translated_pages = []

        print(
            "Total pages:",
            len(pages)
        )

        for index, page in enumerate(
            pages,
            start=1
        ):

            print(
                f"Processing page {index}"
            )

            output = os.path.join(
                work_dir,
                f"translated_{index}.jpg"
            )

            translate_image(
                page,
                output
            )

            translated_pages.append(
                output
            )

        print(
            "Creating final PDF..."
        )

        images_to_pdf(
            translated_pages,
            output_pdf
        )

    finally:

        shutil.rmtree(
            work_dir,
            ignore_errors=True
        )


# =========================================================
# START
# =========================================================

@app.on_message(
    filters.command("start")
)
async def start_handler(
    client,
    message
):

    await message.reply_text(
        "🇮🇳 **English → Hindi Visual Translator**\n\n"
        "📄 PDF ya Image bhejo.\n\n"
        "Bot English text ko detect karke "
        "Hindi me translate karega aur "
        "image ke same area me Hindi "
        "place karega.\n\n"
        "✅ PDF\n"
        "✅ JPG\n"
        "✅ JPEG\n"
        "✅ PNG\n"
        "✅ WEBP"
    )


# =========================================================
# DOCUMENT
# =========================================================

@app.on_message(
    filters.document
)
async def document_handler(
    client,
    message
):

    document = message.document

    file_name = (
        document.file_name
        or "input_file"
    )

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
            "❌ Sirf PDF, JPG, JPEG, "
            "PNG ya WEBP bhejo."
        )

        return

    status = await message.reply_text(
        "⏳ Processing started..."
    )

    temp_dir = tempfile.mkdtemp(
        prefix="document_"
    )

    input_file = os.path.join(
        temp_dir,
        file_name
    )

    try:

        await message.download(
            file_name=input_file
        )

        if extension == ".pdf":

            output_file = os.path.join(
                temp_dir,
                "Hindi_Translated.pdf"
            )

            await status.edit_text(
                "🔍 PDF process ho raha hai..."
            )

            translate_pdf(
                input_file,
                output_file
            )

            await message.reply_document(
                document=output_file,
                caption=(
                    "🇮🇳 **English → Hindi "
                    "Visual Translation**\n\n"
                    "✅ Translation complete."
                )
            )

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
                    "🇮🇳 **English → Hindi "
                    "Visual Translation**\n\n"
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


# =========================================================
# PHOTO
# =========================================================

@app.on_message(
    filters.photo
)
async def photo_handler(
    client,
    message
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
                "🇮🇳 **English → Hindi "
                "Visual Translation**\n\n"
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


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    print(
        "🇮🇳 English → Hindi Visual "
        "Translator Started!"
    )

    app.run()
