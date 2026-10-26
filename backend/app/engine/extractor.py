"""
[PROJECT_NAME] PyMuPDF Fast Byte-Stream Extractor
Company: [COMPANY_NAME]
"""

from typing import List, Dict, Any


class PDFExtractor:
    @staticmethod
    def extract_text_lines_from_bytes(pdf_bytes: bytes) -> List[str]:
        """
        Extract raw text lines from PDF in-memory bytes using PyMuPDF.
        Runs in <50ms without disk I/O.
        """
        import pymupdf

        lines: List[str] = []
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page in doc:
                text = page.get_text("text")
                for line in text.splitlines():
                    cleaned = line.strip()
                    if cleaned:
                        lines.append(cleaned)
        return lines

    @staticmethod
    def extract_structured_blocks_from_bytes(pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Extract structured blocks with coordinates from PDF in-memory bytes.
        """
        import pymupdf

        blocks_data: List[Dict[str, Any]] = []
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page_idx, page in enumerate(doc):
                page_blocks = page.get_text("blocks")
                for b in page_blocks:
                    # b format: (x0, y0, x1, y1, text, block_no, block_type)
                    if b[6] == 0:  # text block
                        blocks_data.append({
                            "page": page_idx + 1,
                            "bbox": (b[0], b[1], b[2], b[3]),
                            "text": b[4].strip()
                        })
        return blocks_data
