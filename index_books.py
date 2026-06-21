import os
import time
import json
import chromadb
from chromadb.utils import embedding_functions

# ── Config ────────────────────────────────────────────────────────────────────
BOOK_DIR        = "/srv/ftp/dayone"
DB_PATH         = os.path.join(os.path.expanduser("~"), "juniper_vector_db")
CHECKPOINT_FILE = os.path.join(os.path.expanduser("~"), "juniper_index_checkpoint.json")
CHUNK_SIZE      = 1200   # max characters per chunk
CHUNK_STEP      = 900    # step between chunks, controls overlap
BATCH_SIZE      = 10     # chunks per ChromaDB write
PAGE_SLEEP      = 0.2    # seconds between pages to avoid hammering Ollama
# ─────────────────────────────────────────────────────────────────────────────

# ── PyMuPDF import check ──────────────────────────────────────────────────────
try:
    import fitz  # PyMuPDF
except ImportError:
    print("❌ PyMuPDF not installed. Run:")
    print("   ./juniper-env/bin/pip install pymupdf")
    exit(1)

# ── Load checkpoint ───────────────────────────────────────────────────────────
if os.path.exists(CHECKPOINT_FILE):
    with open(CHECKPOINT_FILE, "r") as f:
        completed = set(json.load(f))
    print(f"📋 Checkpoint found: {len(completed)} file(s) already indexed, skipping.\n")
else:
    completed = set()

# ── ChromaDB setup ────────────────────────────────────────────────────────────
chroma_client = chromadb.PersistentClient(path=DB_PATH)

ollama_ef = embedding_functions.OllamaEmbeddingFunction(
    url="http://localhost:11434/api/embeddings",
    model_name="all-minilm"
)

collection = chroma_client.get_or_create_collection(
    name="juniper_books",
    embedding_function=ollama_ef
)

pdf_files = sorted([f for f in os.listdir(BOOK_DIR) if f.endswith(".pdf")])
print(f"📚 Found {len(pdf_files)} PDF(s) to index into ChromaDB at {DB_PATH}\n")

total_chunks = 0


def line_aware_chunks(text, chunk_size, chunk_step):
    """
    Split text into overlapping chunks that always break on line boundaries.
    Never splits mid-line so Junos set commands and config stanzas stay intact.
    """
    lines = text.splitlines(keepends=True)
    chunks = []
    current_chunk = []
    current_len = 0
    i = 0

    while i < len(lines):
        line = lines[i]
        # If adding this line would exceed chunk_size and we already have content,
        # save the current chunk and start a new one with overlap
        if current_len + len(line) > chunk_size and current_chunk:
            chunk_text = "".join(current_chunk).strip()
            if chunk_text:
                chunks.append(chunk_text)

            # Rewind by chunk_step characters worth of lines for overlap
            overlap_len = 0
            overlap_lines = []
            for prev_line in reversed(current_chunk):
                if overlap_len + len(prev_line) > (chunk_size - chunk_step):
                    break
                overlap_lines.insert(0, prev_line)
                overlap_len += len(prev_line)

            current_chunk = overlap_lines
            current_len = overlap_len

        current_chunk.append(line)
        current_len += len(line)
        i += 1

    # Flush final chunk
    if current_chunk:
        chunk_text = "".join(current_chunk).strip()
        if chunk_text:
            chunks.append(chunk_text)

    return chunks


# ── Index each PDF ────────────────────────────────────────────────────────────
for file_idx, file in enumerate(pdf_files, 1):
    if file in completed:
        print(f"[{file_idx}/{len(pdf_files)}] Skipping (already indexed): {file}")
        continue

    filepath = os.path.join(BOOK_DIR, file)
    print(f"[{file_idx}/{len(pdf_files)}] Indexing: {file}")

    try:
        doc = fitz.open(filepath)
        file_chunks = 0
        batch_docs, batch_metas, batch_ids = [], [], []

        for page_num in range(len(doc)):
            page = doc[page_num]

            # PyMuPDF text extraction preserving layout (whitespace, indentation)
            text = page.get_text("text", sort=True)

            if not text or len(text.strip()) < 100:
                continue

            chunks = line_aware_chunks(text, CHUNK_SIZE, CHUNK_STEP)

            for chunk_idx, chunk in enumerate(chunks):
                doc_id = f"{file}_{page_num}_{chunk_idx}"
                batch_docs.append(chunk)
                batch_metas.append({"source": file, "page": page_num})
                batch_ids.append(doc_id)

                if len(batch_docs) >= BATCH_SIZE:
                    collection.add(documents=batch_docs, metadatas=batch_metas, ids=batch_ids)
                    batch_docs, batch_metas, batch_ids = [], [], []
                    file_chunks += BATCH_SIZE
                    total_chunks += BATCH_SIZE

            time.sleep(PAGE_SLEEP)

        doc.close()

        # Flush remaining batch
        if batch_docs:
            collection.add(documents=batch_docs, metadatas=batch_metas, ids=batch_ids)
            file_chunks += len(batch_docs)
            total_chunks += len(batch_docs)

        completed.add(file)
        with open(CHECKPOINT_FILE, "w") as f:
            json.dump(list(completed), f)

        print(f"    ✅ Done: {file_chunks} chunks indexed\n")

    except Exception as e:
        print(f"    ❌ Error indexing {file}: {e}\n")

print(f"🎉 Indexing complete! Total chunks: {total_chunks}")
