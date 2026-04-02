from __future__ import annotations

import tools.pubmed_search as ps


def test_build_and_rank_pubmed_results(monkeypatch):
    def fake_esearch(query, api_key, retmax):
        return ["1", "2", "3"]

    def fake_efetch(pmids, api_key):
        return [
            {"pmid": "1", "title": "Circadian rhythm and sleep", "abstract": "Actigraphy sleep regularity", "journal": "J1", "year": "2022"},
            {"pmid": "2", "title": "Unrelated plant study", "abstract": "Arabidopsis genes", "journal": "J2", "year": "2020"},
            {"pmid": "3", "title": "Light exposure circadian", "abstract": "Melanopic EDI and phase", "journal": "J3", "year": "2021"},
        ]

    monkeypatch.setattr(ps, "_esearch", fake_esearch)
    monkeypatch.setattr(ps, "_efetch_details", fake_efetch)

    out = ps.search_pubmed([
        {"topic": "circadian rhythm", "population": "humans", "context": "sleep"}
    ])

    assert out
    assert all("pmid" in x and "score" in x and "compiled_query" in x for x in out)
    assert out[0]["pmid"] in {"1", "3"}
