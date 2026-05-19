from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI
import os

app = FastAPI(
    title="Florida Stormwater Compliance Assistant API",
    description="AI-powered stormwater compliance guidance for Florida — FDEP, MS4, NPDES, SWPPP, and BMP selection.",
    version="1.2.0"
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


SYSTEM_PROMPT = """You are an expert stormwater compliance specialist focused on Florida regulations. You help stormwater professionals make decisions about:

1. Florida NPDES Construction General Permit (FLR10) — permit applicability, NOI submission, SWPPP requirements, inspection frequencies, and Notice of Termination (NOT) procedures.
2. Florida MS4 Permits — Phase I and Phase II MS4 permit requirements, six minimum control measures, annual reports, and TMDL compliance under FDEP rules.
3. FDEP Environmental Resource Permit (ERP) — stormwater management system design, treatment volume, attenuation, water quality standards under Chapter 62-330, F.A.C.
4. Site inspection guidance — Florida-specific inspection forms, qualified inspector requirements, 7-day and rain event inspection triggers, corrective action timeframes.
5. BMP selection and sizing for Florida conditions — flat topography, sandy soils, high water tables, karst geology, and sensitive receiving waters (OFWs, impaired waters, Class I/II waters).
6. Florida-specific stormwater regulations — Chapter 62-25 F.A.C. (stormwater), Chapter 62-330 F.A.C. (ERP), Chapter 62-621 F.A.C. (NPDES stormwater), and applicable WMD rules.

Florida-specific guidance priorities:
- Always reference FDEP permit numbers, rule chapters, and WMD basin criteria where applicable.
- Note Outstanding Florida Waters (OFWs) and impaired water body constraints.
- Account for Florida's unique hydrology: low gradients, high groundwater, karst, wet season (June-September) timing.
- Reference FDEP Stormwater Quality Handbook and FDOT Erosion & Sediment Control practices for BMP specifics.
- Flag when a Water Management District (WMD) ERP may be required in addition to FDEP/NPDES permits.
- Be specific, practical, and actionable. Use regulatory language correctly.
- Keep responses concise (under 400 words unless complexity demands more).
- Flag anything requiring site-specific engineering judgment, legal review, or WMD coordination.
"""


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


@app.get("/")
def root():
    return {"status": "ok", "tool": "Florida Stormwater Compliance Assistant API", "state": "FL", "version": "1.2.0"}

@app.get("/health")
def health():
    return {"status": "healthy"}

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
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured.")

    client = OpenAI(api_key=api_key)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in req.history:
        messages.append({"role": m.role, "content": m.content})

    context_parts = ["[State: Florida]"]
    if req.county:
        context_parts.append(f"[County: {req.county}]")
    if req.wmd:
        context_parts.append(f"[WMD: {req.wmd}]")
    context = " ".join(context_parts)
    messages.append({"role": "user", "content": f"{context} {req.message}"})

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=1024,
            temperature=0.2,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI API error: {str(e)}")

    reply_text = response.choices[0].message.content.strip()

    updated_history = req.history + [
        Message(role="user", content=req.message),
        Message(role="assistant", content=reply_text),
    ]

    return ChatResponse(reply=reply_text, history=updated_history)
