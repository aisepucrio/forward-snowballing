import re
import hashlib
from difflib import SequenceMatcher


def slugify(text):
    text = re.sub(r"[^\w\s-]", "", str(text)).strip().lower()
    return re.sub(r"[-\s]+", "-", text)[:50]


def generate_paper_id(title):
    if not title:
        return "id-desconhecido"
    slug = slugify(title)
    return slug or hashlib.md5(str(title).encode()).hexdigest()[:10]


def normalize_doi(doi):

    if not doi:
        return None

    doi = str(doi).strip().lower()

    if doi in {"", "-", "none", "null"}:
        return None

    doi = doi.replace("https://doi.org/", "")
    doi = doi.replace("http://doi.org/", "")
    doi = doi.replace("doi.org/", "")
    doi = doi.replace("doi:", "")
    doi = doi.strip()

    if doi in {"", "-", "none", "null"}:
        return None

    return doi


def normalize_title(title):
    if not title:
        return ""

    title = str(title).strip().lower()
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title


def fuzzy_match(a, b):
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def token_overlap_score(a, b):
    a_tokens = set(normalize_title(a).split())
    b_tokens = set(normalize_title(b).split())

    if not a_tokens:
        return 0

    return len(a_tokens & b_tokens) / len(a_tokens)


def is_missing(value):
    return value in (None, "", "-", "null", "None")
