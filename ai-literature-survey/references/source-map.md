# Source Map

This skill was built from cloned upstream repositories under:

`/apdcephfs/AILab_DHA/apdcephfs_cq11/share_1467498/home/zeyuling/cc_skills/_upstreams/literature`

When installed globally, use that absolute path unless `AI_LITERATURE_UPSTREAMS` points elsewhere. If working from the source checkout, `../_upstreams/literature` relative to the skill folder is also valid.

## Source Families

| Family | Primary use | Local upstream |
|---|---|---|
| arXiv search | broad preprint recall, category/date queries | `ai-skill-arxiv`, `arxiv-skill` |
| arXiv full text | read arXiv markdown, HTML, PDF, or TeX fallback | `ai-skill-arxiv`, `arxiv-skill` |
| arXiv monitoring | watch recurring queries for new work | `ai-skill-arxiv/skills/arxiv-monitor` |
| OpenAlex | cross-venue search, citations, references, DOI, venue metadata | `ai-skill-scholar` |
| two-pass review state | persistent candidate, shortlist, fetch-plan workflow | `ai-skill-scholar/skills/literature-review` |
| daily paper feed | personalized recent arXiv/HuggingFace recommendations | `dailypaper-skills`, `airs-daily-paper` |
| daily AI hotspots | multi-source daily signals beyond arXiv | `ChatGPT-ArXiv-Paper-Assistant` |
| conference comments | arXiv records whose comments mention CVPR, ICCV, ECCV, NeurIPS, ICML, etc. | `ArXiv-Conference-Paper-Crawler` |
| OpenReview venues | accepted papers and metadata from ICLR, NeurIPS, EMNLP, ICML configs | `openreview-crawler` |
| NeurIPS proceedings | proceedings metadata, abstracts, PDFs by year | `NeurIPS-Papers-Crawler` |
| discovery app | FastAPI/Vue arXiv discovery and vector search reference | `ArxivSurveyAgent` |
| generic review workflow | query analysis, dedup, verification, citation formatting, synthesis | `AI-Powered-Literature-Review-Skills` |

## Preferred Search Order

1. Start with OpenAlex for broad cross-venue metadata and citation counts.
2. Run arXiv searches for latest work and exact terminology variants.
3. Search OpenReview for venues that use it.
4. Check official proceedings and conference-specific crawlers for top venues.
5. Use citation snowballing from the highest-relevance anchors.
6. Use daily paper or hotspot feeds to catch current papers and community signals.
7. Search the web for project pages, code repositories, benchmarks, and leaderboards when the task is implementation-heavy.

## Local Upstream Commands

These commands are reference patterns. Check each upstream README before running heavy jobs.

### arXiv Skill

`ai-skill-arxiv` exposes separate skills for search, analysis, and monitoring. Useful patterns:

```bash
python3 /path/to/ai-skill-arxiv/skills/arxiv-search/scripts/arxiv_search.py "query" --category cs.CV --max 50 --sort-by submittedDate
python3 /path/to/ai-skill-arxiv/skills/arxiv-analyze/scripts/arxiv_fetch.py 2401.00000 --metadata-only
python3 /path/to/ai-skill-arxiv/skills/arxiv-monitor/scripts/arxiv_monitor.py add topic-watch --query "query" --category cs.LG --max 30
```

If these scripts are absent or not installed as active skills, use the cloned repo as implementation reference and fall back to web or arXiv API queries.

### OpenAlex Scholar Skill

`ai-skill-scholar` is the default cross-venue source:

```bash
python3 /path/to/ai-skill-scholar/skills/scholar-search/scripts/scholar_search.py "query" --year 2020-2026 --limit 100
python3 /path/to/ai-skill-scholar/skills/scholar-citations/scripts/scholar_citations.py both 2401.00000 --limit 100
python3 /path/to/ai-skill-scholar/skills/literature-review/scripts/literature_review.py init "research question"
```

Set `OPENALEX_EMAIL` when doing heavy OpenAlex work if the user has an email to use for the polite pool.

### Conference and Proceedings Crawlers

Use these for venue coverage audits:

```bash
python3 /path/to/openreview-crawler/main.py --config configs/iclr_2024.yaml --selection poster
python3 /path/to/NeurIPS-Papers-Crawler/crawler.py --start_year 2020 --end_year 2025 --output_dir ./data --type all
python3 /path/to/ArXiv-Conference-Paper-Crawler/Demo/advanced_search_Spider.py
```

These crawlers may need dependency installation or config edits. If running them is too heavy, inspect their sample outputs and use official venue pages or OpenReview directly.

### Daily Paper Pipelines

Use these for monitoring and recent-work inspiration, not as the only source for a serious review:

```bash
python3 /path/to/gpt_paper_assistant/main.py
python3 /path/to/ChatGPT-ArXiv-Paper-Assistant/main.py --output-root out --mode auto
```

The daily feeds are tuned by prompts, keywords, authors, and categories. Record the config used in the source ledger.

## Source Reliability Notes

- arXiv has high recall for recent AI preprints but weak venue certainty unless comments or later metadata are present.
- OpenAlex has good broad metadata but can lag on very recent preprints and may have missing abstracts or sparse references.
- OpenReview is authoritative for venues hosted there, but configs and invitation names change by year.
- Proceedings pages are authoritative for accepted papers but usually lack citation graph data.
- Daily paper feeds are useful for recency and community signal, but they are personalized filters and should not define the universe alone.
