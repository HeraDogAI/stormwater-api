from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI
from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings
import os

app = FastAPI(
    title="Florida Stormwater Compliance Assistant API",
    description="RAG-powered stormwater compliance guidance grounded in verified FL rule documents.",
    version="2.0.0"
)

allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
allowed_origins = [o.strip() for o in allowed_origins]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def verify_api_key(key: Optional[str] = Security(api_key_header)):
    app_key = os.environ.get("APP_API_KEY")
    if app_key and key != app_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key.")
    return key


# ── KNOWN-VALID REGISTRIES ────────────────────────────────────────────────────
VALID_PERMIT_CODES = {
    "FLR10": "FDEP NPDES Construction General Permit (CGP)",
    "FLR04": "FDEP MS4 Phase II Generic Permit",
    "FLR05": "FDEP Multi-Sector Generic Permit (MSGP) for Industrial Stormwater",
    "FLR06": "FDEP Generic Permit for Large and Small MS4s",
}

VALID_RULE_CHAPTERS = {
    "62-25", "62-302", "62-303", "62-330", "62-521",
    "62-621", "62-624", "62-640", "40 CFR 122", "40 CFR 123",
}

SPLIT_JURISDICTION_COUNTIES = {
    "Marion":  "Primarily SJRWMD, but southwestern portion near Dunnellon falls under SWFWMD.",
    "Polk":    "Split between SFWMD (southern) and SWFWMD (northern).",
    "Levy":    "Split between SRWMD (eastern) and SWFWMD (western coastal).",
    "Citrus":  "Primarily SWFWMD with partial SRWMD overlap.",
    "Alachua": "Primarily SRWMD with partial SJRWMD overlap.",
}

PINECONE_INDEX = "stormwater-fl"
TOP_K_CHUNKS   = 5  # Number of document chunks to retrieve per query


# ── RAG RETRIEVAL ─────────────────────────────────────────────────────────────
def retrieve_context(query: str, openai_key: str, pinecone_key: str) -> tuple[str, list[str]]:
    """
    Embed the query, search Pinecone, return (context_text, source_list).
    Falls back gracefully if Pinecone is not configured or index is empty.
    """
    if not pinecone_key:
        return "", []

    try:
        embeddings = OpenAIEmbeddings(api_key=openai_key, model="text-embedding-3-small")
        query_vector = embeddings.embed_query(query)

        pc    = Pinecone(api_key=pinecone_key)
        index = pc.Index(PINECONE_INDEX)
        results = index.query(vector=query_vector, top_k=TOP_K_CHUNKS, include_metadata=True)

        if not results.matches:
            return "", []

        chunks  = []
        sources = []
        for match in results.matches:
            if match.score > 0.70:  # Only use high-confidence matches
                chunks.append(match.metadata.get("text", ""))
                source = match.metadata.get("source", "Unknown source")
                chunk_num = match.metadata.get("chunk", "?")
                if source not in sources:
                    sources.append(source)

        context = "\n\n---\n\n".join(chunks)
        return context, sources

    except Exception as e:
        # Graceful fallback — API still works without RAG
        print(f"RAG retrieval error: {e}")
        return "", []


# ── SYSTEM PROMPT ─────────────────────────────────────────────────────────────
BASE_SYSTEM_PROMPT = """You are an expert stormwater compliance specialist for Florida. You answer questions about MS4/NPDES permits, site inspections, and BMP selection.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. SOURCE GROUNDING
When RETRIEVED DOCUMENT SECTIONS are provided, you MUST base your answer on them.
Always cite the source document in your answer: "According to [Source Name]..."
If retrieved sections don't cover the question, say so and answer from verified knowledge only.

2. PERMIT CODE VERIFICATION
Valid Florida permits: FLR10, FLR04, FLR05, FLR06.
Valid rule chapters: 62-25, 62-302, 62-303, 62-330, 62-521, 62-621, 62-624, 40 CFR 122/123.
If a user references any permit or rule NOT in these lists, refuse and flag it:
"I don't recognize [X] as a valid Florida stormwater permit or rule. I won't elaborate on unverified citations."

3. NEVER ACCEPT FABRICATED PREMISES
If a user states a threshold or rule as fact that conflicts with verified Florida requirements, correct them directly:
"The value you've mentioned doesn't match verified Florida requirements. The correct value is [X]."

4. VERIFIED FLORIDA THRESHOLDS (never substitute federal EPA CGP values):
- FLR10 post-storm inspection: 0.5 inches (NOT 0.25" — that is the federal EPA CGP)
- FLR10 inspection citation: Part 4.6 (NOT Part 4.2.1)
- ERP wet detention residence time: 14 days — STATEWIDE for ALL WMDs
- ERP littoral zone: 35% of normal pool — STATEWIDE for ALL WMDs
- OFW treatment volume: 1.5" or 3.75 × impervious (50% increase over standard)
- Stabilization: 14 days standard, 7 days for high-quality waters
- Sediment basin: Required at 10+ disturbed acres draining to common point — 3,600 cubic feet of storage per acre drained (Part 5.6 FLR10). For less than 10 acres, sediment basins are recommended but NOT required.

5. WMD CRITERIA ARE STATEWIDE HARMONIZED
Do NOT invent WMD-specific differences under Chapter 62-330 F.A.C. unless citing a verified section from the WMD's Applicant's Handbook.

6. CITATION DISCIPLINE
Only cite section numbers confirmed in retrieved documents or verified knowledge.
Never fabricate a section number. If unsure, say "verify the current section in [document name]."

7. CONFIDENCE TIERS — label every response:
🟢 FRAMEWORK: Established regulatory structure — high confidence
🟡 THRESHOLD: Numerical value — verify against source document
🔴 ENGINEERING: Site-specific design — requires licensed engineer review

8. End every response with:
"⚠ Verify all citations, permit numbers, and thresholds against the current source document before relying on this for compliance work."
"""

def build_system_prompt(context: str, sources: list[str]) -> str:
    if not context:
        return BASE_SYSTEM_PROMPT + "\n\n[No document sections retrieved — answering from verified knowledge only.]"

    source_list = "\n".join(f"  - {s}" for s in sources)
    return BASE_SYSTEM_PROMPT + f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RETRIEVED DOCUMENT SECTIONS
Sources: 
{source_list}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Base your answer on the retrieved sections above. Cite the source by name.
"""


# ── MODELS ────────────────────────────────────────────────────────────────────
class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: Optional[list[Message]] = []
    county: Optional[str] = None
    wmd: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str
    history: list[Message]
    sources: list[str] = []
    split_jurisdiction_warning: Optional[str] = None
    rag_active: bool = False


# ── ROUTES ────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "tool": "Florida Stormwater Compliance Assistant API", "state": "FL", "version": "2.0.0", "rag": True}

@app.get("/health")
def health():
    pinecone_configured = bool(os.environ.get("PINECONE_API_KEY"))
    return {"status": "healthy", "rag_enabled": pinecone_configured}

@app.get("/topics")
def topics():
    return {
        "state": "FL",
        "topics": [
            {"id": "npdes",      "label": "NPDES / FLR10 CGP",     "description": "Construction general permit, NOI, SWPPP, inspections"},
            {"id": "ms4",        "label": "MS4 Compliance",         "description": "Phase I/II MS4 permits, six MCMs, annual reports"},
            {"id": "erp",        "label": "ERP Stormwater",         "description": "Chapter 62-330 F.A.C., treatment volume, attenuation"},
            {"id": "inspection", "label": "Site Inspection",        "description": "FL inspection forms, frequencies, corrective actions"},
            {"id": "bmp",        "label": "BMP Selection & Sizing", "description": "Florida-specific BMPs for flat terrain, high water table"},
            {"id": "wmd",        "label": "WMD Requirements",       "description": "SFWMD, SJRWMD, SWFWMD, NWFWMD, SRWMD basin rules"},
        ]
    }

@app.get("/wmds")
def wmds():
    return {
        "water_management_districts": [
            {"id": "SFWMD",  "name": "South Florida Water Management District",     "counties": ["Miami-Dade","Broward","Palm Beach","Hendry","Glades","Collier","Monroe","Martin","St. Lucie","Okeechobee","Indian River","Lake"]},
            {"id": "SJRWMD", "name": "St. Johns River Water Management District",  "counties": ["Brevard","Duval","Flagler","Indian River","Lake","Marion","Orange","Osceola","Putnam","Seminole","St. Johns","Volusia","Clay","Alachua"]},
            {"id": "SWFWMD", "name": "Southwest Florida Water Management District","counties": ["Citrus","DeSoto","Hardee","Hernando","Highlands","Hillsborough","Manatee","Pasco","Pinellas","Polk","Sarasota","Charlotte"]},
            {"id": "NWFWMD", "name": "Northwest Florida Water Management District","counties": ["Bay","Calhoun","Escambia","Franklin","Gadsden","Gulf","Holmes","Jackson","Leon","Okaloosa","Santa Rosa","Walton","Washington"]},
            {"id": "SRWMD",  "name": "Suwannee River Water Management District",   "counties": ["Alachua","Baker","Bradford","Columbia","Dixie","Gilchrist","Hamilton","Lafayette","Levy","Madison","Suwannee","Taylor","Union"]},
        ]
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, _: str = Depends(verify_api_key)):
    openai_key   = os.environ.get("OPENAI_API_KEY")
    pinecone_key = os.environ.get("PINECONE_API_KEY", "")

    if not openai_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured.")

    # Split-jurisdiction warning
    split_warning = None
    if req.county and req.county in SPLIT_JURISDICTION_COUNTIES:
        split_warning = f"⚠ {req.county} County has dual WMD jurisdiction: {SPLIT_JURISDICTION_COUNTIES[req.county]}"

    # Build context prefix
    context_parts = ["[State: Florida]"]
    if req.county:
        context_parts.append(f"[County: {req.county}]")
        if split_warning:
            context_parts.append(f"[WARNING: Split jurisdiction — {SPLIT_JURISDICTION_COUNTIES[req.county]}]")
    if req.wmd:
        context_parts.append(f"[WMD: {req.wmd}]")
    context_prefix = " ".join(context_parts)
    full_query = f"{context_prefix} {req.message}"

    # ── RAG retrieval ──
    retrieved_context, sources = retrieve_context(full_query, openai_key, pinecone_key)
    rag_active = bool(retrieved_context)

    # ── Build messages ──
    system_prompt = build_system_prompt(retrieved_context, sources)
    messages = [{"role": "system", "content": system_prompt}]
    for m in req.history:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": full_query})

    # ── Call OpenAI ──
    client = OpenAI(api_key=openai_key)
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=1024,
            temperature=0.1,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI API error: {str(e)}")

    reply_text = response.choices[0].message.content.strip()

    updated_history = req.history + [
        Message(role="user", content=req.message),
        Message(role="assistant", content=reply_text),
    ]

    return ChatResponse(
        reply=reply_text,
        history=updated_history,
        sources=sources,
        split_jurisdiction_warning=split_warning,
        rag_active=rag_active,
    )
