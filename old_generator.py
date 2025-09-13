# backend/resume_improv_lib/generator.py

from typing import Dict, List, Any
from backend.resume_improv_lib.schemas import ResumeSuggestion
from backend.resume_improv_lib.llm_handler import llm_call


# -------------------- small utilities --------------------

def _append_if_changed(
    out: List[ResumeSuggestion],
    section: str,
    issue: str,
    original: str,
    improved: str,
) -> None:
    """Append suggestion only if LLM produced a non-empty, changed result."""
    if not improved:
        return
    orig_norm = (original or "").strip().lower()
    imp_norm = improved.strip().lower()
    if imp_norm and imp_norm != orig_norm:
        out.append(
            ResumeSuggestion(
                section=section,
                issue=issue,
                original_text=original,
                improved_text=improved,
            )
        )


def _combine_entry_text(entry: Any) -> str:
    """
    Turn a single section item (dict / list / str) into a single-line string
    to feed the LLM. Non-destructive (doesn't invent anything).
    """
    if entry is None:
        return ""

    # if it's already a simple string
    if isinstance(entry, str):
        return entry

    # dict-like entries are common
    if isinstance(entry, dict):
        # prefer explicit fields if present
        for key in ("description", "details", "summary", "line", "text"):
            val = entry.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

        # join bullets if present
        bullets = entry.get("bullets")
        if isinstance(bullets, list) and bullets:
            return " • ".join([b for b in bullets if isinstance(b, str)])

        # as a last resort, join all primitive string-ish values
        parts: List[str] = []
        for k, v in entry.items():
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, (list, tuple)):
                parts.extend([x for x in v if isinstance(x, str)])
        return " • ".join([p for p in parts if p.strip()])

    # list of strings/bullets
    if isinstance(entry, list):
        return " • ".join([x for x in entry if isinstance(x, str)])

    return ""


def _get_items(resume: Dict[str, Any], keys: List[str]) -> List[Any]:
    """Return list of items for the first matching key in parsed resume."""
    for k in keys:
        items = resume.get(k)
        if isinstance(items, list):
            return items
    return []


def _get_section_issues(analysis: Dict[str, Any], keys: List[str]) -> Any:
    """
    Return the analysis payload for the first matching key.
    Can be a list (per-item issues) or a dict (section-level issues).
    """
    for k in keys:
        if k in analysis:
            return analysis[k]
    return None


# -------------------- handlers for different section types --------------------

_EXPERIENCE_KEYS = ["experience", "work_experience", "work", "professional_experience"]
_INTERNSHIP_KEYS = ["internships", "internship"]
_EDUCATION_KEYS = ["education", "educations"]
_AWARDS_KEYS = ["awards_achievements", "awards", "achievements", "honors"]
_POR_KEYS = ["positions_of_responsibility", "leadership", "por"]
_CO_CURR_KEYS = ["co_curricular", "co_curricular_activities", "cocurricular"]
_EXTRA_CURR_KEYS = ["extra_curricular", "extracurricular", "extracurricular_activities"]
_SKILLS_KEYS = ["skills"]
_SUMMARY_KEYS = ["summary", "objective", "profile"]


def _process_experience_like(
    suggestions: List[ResumeSuggestion],
    llm_client,
    section_label: str,
    items: List[Any],
    issues: Any,
) -> None:
    """
    Handle sections that are lists of role entries: experience / internships.
    `issues` is expected to be a list with same indexing as items, where each entry is a dict of flags.
    """
    if not isinstance(issues, list):
        return

    for idx, issue_dict in enumerate(issues):
        if not isinstance(issue_dict, dict):
            continue
        original = _combine_entry_text(items[idx] if idx < len(items) else "")
        if not original:
            continue

        # map common flags -> concise LLM instructions
        if issue_dict.get("no_metrics") or issue_dict.get("missing_metrics"):
            improved = llm_call(llm_client, original, "Add measurable impact and metrics without inventing facts")
            _append_if_changed(suggestions, section_label, "No measurable impact", original, improved)

        if issue_dict.get("weak_action_verbs"):
            improved = llm_call(llm_client, original, "Strengthen action verbs; start with a strong verb")
            _append_if_changed(suggestions, section_label, "Weak action verbs", original, improved)

        if issue_dict.get("responsibility_over_achievement"):
            improved = llm_call(llm_client, original, "Rewrite as an achievement with outcome and scale")
            _append_if_changed(suggestions, section_label, "Not achievement-oriented", original, improved)

        if issue_dict.get("too_wordy") or issue_dict.get("too_long"):
            improved = llm_call(llm_client, original, "Make this a concise one-line resume bullet")
            _append_if_changed(suggestions, section_label, "Too wordy", original, improved)

        if issue_dict.get("missing_keywords"):
            improved = llm_call(llm_client, original, "Include job-relevant keywords naturally if present in input")
            _append_if_changed(suggestions, section_label, "Missing keywords", original, improved)


def _process_simple_list_section(
    suggestions: List[ResumeSuggestion],
    llm_client,
    section_label: str,
    items: List[Any],
    issues: Any,
    generic_instruction: str,
) -> None:
    """
    Handle sections that are usually bullet-like lists (awards, POR, co-/extra-curricular).
    Issues can be a list (per-item flags) or a dict (section-level).
    """
    # Per-item issues
    if isinstance(issues, list):
        for idx, issue_dict in enumerate(issues):
            if not isinstance(issue_dict, dict):
                continue
            original = _combine_entry_text(items[idx] if idx < len(items) else "")
            if not original:
                continue

            # common flags
            applied = False
            if issue_dict.get("too_generic") or issue_dict.get("missing_impact"):
                improved = llm_call(llm_client, original, generic_instruction)
                _append_if_changed(suggestions, section_label, "Too generic", original, improved)
                applied = True

            if issue_dict.get("too_wordy") or issue_dict.get("too_long"):
                improved = llm_call(llm_client, original, "Make this concise, single resume bullet")
                _append_if_changed(suggestions, section_label, "Too wordy", original, improved)
                applied = True

            if not applied and issue_dict:  # unknown flags -> generic polish
                improved = llm_call(llm_client, original, generic_instruction)
                _append_if_changed(suggestions, section_label, "Improve phrasing", original, improved)

    # Section-level issues (polish all bullets as one block)
    elif isinstance(issues, dict) and (issues.get("too_generic") or issues.get("too_long") or issues.get("missing_impact")):
        block = " • ".join([_combine_entry_text(x) for x in items])
        if block:
            improved = llm_call(llm_client, block, generic_instruction)
            _append_if_changed(suggestions, section_label, "Section too generic", block, improved)


def _process_education(
    suggestions: List[ResumeSuggestion],
    llm_client,
    items: List[Any],
    issues: Any,
) -> None:
    """
    Education entries are typically list[dict].
    We support common flags; fallback to standardized one-line formatting.
    """
    if isinstance(issues, list):
        for idx, issue_dict in enumerate(issues):
            if not isinstance(issue_dict, dict):
                continue
            original = _combine_entry_text(items[idx] if idx < len(items) else "")
            if not original:
                continue

            # known flags
            if issue_dict.get("too_generic"):
                instr = ("Rewrite as a clean one-line education entry: "
                         "Degree, Major — Institute, Location — Dates. "
                         "Include GPA/CGPA and honors only if present in input. Do not invent.")
                improved = llm_call(llm_client, original, instr)
                _append_if_changed(suggestions, "education", "Too generic", original, improved)

            if issue_dict.get("missing_dates"):
                instr = "Standardize dates to MMM YYYY or YYYY range if present; keep concise; do not fabricate."
                improved = llm_call(llm_client, original, instr)
                _append_if_changed(suggestions, "education", "Missing dates", original, improved)

            if issue_dict.get("missing_gpa"):
                instr = "If GPA/CGPA is present in the input, include it in a standard format; otherwise omit."
                improved = llm_call(llm_client, original, instr)
                _append_if_changed(suggestions, "education", "GPA/CGPA formatting", original, improved)

            if issue_dict.get("too_wordy") or issue_dict.get("too_long"):
                instr = "Make this a single concise line focusing on degree, institute, location, dates (and GPA if present)."
                improved = llm_call(llm_client, original, instr)
                _append_if_changed(suggestions, "education", "Too wordy", original, improved)

    elif isinstance(issues, dict) and (issues.get("too_generic") or issues.get("too_long")):
        # Section-level cleanup
        block = " • ".join([_combine_entry_text(x) for x in items])
        if block:
            instr = ("Polish education entries to one-line standardized format: "
                     "Degree, Major — Institute, Location — Dates — GPA/CGPA (if present). "
                     "Do not invent any data.")
            improved = llm_call(llm_client, block, instr)
            _append_if_changed(suggestions, "education", "Section needs standardization", block, improved)

def _get_skills_text(resume_text: Dict[str, Any]) -> str:
    """Flatten skills (list or dict) into a comma-separated string."""
    skills = resume_text.get("skills")
    flat: List[str] = []
    if isinstance(skills, list):
        flat = [s for s in skills if isinstance(s, str)]
    elif isinstance(skills, dict):
        for k in ("technical", "tools", "languages", "frameworks", "soft"):
            vals = skills.get(k)
            if isinstance(vals, list):
                flat.extend([s for s in vals if isinstance(s, str)])
    return ", ".join(flat)

def _process_skills( 
    suggestions: List[ResumeSuggestion],
    llm_client,
    resume_text: Dict[str, Any],
    issues: Any,
) -> None:
    original = _get_skills_text(resume_text)
    if not original:
        return

    if isinstance(issues, dict):
        if issues.get("too_generic") or issues.get("missing_proficiency"):
            issue_text = "Skills too generic" if issues.get("too_generic") else "Missing proficiency levels"
            instr = ("Cluster by category (e.g., Languages, Frameworks, Tools) and include proficiency levels "
                     "only if present in input. Keep it concise.")
            improved = llm_call(llm_client, original, instr)
            _append_if_changed(suggestions, "skills", issue_text, original, improved)

def _process_summary(
    suggestions: List[ResumeSuggestion],
    llm_client,
    resume_text: Dict[str, Any],
    issues: Any,
) -> None:
    original = resume_text.get("summary") if isinstance(resume_text.get("summary"), str) else ""
    if not original:
        return

    if isinstance(issues, dict):
        if issues.get("too_generic"):
            improved = llm_call(llm_client, original, "Make summary specific and tailored to the target role")
            _append_if_changed(suggestions, "summary", "Summary too generic", original, improved)

        if issues.get("too_long"):
            improved = llm_call(llm_client, original, "Make summary concise (2–3 lines)")
            _append_if_changed(suggestions, "summary", "Summary too long", original, improved)

        if issues.get("missing_keywords"):
            improved = llm_call(llm_client, original, "Include job-relevant keywords naturally if present in input")
            _append_if_changed(suggestions, "summary", "Missing keywords", original, improved)


# -------------------- public entrypoint --------------------

def generate_resume_improvements(
    llm_client,
    analysis: Dict[str, Any],
    resume_text: Dict[str, Any],
) -> List[ResumeSuggestion]:
    """
    Generate resume improvement suggestions from precomputed analysis and parsed resume.
    Supports: education, internships, work experience, awards/achievements,
              positions of responsibility, co-/extra-curricular, skills, summary.
    """
    suggestions: List[ResumeSuggestion] = []

    if not analysis or not resume_text:
        return suggestions  # Always return a list

    # Experience-like: work experience
    exp_items = _get_items(resume_text, _EXPERIENCE_KEYS)
    exp_issues = _get_section_issues(analysis, _EXPERIENCE_KEYS)
    if exp_items and exp_issues is not None:
        _process_experience_like(suggestions, llm_client, "experience", exp_items, exp_issues)

    # Experience-like: internships
    intern_items = _get_items(resume_text, _INTERNSHIP_KEYS)
    intern_issues = _get_section_issues(analysis, _INTERNSHIP_KEYS)
    if intern_items and intern_issues is not None:
        _process_experience_like(suggestions, llm_client, "internships", intern_items, intern_issues)

    # Education
    edu_items = _get_items(resume_text, _EDUCATION_KEYS)
    edu_issues = _get_section_issues(analysis, _EDUCATION_KEYS)
    if edu_items and edu_issues is not None:
        _process_education(suggestions, llm_client, edu_items, edu_issues)

    # Awards & Achievements
    awards_items = _get_items(resume_text, _AWARDS_KEYS)
    awards_issues = _get_section_issues(analysis, _AWARDS_KEYS)
    if awards_items and awards_issues is not None:
        _process_simple_list_section(
            suggestions,
            llm_client,
            "awards_achievements",
            awards_items,
            awards_issues,
            generic_instruction="Rewrite as crisp, impact-focused bullets; keep titles and recognition clear",
        )

    # Positions of Responsibility
    por_items = _get_items(resume_text, _POR_KEYS)
    por_issues = _get_section_issues(analysis, _POR_KEYS)
    if por_items and por_issues is not None:
        _process_simple_list_section(
            suggestions,
            llm_client,
            "positions_of_responsibility",
            por_items,
            por_issues,
            generic_instruction="Emphasize leadership, scope, and outcomes; keep bullets concise and achievement-focused",
        )

    # Co-curricular
    co_curr_items = _get_items(resume_text, _CO_CURR_KEYS)
    co_curr_issues = _get_section_issues(analysis, _CO_CURR_KEYS)
    if co_curr_items and co_curr_issues is not None:
        _process_simple_list_section(
            suggestions,
            llm_client,
            "co_curricular",
            co_curr_items,
            co_curr_issues,
            generic_instruction="Refine to concise bullets showing relevance and impact; avoid fluff",
        )

    # Extra-curricular
    extra_curr_items = _get_items(resume_text, _EXTRA_CURR_KEYS)
    extra_curr_issues = _get_section_issues(analysis, _EXTRA_CURR_KEYS)
    if extra_curr_items and extra_curr_issues is not None:
        _process_simple_list_section(
            suggestions,
            llm_client,
            "extra_curricular",
            extra_curr_items,
            extra_curr_issues,
            generic_instruction="Highlight leadership, scale, achievements; keep it to tight resume bullets",
        )

    # Skills
    skills_issues = _get_section_issues(analysis, _SKILLS_KEYS)
    if skills_issues is not None:
        _process_skills(suggestions, llm_client, resume_text, skills_issues)

    # Summary
    summary_issues = _get_section_issues(analysis, _SUMMARY_KEYS)
    if summary_issues is not None:
        _process_summary(suggestions, llm_client, resume_text, summary_issues)

    return suggestions
