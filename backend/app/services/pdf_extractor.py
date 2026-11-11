import os
from pathlib import Path
import pymupdf as fitz
import pytesseract
from PIL import Image

def extract_pdf(path: str):
    doc=fitz.open(path)
    if doc.is_encrypted: raise ValueError("Password-protected PDFs are not supported.")
    text="\n".join(p.get_text("text") for p in doc).strip()
    if len(text)>=40: return text,"embedded_text",[]
    cmd=os.getenv("TESSERACT_CMD")
    if not cmd:
        default_cmd=Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        if default_cmd.is_file(): cmd=str(default_cmd)
    if cmd: pytesseract.pytesseract.tesseract_cmd=cmd
    try:
        pages=[]
        for page in doc:
            pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
            pages.append(pytesseract.image_to_string(Image.frombytes("RGB",[pix.width,pix.height],pix.samples)))
        ocr="\n".join(pages).strip()
    except pytesseract.TesseractNotFoundError: return text,"embedded_text_insufficient",["Tesseract is unavailable; scanned text could not be read."]
    return (ocr,"ocr",[]) if ocr else (text,"ocr_empty",["OCR returned no readable text."])
