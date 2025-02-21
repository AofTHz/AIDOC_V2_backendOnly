import ast
import csv
import logging
import os
import pathlib
import platform
import shutil
import time
import traceback
import re
from datetime import datetime

import pytesseract
from PIL import Image
from pdf2image import convert_from_bytes
from sqlmodel import Session

from AIDOC_database import update_file_data
from AIDOC_geminiAPI import generate_response
from AIDOC_keyword_list import text_fix
from AIDOC_upload_status import upload_status

if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    pytesseract.pytesseract_cmd = "/usr/bin/tesseract"


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def log_statistics(pdf_filename: str, found_keywords: dict, accuracy):
    """
    บันทึกสถิติลงไฟล์ CSV โดย found_keywords ควรเป็น dict ที่เก็บข้อมูลว่า
    'keyword' : [list ของ page ที่พบคีย์เวิร์ด]
    เช่น { "abstract": [1, 2], "overview": [3], ... }
    """
    # สร้างไฟล์ /database/statistics.csv ไว้เก็บสถิติ (ถ้าไม่มีจะสร้างให้)
    with open("database/statistics.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # รวมจำนวนคีย์เวิร์ดที่เจอทั้งหมด (นับเป็น +1 ต่อ keyword)
        total_found = len(found_keywords)

        # แปลง dict ของ keywords-pageList ให้เป็น string เพื่อเขียนง่าย
        # หรืออาจกำหนดฟอร์แมตตามต้องการ เช่น JSON ก็ได้
        keyword_detail = str(found_keywords)

        # บันทึกเป็น 5 คอลัมน์: [วัน-เวลา, ชื่อไฟล์, พบกี่คีย์เวิร์ด, รายละเอียด keyword, ...]
        # จะเพิ่มคอลัมน์ตามต้องการก็ได้
        writer.writerow([
            datetime.now().isoformat(),  # วัน-เวลา
            pdf_filename,                # ชื่อไฟล์
            total_found,                 # จำนวน keyword ที่เจอ
            keyword_detail,               # รายละเอียดหน้า
            accuracy
        ])

def clean_text(text: str) -> str:
    """Remove all whitespace characters while preserving Thai text structure."""
    original_length = len(text)

    # 🔹 Remove **all** whitespace (spaces, tabs, newlines) to match your Thai approach
    cleaned = re.sub(r'\s+', '', text)

    final_length = len(cleaned)
    logger.debug(f"Text cleaning: Original length: {original_length}, Final length: {final_length}")
    logger.debug(f"Characters removed: {original_length - final_length}")

    return cleaned
def pdf2image_converter(files, task_id, page_range=None):
    pathlib.Path(f"database/temp").mkdir(parents=True, exist_ok=True)
    if platform.system() == "Windows":
        poppler_path = r"C:\Program Files\poppler-24.08.0\Library\bin"
    elif platform.system() == "Linux":
        poppler_path = "/usr/bin"  # Poppler is installed system-wide on Linux

    images = convert_from_bytes(files, poppler_path=poppler_path, fmt="png",
                                output_folder=f"database/temp/{task_id}", output_file="page",
                                first_page=page_range[0] if page_range else None,
                                last_page=page_range[1] if page_range else None)
    logger.debug(f"Converted PDF to {len(images)} images for pages {page_range}")
    return images

def extract_text_from_pdf_pages(pdf_file, task_id):
    """
    OCR แบบแยกหน้าคืนมาเป็น list โดยแต่ละ element คือข้อความของหน้านั้น
    """
    page_range = [1,7]
    try:
        logger.debug(f"Processing PDF for OCR (task: {task_id}, pages {page_range})")
        images = pdf2image_converter(pdf_file, task_id, page_range=page_range)
        page_texts = []

        for i, image in enumerate(images):
            logger.debug(f"Processing image {i+1} of {len(images)}")
            text = ocr_image(image.filename)
            # ไม่ต้อง clean_text รวบทีเดียวก็ได้ หรือจะ clean ก็ได้
            page_texts.append(text)

        return page_texts
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        logger.error(traceback.format_exc())
        return []

def search_keywords_in_pdfs(pdf_texts: dict, keywords: list[str]):
    matched_pdfs = {}
    for filename, text in pdf_texts.items():
        # Check if *any* of the keywords is found
        if any(kw.lower() in text.lower() for kw in keywords):
            matched_pdfs[filename] = text
            # OPTIONAL: you can also log which keywords were found if desired
    return matched_pdfs


def process_pdfs_with_keyword(pdf_files: dict, task_id, keywords: list[str]):
    extracted_texts = {}
    keyword_statistics = {}
    found_pages_for_keyword = {}

    for filename, pdf_content in pdf_files.items():
        logger.debug(f"Extracting text (split by pages) from {filename}")
        page_texts = extract_text_from_pdf_pages(pdf_content, task_id)

        for page_index, text in enumerate(page_texts, start=1):
            for kw in keywords:
                if kw.lower() in text.lower():
                    if kw not in found_pages_for_keyword:
                        found_pages_for_keyword[kw] = []
                    found_pages_for_keyword[kw].append(page_index)

        keyword_statistics[filename] = found_pages_for_keyword

        selected_pages = sorted(set([p for pages in found_pages_for_keyword.values() for p in pages]))

        if selected_pages:
            text_for_gemini = "\n".join(page_texts[p - 1] for p in selected_pages)
            logger.debug(f"Selecting pages {selected_pages} for Gemini")
        else:
            text_for_gemini = "\n".join(page_texts)
            logger.debug("No keywords found, sending full document to Gemini")

        extracted_texts[filename] = text_for_gemini

    for filename, text in extracted_texts.items():
        return text, [filename, found_pages_for_keyword]

    return None


def ocr_image(images_name):
    path = f"{images_name}"
    im = Image.open(path)
    im_gray = im.convert('L')
    im_gray.save(f"{images_name}_gray.png")
    result = pytesseract.image_to_string(f"{images_name}_gray.png", lang='eng+tha', config='--oem 1  --psm 4')
    cleaned_result = clean_text(result)
    logger.debug(f"OCR result length: {len(cleaned_result)} characters")
    logger.debug(f"OCR text preview: {cleaned_result[:200]}...")
    return cleaned_result

def core_result_processing(pdf_file, task_id, folder_list: list, filename: str):
    """Handles text extraction, AI classification, and returns all required data."""
    keywords = ["บทคัดย่อ", "abstract", "overview", *text_fix]
    page_range = (1, 7)

    logger.debug(f"Extracting text from PDF (task: {task_id}, filename: {filename})")

    if not pdf_file or len(pdf_file) == 0:
        raise Exception("PDF file is empty")

    pdf_files = {filename: pdf_file}
    matched_text, found_keywords = process_pdfs_with_keyword(pdf_files, task_id, keywords)

    if not matched_text:
        logger.debug("Keyword not found. Using fallback OCR processing.")
        images = pdf2image_converter(pdf_file, task_id, page_range=page_range)

        full_text = ""
        for i, image in enumerate(images):
            logger.debug(f"Fallback OCR on image {i + 1}/{len(images)}")
            text = ocr_image(image.filename)
            full_text += text + "\n"
    else:
        full_text = matched_text

    if not full_text.strip():
        raise Exception("OCR returned empty text. AI processing skipped.")

    logger.debug("=== Text being sent to Gemini AI ===")
    logger.debug(f"Text length: {len(full_text)} characters")
    logger.debug(f"First 500 characters:\n{full_text[:500]}")
    logger.debug(f"FolderList: {folder_list}")
    logger.debug("===============================")

    max_retries = 5
    retry_count = 0

    while retry_count < max_retries:
        result = generate_response(full_text, folder_list)
        logger.debug(f"MR.Result is here: {result}")
        split_result = result.split(",", 1)

        if len(split_result) == 2:
            gemini_label = split_result[0].strip()
            try:
                accuracy = ast.literal_eval(split_result[1].strip())
                return gemini_label, accuracy, full_text, found_keywords  # ✅ Return all useful data
            except (SyntaxError, ValueError):
                pass  # Retry if parsing fails

        retry_count += 1
        time.sleep(1)

    raise ValueError("AI response format is incorrect after multiple retries")

def return_result(pdf_file, task_id, folder_list: list, filename: str):
    """Keeps original return format (label, accuracy as string)."""
    try:
        gemini_label, accuracy, _, found_keywords = core_result_processing(pdf_file, task_id, folder_list, filename)

        # ✅ Log statistics using extracted keywords
        log_statistics(filename, found_keywords, accuracy)

        return gemini_label, str(accuracy)
    except Exception as e:
        logger.error(f"Error processing PDF file: {e}")
        logger.error(traceback.format_exc())
        raise Exception("Failed to process PDF file")

def return_result_with_text(pdf_file, task_id, folder_list: list, filename: str):
    """Returns (label, [accuracy], full_text) for AI tuning."""
    try:
        gemini_label, accuracy, full_text, found_keywords = core_result_processing(pdf_file, task_id, folder_list, filename)

        # ✅ Log statistics using extracted keywords
        log_statistics(filename, found_keywords, accuracy)

        return gemini_label, accuracy, full_text  # ✅ Returns full text for AI tuning
    except Exception as e:
        logger.error(f"Error processing PDF file: {e}")
        logger.error(traceback.format_exc())
        raise Exception("Failed to process PDF file")


def launch_scan(pdf_content: bytes, filename: str, task_id: str, folder_list: list, session: Session):
    upload_status[task_id] = {
        "status": "Processing",
        "file_name": filename,
        "current_step": "Starting scan",
        "progress": 0
    }
    try:
        logger.debug("Starting scan process")
        upload_status[task_id].update({
            "current_step": "Extracting text",
            "progress": 25
        })

        folder_names = [folder.name for folder in folder_list]

        text_result, accuracy = return_result(pdf_content, task_id, folder_names, filename)
        logger.debug(f"Scan completed. Result: {text_result}")
        upload_status[task_id].update({
            "current_step": "Organizing files",
            "progress": 75
        })

        organizing_files(text_result, filename, task_id, accuracy, session)

        upload_status[task_id].update({
            "status": "Completed",
            "current_step": "Process complete",
            "progress": 100
        })
        logger.debug(f"Task {task_id} completed successfully")
    except Exception as e:
        logger.error(f"Error in launch_scan: {e}")

        upload_status[task_id].update({
            "status": "Failed",
            "error": str(e),
            "current_step": "Error occurred"
        })
    finally:
        try:
            shutil.rmtree(f"database/temp/{task_id}", ignore_errors=True)
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup: {cleanup_error}")


def organizing_files(folder_name: str, filename: str, task_id: str, accuracy, session: Session):
    """
    Organize files and update their location in the database.
    """
    try:
        # Update status for database update
        upload_status[task_id].update({
            "current_step": "Updating database",
            "progress": 85
        })

        update_file_data(folder_name, filename, accuracy, session)

        # Update status for file copying
        upload_status[task_id].update({
            "current_step": "Copying file to storage",
            "progress": 95
        })

        # Ensure the destination directory exists
        os.makedirs(f"database/storage/{folder_name}", exist_ok=True)

        # Copy the file
        shutil.copy(f"database/temp/{task_id}/{filename}", f"database/storage/{folder_name}")

    except Exception as e:
        logger.error(f"Error in organizing_files: {e}")
        raise  # Re-raise the exception to be caught by launch_scan