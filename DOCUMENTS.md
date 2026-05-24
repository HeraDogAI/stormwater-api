# Florida Stormwater Rule Documents to Ingest

Download these PDFs and run ingest.py for each one.
All documents are publicly available from FDEP and WMD websites.

## FDEP Documents

| Document | URL | ingest.py doc-id |
|----------|-----|-----------------|
| FLR10 Construction General Permit | https://www.flrules.org/gateway/ruleNo.asp?id=62-621.300(4) | flr10 |
| Chapter 62-330 F.A.C. (ERP) | https://www.flrules.org/gateway/ChapterHome.asp?Chapter=62-330 | erp_62330 |
| Chapter 62-621 F.A.C. (Generic Permits) | https://www.flrules.org/gateway/ChapterHome.asp?Chapter=62-621 | erp_62621 |
| Chapter 62-624 F.A.C. (MS4) | https://www.flrules.org/gateway/ChapterHome.asp?Chapter=62-624 | ms4_62624 |
| Chapter 62-302 F.A.C. (Water Quality) | https://www.flrules.org/gateway/ChapterHome.asp?Chapter=62-302 | wq_62302 |

## WMD Applicant's Handbooks

| Document | URL | ingest.py doc-id |
|----------|-----|-----------------|
| SFWMD AH Vol II | https://www.sfwmd.gov/permits-applicants | sfwmd_ah2 |
| SJRWMD AH Vol II | https://www.sjrwmd.com/permits | sjrwmd_ah2 |
| SWFWMD AH Vol II | https://www.swfwmd.state.fl.us/permits | swfwmd_ah2 |
| NWFWMD AH | https://www.nwfwmd.state.fl.us/permits | nwfwmd_ah |
| SRWMD AH | https://www.srwmd.org/permits | srwmd_ah |

## Ingest Commands

```bash
# Set your keys first
export OPENAI_API_KEY=sk-proj-...
export PINECONE_API_KEY=your-pinecone-key

# Run for each document
python ingest.py --file FLR10.pdf --source "FLR10 CGP (FDEP, 02/2015)" --doc-id flr10
python ingest.py --file 62-330.pdf --source "Chapter 62-330 F.A.C. ERP Rule" --doc-id erp_62330
python ingest.py --file 62-621.pdf --source "Chapter 62-621 F.A.C. Generic Permits" --doc-id erp_62621
python ingest.py --file 62-624.pdf --source "Chapter 62-624 F.A.C. MS4 Permit Rule" --doc-id ms4_62624
python ingest.py --file SWFWMD_AH_Vol2.pdf --source "SWFWMD Applicant's Handbook Vol II" --doc-id swfwmd_ah2
python ingest.py --file SJRWMD_AH_Vol2.pdf --source "SJRWMD Applicant's Handbook Vol II" --doc-id sjrwmd_ah2
python ingest.py --file SFWMD_AH_Vol2.pdf --source "SFWMD Applicant's Handbook Vol II" --doc-id sfwmd_ah2
```
