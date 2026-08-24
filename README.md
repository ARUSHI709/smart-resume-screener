# Smart Resume Screener

A local, privacy-friendly resume screening API and dashboard. It accepts text or searchable PDF resumes, extracts skills/experience/education, stores the result in SQLite, and ranks candidates against a job description with a human-readable justification.

## Run

Use Python 3.11+, then:

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

Open `http://127.0.0.1:8000`. Upload a PDF or `.txt` resume (or paste text), then paste the job description and select a minimum score. Data stays in `data/screener.db`.

## Architecture

`static/index.html` -> standard-library HTTP API in `app.py` -> SQLite.

`POST /api/resumes` parses text or PDF; `GET /api/candidates` lists extracted records; `POST /api/screen` returns ranked matches. The score combines recognized-skill coverage (65%), job/resume term overlap (25%), and stated-experience fit (10%). This makes each result reproducible and easy to audit.

## LLM scoring

The application uses OpenAI structured output whenever `OPENAI_API_KEY` is configured;
otherwise it automatically falls back to the transparent rules score. Configure it on the
server (never in browser JavaScript):

```bash
export OPENAI_API_KEY="..."
export OPENAI_MODEL="gpt-5-mini" # optional
python3 app.py
```

The server asks the model for a schema-validated score, matched requirements, gaps, and an
evidence-based justification. It rejects malformed output and returns the rules fallback if
the provider is unavailable. Resume text is sent to the configured LLM provider only when
this option is enabled, so obtain appropriate consent and follow your retention policy.

The evaluation instructions are:

```text
Compare the candidate profile with the job description. Return JSON with a fit score 1-10,
matched requirements, missing requirements, and a 2-sentence evidence-based justification.
Do not infer or use protected characteristics (age, race, gender, disability, religion,
nationality, or marital/family status). Cite only evidence present in the supplied text.
```

The UI labels each result as an LLM assessment or rules fallback for auditability.

## Responsible use

Scores are decision support, not an automated hiring decision. Validate extraction, consider accessibility/formatting failures, and review every ranked result with consistent human criteria.
