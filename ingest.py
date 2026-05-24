"""
ingest.py — Run this ONCE to load Florida stormwater rule documents into Pinecone.

Usage:
  pip install -r requirements.txt
  python ingest.py --file path/to/FLR10.pdf --source "FLR10 CGP" --doc-id flr10
  python ingest.py --file path/to/62-330.pdf --source "Chapter 62-330 F.A.C." --doc-id erp_62330
  python ingest.py --file path/to/SWFWMD_AH_Vol2.pdf --source "SWFWMD Applicant's Handbook Vol II" --doc-id swfwmd_ah2

Documents to ingest (download from FDEP / WMD websites):
  - FLR10 Construction General Permit (FDEP)
  - Chapter 62-330 F.A.C. (ERP Rule)
  - Chapter 62-621 F.A.C. (Generic Permits)
  - Chapter 62-624 F.A.C. (MS4 Generic Permit)
  - Chapter 62-302 F.A.C. (Surface Water Quality Standards)
  - SFWMD Applicant's Handbook Vol II
  - SJRWMD Applicant's Handbook Vol II
  - SWFWMD Applicant's Handbook Vol II
  - NWFWMD Applicant's Handbook
  - SRWMD Applicant's Handbook
"""

import argparse
import os
from pypdf import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone, ServerlessSpec

PINECONE_INDEX = "stormwater-fl"
CHUNK_SIZE     = 800
CHUNK_OVERLAP  = 150


def load_pdf(path: str) -> str:
    reader = PdfReader(path)
    text = ""
    for i, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        text += f"\n[Page {i+1}]\n{page_text}"
    return text


def ingest(file_path: str, source_name: str, doc_id: str):
    openai_key  = os.environ["OPENAI_API_KEY"]
    pinecone_key = os.environ["PINECONE_API_KEY"]

    print(f"Loading {file_path}...")
    raw_text = load_pdf(file_path)
    print(f"  Extracted {len(raw_text):,} characters")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " "],
    )
    chunks = splitter.split_text(raw_text)
    print(f"  Split into {len(chunks)} chunks")

    pc = Pinecone(api_key=pinecone_key)

    if PINECONE_INDEX not in [i.name for i in pc.list_indexes()]:
        print(f"  Creating Pinecone index '{PINECONE_INDEX}'...")
        pc.create_index(
            name=PINECONE_INDEX,
            dimension=1536,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )

    index = pc.Index(PINECONE_INDEX)
    embeddings = OpenAIEmbeddings(api_key=openai_key, model="text-embedding-3-small")

    print(f"  Embedding and upserting {len(chunks)} chunks...")
    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        vectors = embeddings.embed_documents(batch)
        upsert_data = [
            (
                f"{doc_id}_chunk_{i+j}",
                vectors[j],
                {"text": batch[j], "source": source_name, "doc_id": doc_id, "chunk": i+j}
            )
            for j in range(len(batch))
        ]
        index.upsert(vectors=upsert_data)
        print(f"    Upserted chunks {i} to {i+len(batch)}")

    print(f"✅ Done — {len(chunks)} chunks from '{source_name}' loaded into Pinecone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file",   required=True, help="Path to PDF file")
    parser.add_argument("--source", required=True, help="Human-readable source name")
    parser.add_argument("--doc-id", required=True, help="Short ID for this document")
    args = parser.parse_args()
    ingest(args.file, args.source, args.doc_id)
