# ecfr-analyzer

## Reflection on the eCFR Analyzer project

This is a POC of a website we can use to analyze CFRs. We focus on the up to date CFR here, rather than the historical
CFR.

Time taken:
Wall time: 1 day
Actual time, minus time spent downloading/analyzing CFRs, setup etc: 5 hours

### Technologies used:

* Python 3.14
* Postgresql 18 (with Alembic)
* FastAPI
* htmx + jinja2 templates for server-side rendering
* Claude Code - Sonnet 4.5
* Claude haiku-4.5 for CFR summaries
* PyCharm IDE

CLAUDE.md in the repository has all of the technical details you could want. Thanks, Claude!

For this project, I chose to develop using Claude Code and I chose to focus on product work
versus infrastructure work. As a result, there is no containerization, no CI/CD pipeline, and no centralized logging.

I am nominally an infrastructure engineer; I write a lot of code, but most of it is ops/infra related. I have a
background in web development, but haven’t actively done full stack development since late 2018 using Flask. I wanted to
gain some experience with an async-first framework as well as modern dependency management with uv. I would have also
chosen to use React for the front end, but I figured that was too much experimentation and overkill for what I wanted to
do.

Here’s what I would do differently with additional time:
1. Consider using Elasticsearch/OpenSearch instead of PG18 tsvector for full text search on summaries. This would simplify
testing dramatically, as it currently requires a PG test database or it will skip tests that use the cfr_reference.
1. Consider generating summaries as the cfr is requested by the user instead of batch processing all current cfr
references.
1. Containerize the project so it can be easily packaged for deployment into a Kubernetes project. Use Tilt to enable the
edit->build->test cycle in a local Kubernetes.
1. Keyword search
1. Add suggestions on potential CFR improvements on the CFR summary page from Claude

Repository initiated with [fpgmaas/cookiecutter-uv](https://github.com/fpgmaas/cookiecutter-uv).
