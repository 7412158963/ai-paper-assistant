from app.services.text_cleaner import clean_extracted_text


def split_text_into_chunks(
    text: str,
    paper_id: str,
    chunk_size: int = 1000,
    overlap: int = 150,
) -> list[dict]:
    cleaned_text = clean_extracted_text(text)

    if not cleaned_text:
        return []

    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks = []
    start = 0
    chunk_index = 0

    while start < len(cleaned_text):
        end = min(start + chunk_size, len(cleaned_text))

        if end < len(cleaned_text):
            paragraph_break = cleaned_text.rfind("\n\n", start, end)
            sentence_break = max(
                cleaned_text.rfind(". ", start, end),
                cleaned_text.rfind("? ", start, end),
                cleaned_text.rfind("! ", start, end),
                cleaned_text.rfind("。", start, end),
                cleaned_text.rfind("？", start, end),
                cleaned_text.rfind("！", start, end),
            )

            if paragraph_break > start + chunk_size // 2:
                end = paragraph_break
            elif sentence_break > start + chunk_size // 2:
                end = sentence_break + 1

        chunk_text = cleaned_text[start:end].strip()

        if chunk_text:
            chunks.append(
                {
                    "paper_id": paper_id,
                    "chunk_id": f"{paper_id}_chunk_{chunk_index:04d}",
                    "chunk_index": chunk_index,
                    "char_count": len(chunk_text),
                    "text": chunk_text,
                }
            )
            chunk_index += 1

        if end >= len(cleaned_text):
            break

        start = max(end - overlap, start + 1)

    return chunks
