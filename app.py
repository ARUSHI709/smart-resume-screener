"""Smart Resume Screener: a small, dependency-light local web application."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "data" / "screener.db"

# Deliberately transparent: scoring is based on job-description terms, not protected attributes.
STOPWORDS = frozenset("a an and are as at be by for from in is it of on or that the this to with you your years experience required preferred".split())
SKILL_ALIASES = {
    "javascript": ("javascript", "js"), "typescript": ("typescript", "ts"),
    "python": ("python",), "sql": ("sql", "postgres", "mysql", "sqlite"),
    "aws": ("aws", "amazon web services"), "docker": ("docker",), "kubernetes": ("kubernetes", "k8s"),
    "react": ("react", "reactjs", "react.js"), "node.js": ("node", "node.js", "nodejs"),
    "machine learning": ("machine learning", "ml"), "data analysis": ("data analysis", "analytics"),
    "git": ("git",), "java": ("java",), "excel": ("excel",), "tableau": ("tableau",),
}

@dataclass
class Candidate:
    id: int
    name: str
    source_name: str
    resume_text: str
    skills: list[str]
    experience_years: float | None
    education: list[str]
    created_at: str

def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS candidates (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, source_name TEXT NOT NULL,
        resume_text TEXT NOT NULL, skills TEXT NOT NULL, experience_years REAL,
        education TEXT NOT NULL, created_at TEXT NOT NULL)""")
    return con

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()

def find_skills(text: str) -> list[str]:
    haystack = normalize(text)
    found = [canonical for canonical, aliases in SKILL_ALIASES.items()
             if any(re.search(r"(?<!\w)" + re.escape(a) + r"(?!\w)", haystack) for a in aliases)]
    return sorted(found)

def extract_years(text: str) -> float | None:
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", text.lower())
    return max(map(float, matches)) if matches else None

def find_education(text: str) -> list[str]:
    labels = []
    lower = text.lower()
    for label, pattern in [("PhD", r"\b(ph\.?d|doctorate)\b"), ("Master's", r"\b(m\.?s\.?|m\.?tech|mba|master'?s?)\b"), ("Bachelor's", r"\b(b\.?s\.?|b\.?tech|bachelor'?s?)\b")]:
        if re.search(pattern, lower): labels.append(label)
    return labels

def candidate_name(text: str, fallback: str) -> str:
    for line in text.splitlines()[:5]:
        cleaned = re.sub(r"[^A-Za-z .'-]", "", line).strip()
        if 3 <= len(cleaned) <= 60 and len(cleaned.split()) <= 5 and not re.search(r"resume|curriculum|email|phone", cleaned, re.I):
            return cleaned.title()
    return Path(fallback).stem.replace("_", " ").title() or "Unnamed candidate"

def parse_resume(text: str, source_name: str) -> dict:
    text = text.strip()
    if not text: raise ValueError("Resume content is empty.")
    return {"name": candidate_name(text, source_name), "source_name": source_name,
            "resume_text": text, "skills": find_skills(text), "experience_years": extract_years(text),
            "education": find_education(text)}

def insert_candidate(data: dict) -> Candidate:
    created = datetime.now(UTC).isoformat()
    with db() as con:
        cur = con.execute("INSERT INTO candidates(name,source_name,resume_text,skills,experience_years,education,created_at) VALUES(?,?,?,?,?,?,?)",
            (data["name"], data["source_name"], data["resume_text"], json.dumps(data["skills"]), data["experience_years"], json.dumps(data["education"]), created))
        row = con.execute("SELECT * FROM candidates WHERE id=?", (cur.lastrowid,)).fetchone()
    return row_to_candidate(row)

def row_to_candidate(row: sqlite3.Row) -> Candidate:
    return Candidate(row["id"], row["name"], row["source_name"], row["resume_text"], json.loads(row["skills"]), row["experience_years"], json.loads(row["education"]), row["created_at"])

def list_candidates() -> list[Candidate]:
    with db() as con: rows = con.execute("SELECT * FROM candidates ORDER BY created_at DESC").fetchall()
    return [row_to_candidate(r) for r in rows]

def job_terms(job: str) -> set[str]:
    words = re.findall(r"[a-z][a-z+#.]{1,}", normalize(job))
    return {w for w in words if w not in STOPWORDS}

def score(candidate: Candidate, job_description: str) -> dict:
    job_skills = set(find_skills(job_description)); candidate_skills = set(candidate.skills)
    matched = sorted(job_skills & candidate_skills); missing = sorted(job_skills - candidate_skills)
    terms = job_terms(job_description); resume_words = set(re.findall(r"[a-z][a-z+#.]{1,}", normalize(candidate.resume_text)))
    lexical = len(terms & resume_words) / len(terms) if terms else 0
    skill_coverage = len(matched) / len(job_skills) if job_skills else lexical
    years_req = extract_years(job_description)
    years_fit = 1 if not years_req else min((candidate.experience_years or 0) / years_req, 1)
    raw = .65 * skill_coverage + .25 * lexical + .10 * years_fit
    score_10 = round(raw * 10, 1)
    reason = f"Matched skills: {', '.join(matched) or 'none identified'}."
    if missing: reason += f" Gaps: {', '.join(missing)}."
    if years_req: reason += f" Experience: {candidate.experience_years or 0:g} years identified (role asks {years_req:g})."
    return {"candidate": public_candidate(candidate), "score": score_10, "matched_skills": matched, "missing_skills": missing, "justification": reason, "scoring_method": "rules_fallback"}

LLM_INSTRUCTIONS = """You evaluate resume fit only as decision support for a human recruiter.
Use only evidence from the supplied resume and job description. Do not infer or consider
protected characteristics, including age, race, ethnicity, gender, disability, religion,
nationality, marital status, or family status. Return a balanced fit score and concise,
evidence-based rationale. Do not make a hiring decision."""

FIT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "score": {"type": "number"},
        "matched_requirements": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "justification": {"type": "string"},
    },
    "required": ["score", "matched_requirements", "gaps", "justification"],
}

def llm_score(candidate: Candidate, job_description: str) -> dict | None:
    """Return a validated LLM result, or None when LLM scoring is unavailable."""
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI
        response = OpenAI().responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            store=False,
            instructions=LLM_INSTRUCTIONS,
            input=json.dumps({"candidate": public_candidate(candidate), "resume": candidate.resume_text,
                              "job_description": job_description}),
            text={"format": {"type": "json_schema", "name": "candidate_fit", "strict": True, "schema": FIT_SCHEMA}},
        )
        result = json.loads(response.output_text)
        score_10 = float(result["score"])
        matches, gaps, justification = result["matched_requirements"], result["gaps"], result["justification"]
        if (not 0 <= score_10 <= 10 or not isinstance(matches, list) or not isinstance(gaps, list)
                or not all(isinstance(item, str) for item in matches + gaps)
                or not isinstance(justification, str) or not 1 <= len(justification.strip()) <= 800):
            raise ValueError("LLM result did not meet validation requirements")
        return {"candidate": public_candidate(candidate), "score": round(score_10, 1),
                "matched_skills": matches, "missing_skills": gaps,
                "justification": justification.strip(), "scoring_method": "llm"}
    except Exception:
        # Screening remains available if credentials, the provider, or output validation fail.
        return None

def screen_candidate(candidate: Candidate, job_description: str) -> dict:
    return llm_score(candidate, job_description) or score(candidate, job_description)

def public_candidate(c: Candidate) -> dict:
    result = asdict(c); result.pop("resume_text", None); return result

def extract_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader
        from io import BytesIO
        return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
    except Exception as exc: raise ValueError(f"Could not extract text from PDF: {exc}") from exc

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None: print(fmt % args)
    def send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode(); self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def read_body(self) -> bytes: return self.rfile.read(int(self.headers.get("Content-Length", "0")))
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            body = (APP_DIR / "static" / "index.html").read_bytes(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif path == "/api/candidates": self.send_json([public_candidate(c) for c in list_candidates()])
        else: self.send_json({"error": "Not found"}, 404)
    def do_POST(self) -> None:
        try:
            path = urlparse(self.path).path
            if path == "/api/resumes":
                raw = self.read_body(); ctype = self.headers.get("Content-Type", "")
                if ctype.startswith("application/json"):
                    payload = json.loads(raw); data = parse_resume(payload.get("text", ""), payload.get("source_name", "pasted-resume.txt"))
                else:
                    source = self.headers.get("X-Filename", "uploaded-resume.pdf")
                    data = parse_resume(extract_pdf(raw) if "pdf" in ctype else raw.decode("utf-8"), source)
                self.send_json(public_candidate(insert_candidate(data)), 201)
            elif path == "/api/screen":
                payload = json.loads(self.read_body()); job = payload.get("job_description", "").strip()
                if not job: raise ValueError("A job description is required.")
                threshold = float(payload.get("minimum_score", 0)); results = [screen_candidate(c, job) for c in list_candidates()]
                self.send_json(sorted([r for r in results if r["score"] >= threshold], key=lambda r: r["score"], reverse=True))
            else: self.send_json({"error": "Not found"}, 404)
        except (ValueError, json.JSONDecodeError) as exc: self.send_json({"error": str(exc)}, 400)
        except Exception as exc: self.send_json({"error": "Server error", "detail": str(exc)}, 500)

def main() -> None:
    port = int(os.getenv("PORT", "8000")); print(f"Smart Resume Screener listening at http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()

if __name__ == "__main__": main()
