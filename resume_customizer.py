"""PDF section 5.3 — tailor a resume to one job and export a PDF."""

import json
import re
import shutil
from pathlib import Path

from docx import Document

from llm_client import complete_json
from lock_util import close_word, word_lock
from settings import SCRATCH

SUMMARY = {"professional summary", "summary", "profile summary", "about me", "objective"}
PROJECTS = {
    "professional experience", "work experience", "experience",
    "projects", "project experience", "relevant experience",
}
SKILLS = {"technical skills", "skills", "core skills", "technical skills summary"}
STOP = {"education", "certifications", "certification", "awards", "publications"}

PROMPT = """You tailor a resume to a job post. Return JSON only with these keys:
rewritten_summary (string),
rewritten_paragraphs (array of strings, same length and order as the project paragraphs),
rewritten_skills (array of strings, same length as the skills lines).

Rules:
- Keep employers, dates, and titles unchanged.
- Do not invent companies, degrees, or tools.
- Use the job's technologies 2 or 3 times in each project paragraph, only where the original work supports them.
- Keep each paragraph about the same length.

Job description:
<<JD>>

Summary:
<<SUMMARY>>

Project paragraphs:
<<PROJECTS>>

Skills lines:
<<SKILLS>>
"""


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(":").lower()


def header_bucket(label: str):
    if label in SUMMARY:
        return "summary"
    if label in PROJECTS:
        return "projects"
    if label in SKILLS:
        return "skills"
    if label in STOP:
        return ""
    return None


def locate(document):
    # Walk body paragraphs, then any skills table, and keep the paragraph objects.
    sections = {"summary": [], "projects": [], "skills": []}
    mode = None
    for paragraph in document.paragraphs:
        bucket = header_bucket(norm(paragraph.text))
        if bucket is not None:
            mode = bucket
            continue
        if mode and paragraph.text.strip():
            sections[mode].append(paragraph)
    for table in document.tables:
        seen = set()
        skill_table = False
        paragraphs = []
        for row in table.rows:
            for cell in row.cells:
                marker = id(cell._tc)
                if marker in seen:
                    continue
                seen.add(marker)
                if norm(cell.text) in SKILLS:
                    skill_table = True
                paragraphs.extend(cell.paragraphs)
        if not skill_table:
            continue
        for paragraph in paragraphs:
            if paragraph.text.strip() and norm(paragraph.text) not in SKILLS:
                sections["skills"].append(paragraph)
    return sections


def write_runs(paragraph, text: str):
    # The first run keeps its font, size, bold, and color. Extra runs are cleared.
    runs = paragraph.runs
    if not runs:
        paragraph.add_run(text)
        return
    runs[0].text = text
    for run in runs[1:]:
        run.text = ""


def pack(sections):
    summary = "\n".join(paragraph.text for paragraph in sections["summary"])[:2000]
    projects = [paragraph.text[:800] for paragraph in sections["projects"][:12]]
    skills = [paragraph.text[:300] for paragraph in sections["skills"][:20]]
    return summary, projects, skills


def as_list(value):
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def fit(new_items, originals):
    items = list(new_items)
    if len(items) < len(originals):
        items.extend(originals[len(items):])
    return items[: len(originals)]


def apply(sections, data):
    summary = str(data.get("rewritten_summary") or "").strip()
    if summary and sections["summary"]:
        write_runs(sections["summary"][0], summary)
        for extra in sections["summary"][1:]:
            write_runs(extra, "")
    projects = sections["projects"][:12]
    skills = sections["skills"][:20]
    for paragraph, text in zip(projects, fit(as_list(data.get("rewritten_paragraphs")), [p.text for p in projects])):
        write_runs(paragraph, text)
    for paragraph, text in zip(skills, fit(as_list(data.get("rewritten_skills")), [p.text for p in skills])):
        write_runs(paragraph, text)


def tidy(document):
    # Collapse double spaces. Stacked blank paragraphs lose their extra gap.
    previous_blank = False
    for paragraph in document.paragraphs:
        text = re.sub(r"[ \t]{2,}", " ", paragraph.text).strip()
        if text != paragraph.text:
            write_runs(paragraph, text)
        blank = not paragraph.text.strip()
        if blank and previous_blank:
            paragraph.paragraph_format.space_before = 0
            paragraph.paragraph_format.space_after = 0
        previous_blank = blank


def ensure_docx(source: Path) -> Path:
    # PDF templates are turned into DOCX once so the XML runs can be edited.
    if source.suffix.lower() == ".docx":
        return source
    if source.suffix.lower() != ".pdf":
        raise ValueError("Resume must be a .docx or .pdf")
    target = SCRATCH / f"{source.stem}.docx"
    from pdf2docx import Converter
    converter = Converter(str(source))
    try:
        converter.convert(str(target))
    finally:
        converter.close()
    return target


def to_pdf(docx_path: Path, pdf_path: Path):
    # Word COM is single-threaded. The lock plus a clean WINWORD process keeps it stable.
    with word_lock():
        close_word()
        from docx2pdf import convert
        convert(str(docx_path), str(pdf_path))
    if not pdf_path.exists():
        raise RuntimeError("Word did not create the PDF")
    from pypdf import PdfReader
    if not PdfReader(str(pdf_path)).pages:
        raise RuntimeError("PDF has no pages")


def customize_resume(job_description: str, source, destination, candidate_key: str):
    # candidate_key matches the hook signature. Heading detection does not use it.
    source = Path(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    working = SCRATCH / f"{destination.stem}.docx"
    shutil.copy(ensure_docx(source), working)
    document = Document(str(working))
    sections = locate(document)
    summary, projects, skills = pack(sections)
    if not summary and not projects and not skills:
        raise RuntimeError("Could not find a summary, projects, or skills section in the resume")
    prompt = (
        PROMPT.replace("<<JD>>", (job_description or "")[:5000])
        .replace("<<SUMMARY>>", summary)
        .replace("<<PROJECTS>>", json.dumps(projects, ensure_ascii=False))
        .replace("<<SKILLS>>", json.dumps(skills, ensure_ascii=False))
    )
    apply(sections, complete_json(prompt))
    tidy(document)
    document.save(str(working))
    to_pdf(working, destination)
    working.unlink(missing_ok=True)
    return destination
