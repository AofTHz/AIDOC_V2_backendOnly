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
    """Remove all whitespace characters and log the cleaning process."""
    original_length = len(text)
    # Remove all whitespace characters including spaces, tabs, newlines
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

def extract_text_from_pdf_pages(pdf_file, task_id, page_range):
    """
    OCR แบบแยกหน้าคืนมาเป็น list โดยแต่ละ element คือข้อความของหน้านั้น
    """
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

def extract_text_from_pdf(pdf_file, task_id, page_range):
    try:
        logger.debug(f"Processing PDF for OCR (task: {task_id}, pages {page_range})")
        images = pdf2image_converter(pdf_file, task_id, page_range=page_range)
        full_text = ""

        for i, image in enumerate(images):
            logger.debug(f"Processing image {i} of {len(images)}")
            text = ocr_image(image.filename)
            full_text += text

        cleaned_text = clean_text(full_text)
        logger.debug(f"Extracted text length: {len(cleaned_text)} characters")
        return cleaned_text
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        logger.error(traceback.format_exc())
        return None


def search_keywords_in_pdfs(pdf_texts: dict, keywords: list[str]):
    matched_pdfs = {}
    for filename, text in pdf_texts.items():
        # Check if *any* of the keywords is found
        if any(kw.lower() in text.lower() for kw in keywords):
            matched_pdfs[filename] = text
            # OPTIONAL: you can also log which keywords were found if desired
    return matched_pdfs


def process_pdfs_with_keyword(pdf_files: dict, task_id, keywords: list[str], page_range=(1, 10)):
    """
    OCR ทุกหน้าเสมอ แต่เลือกส่งเฉพาะหน้าที่มีคีย์เวิร์ดให้ Gemini
    ถ้าไม่พบคีย์เวิร์ดเลย -> ส่งทุกหน้าไปให้ Gemini
    """
    extracted_texts = {}
    keyword_statistics = {}
    found_pages_for_keyword = {}
    for filename, pdf_content in pdf_files.items():
        logger.debug(f"Extracting text (split by pages) from {filename}")
        page_texts = extract_text_from_pdf_pages(pdf_content, task_id, page_range)

        # เก็บว่าคีย์เวิร์ดไหนเจอที่หน้าไหนบ้าง
        for page_index, text in enumerate(page_texts, start=1):
            for kw in keywords:
                if kw.lower() in text.lower():
                    if kw not in found_pages_for_keyword:
                        found_pages_for_keyword[kw] = []
                    found_pages_for_keyword[kw].append(page_index)

        # 📊 บันทึกสถิติว่าคีย์เวิร์ดเจอหน้าไหนบ้าง
        keyword_statistics[filename] = found_pages_for_keyword
        #log_statistics(filename, found_pages_for_keyword)

        # ✂️ เลือกเฉพาะหน้าที่เจอคีย์เวิร์ดไปใช้ (ถ้าไม่มีเลยให้ใช้ทุกหน้า)
        selected_pages = sorted(set([p for pages in found_pages_for_keyword.values() for p in pages]))

        if selected_pages:
            text_for_gemini = "\n".join(page_texts[p - 1] for p in selected_pages)
            logger.debug(f"Selecting pages {selected_pages} for Gemini")
        else:
            text_for_gemini = "\n".join(page_texts)  # ถ้าไม่เจอคีย์เวิร์ด ส่งทุกหน้า
            logger.debug("No keywords found, sending full document to Gemini")

        extracted_texts[filename] = text_for_gemini

    # ✅ คืนค่าข้อความของไฟล์แรกที่ OCR เสร็จ
    for filename, text in extracted_texts.items():
        return text, [filename, found_pages_for_keyword]

    return None  # กรณีผิดปกติ (ไม่มีไฟล์ OCR เลย)

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


def return_result(pdf_file, task_id, folder_list: list, filename:str):
    keywords = ["บทคัดย่อ", "abstract", "overview", *text_fix]
    page_range = (1, 7)

    try:
        logger.debug(f"Starting PDF processing with keyword '{keywords}' in pages {page_range}")
        logger.debug(f"PDF file size: {len(pdf_file)} bytes")

        if not pdf_file or len(pdf_file) == 0:
            raise Exception("PDF file is empty")

        pdf_files = {filename: pdf_file}
        matched_text, file_info = process_pdfs_with_keyword(pdf_files, task_id, keywords, page_range)

        if not matched_text:
            logger.debug("Keyword not found. Using default page processing.")
            images = pdf2image_converter(pdf_file, task_id, page_range=page_range)

            # Instead of only using images[0], loop through all pages
            full_text = ""
            for i, image in enumerate(images):
                logger.debug(f"Fallback OCR on image {i + 1}/{len(images)}")
                text = ocr_image(image.filename)
                full_text += text
        else:
            full_text = matched_text

        logger.debug("=== Text being sent to Gemini ===")
        logger.debug(f"Text length: {len(full_text)} characters")
        logger.debug("First 500 characters:")
        logger.debug(full_text[:500])
        logger.debug("Last 500 characters:")
        logger.debug(full_text[-500:])
        logger.debug("===============================")
        max_retries = 5  # Prevent infinite loops by limiting retries
        retry_count = 0

        while retry_count < max_retries:
            result = generate_response(full_text, folder_list)
            split_result = result.split(",", 1)

            if len(split_result) == 2:  # Ensure it contains exactly two parts
                gemini_result = split_result[0].strip()
                try:
                    accuracy = ast.literal_eval(split_result[1].strip())
                    break  # Successfully parsed, exit loop
                except (SyntaxError, ValueError):
                    pass  # Parsing failed, retry

            retry_count += 1
            time.sleep(1)  # Wait a bit before retrying

        if retry_count == max_retries:
            raise ValueError("AI response format is incorrect after multiple retries")

        log_statistics(file_info[0],file_info[1],accuracy)

        logger.debug("=== Gemini Response ===")
        logger.debug(f"Response length: {len(gemini_result)} characters")
        logger.debug("First 200 characters of response:")
        logger.debug(gemini_result[:200])
        logger.debug("======================")

        return gemini_result.rstrip(), str(accuracy)
    except Exception as e:
        logger.error(f"Error processing PDF file: {e}")
        logger.error(traceback.format_exc())
        raise Exception("Failed to read PDF file")

def launch_scan(pdf_content: bytes, filename: str, task_id: str, folder_list: list, session: Session):
    """
    Process the uploaded PDF file and update its status throughout the process.
    """
    # Initialize status with more detailed information
    upload_status[task_id] = {
        "status": "Processing",
        "file_name": filename,
        "current_step": "Starting scan",
        "progress": 0
    }

    try:
        logger.debug("Starting scan process")
        # Update status for text extraction
        upload_status[task_id].update({
            "current_step": "Extracting text",
            "progress": 25
        })

        text_result, accuracy = return_result(pdf_content, task_id, folder_list, filename)
        logger.debug(f"Scan completed. Result: {text_result}")

        # Update status for file organization
        upload_status[task_id].update({
            "current_step": "Organizing files",
            "progress": 75
        })

        organizing_files(text_result, filename, task_id, accuracy ,session)

        # Mark this upload as completed with final status
        upload_status[task_id].update({
            "status": "Completed",
            "current_step": "Process complete",
            "progress": 100
        })
        logger.debug(f"Task {task_id} completed successfully")

    except Exception as e:
        logger.error(f"Error in launch_scan: {e}")
        # If an exception occurred, mark it as failed with error details
        upload_status[task_id].update({
            "status": "Failed",
            "error": str(e),
            "current_step": "Error occurred"
        })
    finally:
        # Cleanup temp files
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