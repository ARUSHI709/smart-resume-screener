# Smart Resume Screener

A local resume-screening API and dashboard built to explore a practical hiring workflow:
parse a resume, save the extracted information, and compare it with a job description. It
accepts text or searchable PDF resumes and returns a ranked, explainable shortlist.

## Run

Use Python 3.11+, then:

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

Open `http://127.0.0.1:8000`. Upload a PDF or `.txt` resume (or paste text), then paste the job description and select a minimum score. Data stays in `data/screener.db`.

To try it quickly, copy the contents of [`examples/jane-doe.txt`](examples/jane-doe.txt)
into the resume field and [`examples/backend-engineer-job.txt`](examples/backend-engineer-job.txt)
into the job-description field.

## Architecture

`static/index.html` -> standard-library HTTP API in `app.py` -> SQLite.

`POST /api/resumes` parses text or PDF; `GET /api/candidates` lists extracted records; `POST /api/screen` returns ranked matches. The score combines recognized-skill coverage (65%), job/resume term overlap (25%), and stated-experience fit (10%). This makes each result reproducible and easy to audit.

## Design decisions

I chose a small standard-library HTTP server and SQLite to keep setup simple and make the
data flow easy to inspect during a demo. The application is intentionally local-first: a
resume is stored only in the local SQLite file unless the optional LLM feature is enabled.

The rule score gives skills the highest weight because the job description explicitly names
them. Keyword overlap contributes less because it is useful context but not proof of a skill.
Experience contributes the remaining weight and is capped once the stated requirement is
met. These weights are a starting point rather than a hiring policy, and should be tuned with
reviewer feedback and representative examples.

I kept the rule-based score even with LLM support for two reasons: the result is predictable
when there is no API key, and it provides a fallback when the provider is unavailable or
returns invalid output. Every result says which scoring method produced it.

### Known limitations

- PDF extraction works only for searchable PDFs, not image-only scans.
- Skills come from a deliberately small alias list, so uncommon technologies may be missed.
- The first suitable line of a resume is used as the candidate name; this should be replaced
  with a dedicated parser for production use.
- A score is never a hiring decision. A human must review the original resume and apply
  consistent criteria.

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
