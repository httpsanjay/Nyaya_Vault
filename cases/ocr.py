import pytesseract
from pdf2image import convert_from_path
from PIL import Image

def extract_text(file_path):
    text = ""
    if file_path.lower().endswith('.pdf'):
        pages = convert_from_path(file_path)
        for page in pages:
            text += pytesseract.image_to_string(page)
    else:
        image = Image.open(file_path)
        text = pytesseract.image_to_string(image)
    return text.strip()