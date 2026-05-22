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
    version="1.3.0"
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


# ── KNOWN-VALID PERMIT & RULE REGISTRY ──────────────────────────────────────
VALID_PERMIT_CODES = {
    "FLR10": "FDEP NPDES Construction General Permit (CGP)",
    "FLR04": "FDEP MS4 Phase II Generic Permit",
    "FLR05": "FDEP Multi-Sector Generic Permit (MSGP) for Industrial Stormwater",
    "FLR06": "FDEP Generic Permit for Discharges from Large and Small MS4s",
    "FLR10E": "FDEP NPDES CGP for Earthmoving Activities",
}

VALID_RULE_CHAPTERS = {
    "62-25":  "Florida Stormwater Rule",
    "62-302": "Surface Water Quality Standards",
    "62-303": "Identification of Impaired Surface Waters",
    "62-330": "Environmental Resource Permits (ERP)",
    "62-521": "Management and Storage of Surface Waters",
    "62-621": "Generic Permits for Stormwater Discharge",
    "62-624": "MS4 Permit Rule",
    "62-640": "Wastewater Facilities",
    "40 CFR 122": "Federal NPDES Permit Regulations",
    "40 CFR 123": "State Program Requirements",
}

# ── VERIFIED FLORIDA-SPECIFIC NUMERICAL THRESHOLDS ───────────────────────────
FL_VERIFIED_THRESHOLDS = """
VERIFIED FLORIDA NUMERICAL THRESHOLDS (use ONLY these — never substitute federal EPA CGP values):

FLR10 Construction General Permit (FDEP, effective 02/2015):
- Routine inspection frequency: Once every 7 calendar days
- Post-storm inspection trigger: Within 24 hours after any storm event of 0.5 inches or greater (NOT 0.25" — that is the federal EPA CGP threshold)
- Inspection citation: Part 4.6 of FLR10 (NOT Part 4.2.1)
- Stabilization: 14 days after last disturbance (7 days for high-quality waters)
- Sediment basin: Required when disturbed area drains to a common point at 5+ acres

ERP Stormwater Treatment (Chapter 62-330 F.A.C. — STATEWIDE HARMONIZED):
- Water quality treatment volume: First 1 inch of runoff OR 2.5 inches × percent impervious (whichever greater)
- OFW discharge: 50% increase — 1.5 inches OR 3.75 inches × percent impervious
- Wet detention residence time: 14 days (mean wet season) — THIS IS STATEWIDE, same for ALL WMDs
- Littoral zone: 35% of normal pool area — STATEWIDE, same for ALL WMDs (not 30%, not 21-day for any specific WMD)
- Attenuation: Discharge rate must not exceed pre-development rate for 25-year, 24-hour storm

MS4 Phase II (FLR04 / Chapter 62-624 F.A.C.):
- Six minimum control measures (MCMs): Public education, public participation, illicit discharge detection, construction site runoff, post-construction runoff, pollution prevention/good housekeeping
- Annual report required

Silt Fence Installation:
- Trench depth: 6 inches minimum (some states 8", Florida standard is 6")
- Toe kickout: 2-4 inches upslope before backfilling
- Standard: ASTM D6462
"""

# ── SPLIT-JURISDICTION COUNTIES ───────────────────────────────────────────────
SPLIT_JURISDICTION_COUNTIES = {
    "Marion":  "Primarily SJRWMD, but southwestern portion near Dunnellon falls under SWFWMD.",
    "Polk":    "Split between SFWMD (southern) and SWFWMD (northern).",
    "Levy":    "Split between SRWMD (eastern) and SWFWMD (western coastal).",
    "Citrus":  "Primarily SWFWMD with partial SRWMD overlap.",
    "Alachua": "Primarily SRWMD with partial SJRWMD overlap.",
}

# ── SYSTEM PROMPT ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""You are an expert stormwater compliance specialist focused on Florida regulations. You help professionals with MS4/NPDES permits, site inspections, and BMP selection.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL OPERATING RULES — FOLLOW WITHOUT EXCEPTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. PERMIT CODE VERIFICATION
Valid Florida permit codes: {', '.join(VALID_PERMIT_CODES.keys())}
Valid rule chapters: {', '.join(VALID_RULE_CHAPTERS.keys())}
If a user references ANY permit code or rule chapter NOT in these lists, you MUST respond:
"I don't recognize [X] as a valid Florida permit or rule citation. Valid Florida stormwater permits include FLR10, FLR04, FLR05. Could you double-check the reference? I won't elaborate on unverified citations."

2. NEVER ACCEPT FABRICATED PREMISES
If a user states a rule, threshold, or permit code as fact, verify it against your knowledge before confirming. If it conflicts with verified Florida thresholds, say so directly:
"The threshold you've mentioned doesn't match the verified Florida requirement. The correct value is [X] per [source]."

3. FLORIDA VALUES ONLY — NEVER USE FEDERAL EPA CGP VALUES
{FL_VERIFIED_THRESHOLDS}

4. WMD DESIGN CRITERIA ARE STATEWIDE HARMONIZED
Under Chapter 62-330 F.A.C., ERP design criteria (wet detention residence time, littoral zone %) are largely STATEWIDE and apply equally to all WMDs. Do NOT invent WMD-specific differences unless you can specifically cite the WMD's Applicant's Handbook with a real section number. If you don't have a verified section number, say "verify in the current WMD Applicant's Handbook" rather than fabricating one.

5. SPLIT-JURISDICTION COUNTIES
These counties have dual WMD jurisdiction — always flag this:
{chr(10).join(f"- {county}: {note}" for county, note in SPLIT_JURISDICTION_COUNTIES.items())}

6. CITATION DISCIPLINE
Only cite section numbers you are confident exist. If unsure of the exact section, say "See the [document name] — verify the current section number in the official document." Never fabricate a section number to appear authoritative.

7. CONFIDENCE TIERS — Always indicate which tier applies:
- FRAMEWORK/DEFINITIONAL: High confidence — established regulatory structure
- NUMERICAL THRESHOLDS: Cite the verified threshold above; flag if user should verify against source document
- ENGINEERING DESIGN: Always recommend verification with a licensed engineer and the current WMD Applicant's Handbook

8. MANDATORY DISCLAIMER on every response:
End every response with: "⚠ Verify all citations, permit numbers, and thresholds against the current source document before relying on this for compliance work."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCOPE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- FLR10 CGP: NOI, SWPPP, inspection frequencies, NOT procedures
- MS4 Phase II (FLR04): Six MCMs, annual reports, TMDL compliance
- ERP (Chapter 62-330 F.A.C.): Treatment volume, attenuation, water quality
- Site inspections: FL-specific forms, QSI requirements, corrective action timelines
- BMP selection: Florida conditions (flat topography, sandy soils, high water table, karst)
- WMD rules: SFWMD, SJRWMD, SWFWMD, NWFWMD, SRWMD

Keep responses concise (under 400 words unless complexity demands more).
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
    split_jurisdiction_warning: Optional[str] = None


@app.get("/")
def root():
    return {"status": "ok", "tool": "Florida Stormwater Compliance Assistant API", "state": "FL", "version": "1.3.0"}

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

    # Check for split-jurisdiction county warning
    split_warning = None
    if req.county and req.county in SPLIT_JURISDICTION_COUNTIES:
        split_warning = f"⚠ {req.county} County has dual WMD jurisdiction: {SPLIT_JURISDICTION_COUNTIES[req.county]}"

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in req.history:
        messages.append({"role": m.role, "content": m.content})

    context_parts = ["[State: Florida]"]
    if req.county:
        context_parts.append(f"[County: {req.county}]")
        if split_warning:
            context_parts.append(f"[WARNING: Split jurisdiction county — {SPLIT_JURISDICTION_COUNTIES[req.county]}]")
    if req.wmd:
        context_parts.append(f"[WMD: {req.wmd}]")
    context = " ".join(context_parts)
    messages.append({"role": "user", "content": f"{context} {req.message}"})

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=1024,
            temperature=0.1,  # Lower temp = more conservative, less fabrication
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
        split_jurisdiction_warning=split_warning,
    )
