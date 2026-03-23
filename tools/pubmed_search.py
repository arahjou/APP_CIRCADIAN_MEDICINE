"""
PubMed E-utilities helper for the circadian medicine pipeline.

Agent 3 (Literature Search) — pure API calls, no LLM.
Privacy: only search QUERIES touch the internet — no patient data or raw metrics.

Rate limits:
  - Without NCBI API key: 3 requests/sec
  - With key (set NCBI_API_KEY env var): 10 requests/sec

Usage:
    from tools.pubmed_search import search_pubmed
    text, pmids = search_pubmed(["circadian rhythm sleep irregularity", "interdaily stability actigraphy"])
"""

import os
import time
import urllib.request
import urllib.parse
import urllib.error
import json as _json
import xml.etree.ElementTree as ET


_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
_MAX_ABSTRACTS_PER_QUERY = 3
_MAX_TOTAL_CHARS = 8000   # ≈ 2 000 tokens; keeps Agent-5 context manageable
_RETRY_WAIT = 0.40        # seconds between requests (safe for anonymous use)


def _ncbi_get(url: str, retries: int = 2) -> str:
    """Fetch a URL with retries. Returns body as str."""
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.URLError as e:
            if attempt == retries:
                raise
            time.sleep(1.0)


def _esearch(query: str, api_key: str | None) -> list[str]:
    """Return up to _MAX_ABSTRACTS_PER_QUERY PubMed IDs for a query."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": str(_MAX_ABSTRACTS_PER_QUERY),
        "retmode": "json",
    }
    if api_key:
        params["api_key"] = api_key
    url = _BASE_URL + "esearch.fcgi?" + urllib.parse.urlencode(params)
    try:
        body = _ncbi_get(url)
        data = _json.loads(body)
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception:
        return []


def _efetch_abstracts(pmids: list[str], api_key: str | None) -> tuple[str, list[str]]:
    """Fetch and concatenate abstracts for a list of PubMed IDs. Returns (text, pmid_list)."""
    if not pmids:
        return "", []
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "abstract",
        "retmode": "xml",
    }
    if api_key:
        params["api_key"] = api_key
    url = _BASE_URL + "efetch.fcgi?" + urllib.parse.urlencode(params)
    try:
        xml_body = _ncbi_get(url)
        return _parse_abstracts_xml(xml_body)
    except Exception:
        return "", []


def _parse_abstracts_xml(xml_text: str) -> tuple[str, list[str]]:
    """Extract title + abstract text from PubMed XML. Returns (plain text block, pmid list)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return "", []

    blocks: list[str] = []
    pmids: list[str] = []
    for article in root.iter("PubmedArticle"):
        # PMID
        pmid_el = article.find(".//PMID")
        pmid = pmid_el.text.strip() if pmid_el is not None and pmid_el.text else "Unknown"
        # Title
        title_el = article.find(".//ArticleTitle")
        title = title_el.text if title_el is not None and title_el.text else "No title"
        # Abstract (may be multiple AbstractText elements)
        abstract_parts = []
        for el in article.findall(".//AbstractText"):
            part = (el.get("Label", "") + ": " if el.get("Label") else "") + (el.text or "")
            abstract_parts.append(part.strip())
        abstract = " ".join(abstract_parts).strip() or "No abstract available."
        blocks.append(f"PMID: {pmid}\nTITLE: {title}\nABSTRACT: {abstract}")
        pmids.append(pmid)

    return "\n\n---\n\n".join(blocks), pmids


def search_pubmed(
    queries: list[str],
    ncbi_api_key: str | None = None,
) -> tuple[str, list[str]]:
    """
    Search PubMed for each query, fetch abstracts, and return a (text, pmids) tuple.
    Text is a single concatenated block capped at _MAX_TOTAL_CHARS characters.
    Each abstract block includes its PMID.

    Args:
        queries: List of search strings (should be MeSH/keyword style, 3-5 terms each).
        ncbi_api_key: Optional NCBI API key from env var NCBI_API_KEY. Raises rate limits.

    Returns:
        (text, pmid_list) — text has abstracts separated by '---'; pmid_list is deduplicated.
        Returns ("", []) if all queries fail.
    """
    if ncbi_api_key is None:
        ncbi_api_key = os.environ.get("NCBI_API_KEY") or None

    all_blocks: list[str] = []
    seen_ids: set[str] = set()
    all_pmids: list[str] = []
    total_chars = 0

    for query in queries:
        time.sleep(_RETRY_WAIT)
        pmids = _esearch(query, ncbi_api_key)
        # Deduplicate across queries
        new_ids = [p for p in pmids if p not in seen_ids]
        if not new_ids:
            continue
        seen_ids.update(new_ids)

        time.sleep(_RETRY_WAIT)
        block, fetched_pmids = _efetch_abstracts(new_ids, ncbi_api_key)
        if not block:
            continue

        if total_chars + len(block) > _MAX_TOTAL_CHARS:
            # Truncate to fit
            remaining = _MAX_TOTAL_CHARS - total_chars
            if remaining > 200:
                all_blocks.append(block[:remaining] + "\n[...truncated]")
                total_chars += remaining
                all_pmids.extend(fetched_pmids)
            break

        all_blocks.append(block)
        all_pmids.extend(fetched_pmids)
        total_chars += len(block)

        if total_chars >= _MAX_TOTAL_CHARS:
            break

    if not all_blocks:
        return "", []

    return "\n\n===\n\n".join(all_blocks), all_pmids
