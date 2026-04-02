"""
Structured PubMed retrieval with query compilation, lexical reranking, and diversity-aware selection.
"""

from __future__ import annotations

import json as _json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Dict, List


_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
_RETRY_WAIT = 0.34


@dataclass
class RetrievalConfig:
    retmax_per_query: int = 15
    keep_per_query: int = 5
    max_total_items: int = 18
    years_back: int = 10
    humans_only: bool = True
    adults_only: bool = False


def _ncbi_get(url: str, retries: int = 2) -> str:
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.URLError:
            if attempt == retries:
                raise
            time.sleep(1.0)
    return ""


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _title_key(title: str) -> str:
    return re.sub(r"\W+", " ", (title or "").lower()).strip()


def _build_pubmed_query(structured_query: Dict[str, str], cfg: RetrievalConfig) -> str:
    topic = (structured_query.get("topic") or "circadian rhythm").strip()
    population = (structured_query.get("population") or "humans").strip()
    context = (structured_query.get("context") or "sleep").strip()

    topic_block = f"({topic}[Title/Abstract] OR {topic}[MeSH Terms])"
    context_block = f"({context}[Title/Abstract] OR chronobiology[Title/Abstract])"
    pop_block = f"({population}[Title/Abstract])"

    filters = [f'("{max(2000, 2026 - cfg.years_back)}"[Date - Publication] : "3000"[Date - Publication])']
    if cfg.humans_only:
        filters.append("humans[MeSH Terms]")
    if cfg.adults_only:
        filters.append("adult[MeSH Terms]")

    return f"{topic_block} AND {context_block} AND {pop_block} AND " + " AND ".join(filters)


def _esearch(query: str, api_key: str | None, retmax: int) -> list[str]:
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": str(retmax),
        "retmode": "json",
        "sort": "relevance",
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


def _efetch_details(pmids: list[str], api_key: str | None) -> list[dict]:
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    if api_key:
        params["api_key"] = api_key
    url = _BASE_URL + "efetch.fcgi?" + urllib.parse.urlencode(params)

    try:
        body = _ncbi_get(url)
        return _parse_abstracts_xml(body)
    except Exception:
        return []


def _extract_pub_year(article_el: ET.Element) -> str:
    year_el = article_el.find(".//PubDate/Year")
    if year_el is not None and year_el.text:
        return year_el.text.strip()
    medline_date = article_el.find(".//PubDate/MedlineDate")
    if medline_date is not None and medline_date.text:
        match = re.search(r"(19|20)\d{2}", medline_date.text)
        if match:
            return match.group(0)
    return "Unknown"


def _parse_abstracts_xml(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    items: list[dict] = []
    for article in root.iter("PubmedArticle"):
        pmid_el = article.find(".//PMID")
        pmid = pmid_el.text.strip() if pmid_el is not None and pmid_el.text else "Unknown"

        title_el = article.find(".//ArticleTitle")
        title = title_el.text.strip() if title_el is not None and title_el.text else "No title"

        journal_el = article.find(".//Journal/Title")
        journal = journal_el.text.strip() if journal_el is not None and journal_el.text else "Unknown"

        abstract_parts = []
        for el in article.findall(".//AbstractText"):
            prefix = f"{el.get('Label')}: " if el.get("Label") else ""
            abstract_parts.append(prefix + (el.text or ""))
        abstract = " ".join(x.strip() for x in abstract_parts if x and x.strip())
        if not abstract:
            abstract = "No abstract available."

        items.append(
            {
                "pmid": pmid,
                "title": title,
                "abstract": abstract,
                "journal": journal,
                "year": _extract_pub_year(article),
            }
        )
    return items


def _lexical_score(query_text: str, item: dict) -> float:
    q_tokens = _tokenize(query_text)
    doc_tokens = _tokenize((item.get("title") or "") + " " + (item.get("abstract") or ""))
    if not q_tokens or not doc_tokens:
        return 0.0
    overlap = len(q_tokens.intersection(doc_tokens))
    return overlap / max(1, len(q_tokens))


def _diversify(items: list[dict], max_items: int) -> list[dict]:
    seen_title_keys: set[str] = set()
    out: list[dict] = []
    for item in items:
        key = _title_key(item.get("title") or "")
        if key in seen_title_keys:
            continue
        seen_title_keys.add(key)
        out.append(item)
        if len(out) >= max_items:
            break
    return out


def evidence_to_text(evidence_items: List[Dict[str, Any]], max_chars: int = 12000) -> str:
    blocks: list[str] = []
    total = 0
    for item in evidence_items:
        block = (
            f"PMID: {item.get('pmid')}\n"
            f"TITLE: {item.get('title')}\n"
            f"JOURNAL: {item.get('journal')} ({item.get('year')})\n"
            f"ABSTRACT: {item.get('abstract')}"
        )
        if total + len(block) > max_chars:
            break
        blocks.append(block)
        total += len(block)
    return "\n\n---\n\n".join(blocks) if blocks else "No PubMed abstracts found for the given search terms."


def search_pubmed(
    queries: list[dict] | list[str],
    *,
    ncbi_api_key: str | None = None,
    config: RetrievalConfig | None = None,
) -> list[dict]:
    """
    Returns structured records:
    {pmid, title, abstract, journal, year, score, query_source, compiled_query}
    """
    cfg = config or RetrievalConfig()
    if ncbi_api_key is None:
        ncbi_api_key = os.environ.get("NCBI_API_KEY") or None

    structured_queries: list[dict] = []
    for q in queries:
        if isinstance(q, dict):
            structured_queries.append(q)
        else:
            structured_queries.append({"topic": str(q), "population": "humans", "context": "sleep"})

    scored_items: list[dict] = []
    seen_pmids: set[str] = set()

    for qobj in structured_queries:
        compiled = _build_pubmed_query(qobj, cfg)
        time.sleep(_RETRY_WAIT)
        pmids = _esearch(compiled, ncbi_api_key, cfg.retmax_per_query)
        if not pmids:
            continue

        time.sleep(_RETRY_WAIT)
        fetched = _efetch_details(pmids, ncbi_api_key)
        query_label = " | ".join(filter(None, [qobj.get("topic"), qobj.get("context")]))

        per_query_scored: list[dict] = []
        for item in fetched:
            pmid = item.get("pmid")
            if not pmid or pmid in seen_pmids:
                continue
            score = _lexical_score(compiled, item)
            per_query_scored.append(
                {
                    **item,
                    "score": round(float(score), 4),
                    "query_source": query_label,
                    "compiled_query": compiled,
                }
            )

        per_query_scored.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        selected = per_query_scored[: cfg.keep_per_query]
        for sel in selected:
            seen_pmids.add(sel["pmid"])
            scored_items.append(sel)

    scored_items.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return _diversify(scored_items, cfg.max_total_items)
