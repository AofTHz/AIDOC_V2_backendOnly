import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import os

# Set Tesseract path (change this if needed)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def pdf_to_images(pdf_path, first_page=1, last_page=None, dpi=300):
    """ Convert PDF pages to images. """
    return convert_from_path(pdf_path, first_page=first_page, last_page=last_page, dpi=dpi)

def ocr_images(images, lang="tha+eng"):
    """ Perform OCR on images and return extracted text. """
    extracted_text = ""
    for i, img in enumerate(images):
        text = pytesseract.image_to_string(img, lang=lang)
        extracted_text += f"\n\n--- Page {i+1} ---\n\n{text}"
    return extracted_text

def save_text(text, output_path="ocr_output.txt"):
    """ Save extracted text to a file. """
    with open(output_path, "w", encoding="utf-8") as file:
        file.write(text)
    print(f"Text saved to {output_path}")

def main():
    pdf_path = "KachornpopWongpakam.pdf"  # Change this to your PDF path
    output_path = "ocr_output.txt"

    # Convert PDF to images
    images = pdf_to_images(pdf_path, first_page=1, last_page=12)  # Change range as needed

    # Perform OCR
    extracted_text = ocr_images(images)

    # Save to file
    save_text(extracted_text, output_path)

if __name__ == "__main__":
    main()
