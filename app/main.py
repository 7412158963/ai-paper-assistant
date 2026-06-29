import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import load_env_file
from app.services.llm_service import LLMServiceError, answer_with_context
from app.services.pdf_parser import extract_text_from_pdf
from app.services.text_cleaner import clean_extracted_text
from app.services.text_splitter import split_text_into_chunks
from app.services.vector_store import get_vector_store_status, index_chunks, search_chunks


load_env_file()

MAX_QUESTION_LENGTH = 500
DEFAULT_TOP_K = 2
MAX_TOP_K = 3

app = FastAPI(
    title="AI Paper Reading Assistant",
    description="PDF upload and text extraction service",
    version="0.1.0",
)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "storage" / "uploads"
EXTRACTED_DIR = BASE_DIR / "storage" / "extracted"
CHUNKS_DIR = BASE_DIR / "storage" / "chunks"
VECTOR_DB_DIR = BASE_DIR / "storage" / "vector_db"
QA_HISTORY_DIR = BASE_DIR / "storage" / "qa_history"
PAPERS_FILE = BASE_DIR / "storage" / "papers.json"
STATIC_DIR = BASE_DIR / "static"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
QA_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class SearchRequest(BaseModel):
    query: str
    top_k: int = DEFAULT_TOP_K


class AskRequest(BaseModel):
    question: str
    top_k: int = DEFAULT_TOP_K


def _validate_question(question: str) -> str:
    cleaned = question.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if len(cleaned) > MAX_QUESTION_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Question is too long. Maximum length is {MAX_QUESTION_LENGTH} characters.",
        )

    return cleaned


def _validate_top_k(top_k: int) -> int:
    if top_k < 1 or top_k > MAX_TOP_K:
        raise HTTPException(
            status_code=400,
            detail=f"top_k must be between 1 and {MAX_TOP_K} to control LLM cost.",
        )

    return top_k


def _load_paper_records() -> dict:
    if not PAPERS_FILE.exists():
        return {}

    try:
        payload = json.loads(PAPERS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    papers = payload.get("papers", {})
    return papers if isinstance(papers, dict) else {}


def _save_paper_records(records: dict) -> None:
    PAPERS_FILE.write_text(
        json.dumps({"papers": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _upsert_paper_record(
    paper_id: str,
    original_filename: str,
    page_count: int,
    char_count: int,
) -> dict:
    records = _load_paper_records()
    now = datetime.now(timezone.utc).isoformat()
    record = records.get(paper_id, {})
    record.update(
        {
            "paper_id": paper_id,
            "original_filename": original_filename,
            "page_count": page_count,
            "char_count": char_count,
            "updated_at": now,
        }
    )
    record.setdefault("uploaded_at", now)
    records[paper_id] = record
    _save_paper_records(records)
    return record


def _discover_paper_ids() -> set[str]:
    paper_ids = set()
    for directory, suffix in (
        (UPLOAD_DIR, ".pdf"),
        (EXTRACTED_DIR, ".txt"),
        (CHUNKS_DIR, ".json"),
        (QA_HISTORY_DIR, ".json"),
    ):
        for path in directory.glob(f"*{suffix}"):
            paper_ids.add(path.stem)
    return paper_ids


def _load_index_counts() -> dict[str, int]:
    store_path = VECTOR_DB_DIR / "paper_chunks.json"
    if not store_path.exists():
        return {}

    try:
        store = json.loads(store_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    counts: dict[str, int] = {}
    for item in store.get("items", []):
        paper_id = item.get("metadata", {}).get("paper_id")
        if paper_id:
            counts[paper_id] = counts.get(paper_id, 0) + 1
    return counts


def _build_paper_summary(
    paper_id: str,
    record: dict | None = None,
    indexed_count: int = 0,
) -> dict:
    record = record or {}
    pdf_path = UPLOAD_DIR / f"{paper_id}.pdf"
    txt_path = EXTRACTED_DIR / f"{paper_id}.txt"
    chunks_path = CHUNKS_DIR / f"{paper_id}.json"

    char_count = record.get("char_count")
    if char_count is None and txt_path.exists():
        char_count = len(txt_path.read_text(encoding="utf-8"))

    return {
        "paper_id": paper_id,
        "original_filename": record.get("original_filename") or pdf_path.name,
        "uploaded_at": record.get("uploaded_at"),
        "updated_at": record.get("updated_at"),
        "page_count": record.get("page_count"),
        "char_count": char_count,
        "has_pdf": pdf_path.exists(),
        "has_text": txt_path.exists(),
        "has_chunks": chunks_path.exists(),
        "indexed_count": indexed_count,
        "qa_count": len(_load_qa_history(paper_id)),
    }


def _qa_history_path(paper_id: str) -> Path:
    return QA_HISTORY_DIR / f"{paper_id}.json"


def _load_qa_history(paper_id: str) -> list[dict]:
    history_path = _qa_history_path(paper_id)
    if not history_path.exists():
        return []

    try:
        payload = json.loads(history_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    items = payload.get("items", [])
    return items if isinstance(items, list) else []


def _save_qa_history(paper_id: str, items: list[dict]) -> None:
    history_path = _qa_history_path(paper_id)
    history_path.write_text(
        json.dumps(
            {
                "paper_id": paper_id,
                "count": len(items),
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _append_qa_history(
    paper_id: str,
    question: str,
    answer: str,
    mode: str,
    model: str | None,
    top_k: int,
    sources: list[dict],
) -> dict:
    items = _load_qa_history(paper_id)
    item = {
        "qa_id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "paper_id": paper_id,
        "question": question,
        "answer": answer,
        "mode": mode,
        "model": model,
        "top_k": top_k,
        "sources": sources,
    }
    items.insert(0, item)
    _save_qa_history(paper_id, items)
    return item


@app.get("/")
def health_check():
    return {
        "status": "ok",
        "message": "AI Paper Reading Assistant API is running",
    }


@app.get("/app")
def web_app():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/ui")
def redirect_to_app():
    return RedirectResponse(url="/app")


@app.get("/papers")
def list_papers():
    records = _load_paper_records()
    paper_ids = _discover_paper_ids() | set(records.keys())
    index_counts = _load_index_counts()

    papers = [
        _build_paper_summary(
            paper_id=paper_id,
            record=records.get(paper_id),
            indexed_count=index_counts.get(paper_id, 0),
        )
        for paper_id in paper_ids
    ]
    papers.sort(
        key=lambda item: item.get("uploaded_at") or item.get("updated_at") or item["paper_id"],
        reverse=True,
    )

    return {
        "count": len(papers),
        "papers": papers,
    }


@app.post("/papers/upload")
async def upload_paper(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    paper_id = str(uuid4())
    pdf_path = UPLOAD_DIR / f"{paper_id}.pdf"
    txt_path = EXTRACTED_DIR / f"{paper_id}.txt"

    try:
        content = await file.read()

        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        pdf_path.write_bytes(content)

        result = extract_text_from_pdf(pdf_path)
        txt_path.write_text(result["text"], encoding="utf-8")
        record = _upsert_paper_record(
            paper_id=paper_id,
            original_filename=file.filename,
            page_count=result["page_count"],
            char_count=result["char_count"],
        )

        return JSONResponse(
            {
                "paper_id": paper_id,
                "original_filename": file.filename,
                "uploaded_at": record["uploaded_at"],
                "saved_pdf": str(pdf_path),
                "saved_text": str(txt_path),
                "page_count": result["page_count"],
                "char_count": result["char_count"],
                "has_pdf": True,
                "has_text": True,
                "has_chunks": False,
                "indexed_count": 0,
                "qa_count": 0,
                "preview": result["text"][:1000],
            }
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF processing failed: {exc}") from exc


@app.get("/papers/{paper_id}/text")
def get_paper_text(paper_id: str):
    txt_path = EXTRACTED_DIR / f"{paper_id}.txt"

    if not txt_path.exists():
        raise HTTPException(status_code=404, detail="Extracted text not found")

    text = txt_path.read_text(encoding="utf-8")
    cleaned_text = clean_extracted_text(text)

    return {
        "paper_id": paper_id,
        "char_count": len(cleaned_text),
        "text": cleaned_text,
    }


@app.post("/papers/{paper_id}/chunks")
def create_paper_chunks(paper_id: str, chunk_size: int = 1000, overlap: int = 150):
    txt_path = EXTRACTED_DIR / f"{paper_id}.txt"
    chunks_path = CHUNKS_DIR / f"{paper_id}.json"

    if not txt_path.exists():
        raise HTTPException(status_code=404, detail="Extracted text not found")

    try:
        text = txt_path.read_text(encoding="utf-8")
        chunks = split_text_into_chunks(
            text=text,
            paper_id=paper_id,
            chunk_size=chunk_size,
            overlap=overlap,
        )

        payload = {
            "paper_id": paper_id,
            "chunk_size": chunk_size,
            "overlap": overlap,
            "chunk_count": len(chunks),
            "chunks": chunks,
        }
        chunks_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "paper_id": paper_id,
            "chunk_count": len(chunks),
            "saved_chunks": str(chunks_path),
            "preview": chunks[:3],
        }

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/papers/{paper_id}/chunks")
def get_paper_chunks(paper_id: str):
    chunks_path = CHUNKS_DIR / f"{paper_id}.json"

    if not chunks_path.exists():
        raise HTTPException(status_code=404, detail="Chunks not found")

    return json.loads(chunks_path.read_text(encoding="utf-8"))


@app.get("/papers/{paper_id}/qa-history")
def get_paper_qa_history(paper_id: str):
    return {
        "paper_id": paper_id,
        "count": len(_load_qa_history(paper_id)),
        "items": _load_qa_history(paper_id),
    }


@app.post("/papers/{paper_id}/index")
def index_paper_chunks(paper_id: str):
    txt_path = EXTRACTED_DIR / f"{paper_id}.txt"
    chunks_path = CHUNKS_DIR / f"{paper_id}.json"

    if not chunks_path.exists():
        if not txt_path.exists():
            raise HTTPException(status_code=404, detail="Extracted text not found")

        text = txt_path.read_text(encoding="utf-8")
        chunks = split_text_into_chunks(text=text, paper_id=paper_id)
        payload = {
            "paper_id": paper_id,
            "chunk_size": 1000,
            "overlap": 150,
            "chunk_count": len(chunks),
            "chunks": chunks,
        }
        chunks_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return index_chunks(chunks_path=chunks_path, vector_db_dir=VECTOR_DB_DIR)


@app.post("/papers/{paper_id}/search")
def search_paper_chunks(paper_id: str, request: SearchRequest):
    try:
        query = _validate_question(request.query)
        top_k = _validate_top_k(request.top_k)
        return search_chunks(
            paper_id=paper_id,
            query=query,
            top_k=top_k,
            vector_db_dir=VECTOR_DB_DIR,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/papers/{paper_id}/ask")
def ask_paper(paper_id: str, request: AskRequest):
    try:
        question = _validate_question(request.question)
        top_k = _validate_top_k(request.top_k)
        search_result = search_chunks(
            paper_id=paper_id,
            query=question,
            top_k=top_k,
            vector_db_dir=VECTOR_DB_DIR,
        )

        if search_result["hit_count"] == 0:
            raise HTTPException(
                status_code=404,
                detail="No indexed chunks found for this paper. Run /index first.",
            )

        try:
            llm_result = answer_with_context(
                question=question,
                contexts=search_result["results"],
            )
        except LLMServiceError as exc:
            llm_result = {
                "mode": "llm_error",
                "answer": str(exc),
                "model": None,
            }

        sources = [
            {
                "chunk_id": item["metadata"]["chunk_id"],
                "chunk_index": item["metadata"]["chunk_index"],
                "score": item["score"],
                "text": item["text"],
            }
            for item in search_result["results"]
        ]
        history_item = _append_qa_history(
            paper_id=paper_id,
            question=question,
            answer=llm_result["answer"],
            mode=llm_result["mode"],
            model=llm_result["model"],
            top_k=top_k,
            sources=sources,
        )

        return {
            "paper_id": paper_id,
            "question": question,
            "answer": llm_result["answer"],
            "mode": llm_result["mode"],
            "model": llm_result["model"],
            "sources": sources,
            "qa_id": history_item["qa_id"],
            "created_at": history_item["created_at"],
            "cost_control": {
                "question_length": len(question),
                "top_k": top_k,
                "max_question_length": MAX_QUESTION_LENGTH,
                "max_top_k": MAX_TOP_K,
            },
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/vector-store/status")
def vector_store_status():
    return get_vector_store_status(vector_db_dir=VECTOR_DB_DIR)
