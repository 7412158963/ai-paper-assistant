from pathlib import Path

import fitz


def extract_text_from_pdf(pdf_path: str | Path) -> dict:
    path = Path(pdf_path)

    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    doc = fitz.open(path)
    pages = []
    full_text_parts = []

    for page_index in range(len(doc)):
        page = doc[page_index]
        text = page.get_text("text")

        pages.append(
            {
                "page": page_index + 1,
                "text": text,
                "char_count": len(text),
            }
        )
        full_text_parts.append(text)

    full_text = "\n\n".join(full_text_parts)

    return {
        "file_name": path.name,
        "page_count": len(doc),
        "char_count": len(full_text),
        "text": full_text,
        "pages": pages,
    }
