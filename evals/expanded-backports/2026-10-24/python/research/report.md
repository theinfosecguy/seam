# Python backport candidates

The catalogue identifies **21 distinct Python libraries** with published fixes on older release lines. These are research candidates, not 21 completed evaluations. All issue identities differ from the eight original Python dataset cases.

**Five maintainer source/backport pairs are pinned to immutable ordinary commits and parents.** Sixteen distributor publications identify fixed older package versions, but still need a pristine baseline, exact patch-series review, frozen environment and independent runtime qualification.

| Library | Issue | Fixed older release | Published backport evidence | Readiness |
| --- | --- | --- | --- | --- |
| Django | CVE-2026-77050 | `5.2.18` | [2026-10-06](https://www.djangoproject.com/weblog/2026/oct/06/security-releases/) | Commit pair pinned; not run |
| Werkzeug | CVE-2023-46136 | `2.3.8` | [2023-10-24](https://github.com/pallets/werkzeug/security/advisories/GHSA-hrfv-mqp8-q5rw) | Commit pair pinned; not run |
| marshmallow | CVE-2025-68480 | `3.26.2` | [2025-12-22](https://github.com/marshmallow-code/marshmallow/security/advisories/GHSA-428g-f7cq-pgp5) | Commit pair pinned; not run |
| pydantic | CVE-2021-29510 | `1.7.4` | [2021-05-11](https://github.com/pydantic/pydantic/security/advisories/GHSA-5jqp-qgf6-3pvh) | Commit pair pinned; not run |
| Scrapy | GHSA-cc65-xxvf-f7r9 | `1.8.4` | [2024-02-14](https://github.com/scrapy/scrapy/security/advisories/GHSA-cc65-xxvf-f7r9) | Commit pair pinned; not run |
| Paramiko | CVE-2023-48795 | `2.9.3-0ubuntu1.2` | [2024-01-25](https://ubuntu.com/security/notices/USN-6598-1) | Version confirmed; not run |
| aiohttp | CVE-2024-23334 | `3.9.1-1ubuntu0.1` | [2024-09-05](https://ubuntu.com/security/notices/USN-6991-1) | Version confirmed; not run |
| cryptography | CVE-2026-69248 | `46.0.5-1ubuntu2.2` | [2026-09-16](https://ubuntu.com/security/notices/USN-8776-1) | Version confirmed; not run |
| lxml | CVE-2026-41066 | `5.2.1-1ubuntu0.2` | [2026-10-07](https://ubuntu.com/security/notices/USN-8897-1) | Version confirmed; not run |
| Tornado | CVE-2026-35536 | `6.5.4-0.1ubuntu0.1` | [2026-04-28](https://ubuntu.com/security/notices/USN-8198-2) | Version confirmed; not run |
| Requests | CVE-2026-25645 | `2.31.0+dfsg-1ubuntu1.2` | [2026-09-28](https://ubuntu.com/security/notices/USN-8825-1) | Version confirmed; not run |
| urllib3 | CVE-2026-44431 | `1.26.5-1~exp1ubuntu0.7` | [2026-06-03](https://ubuntu.com/security/notices/USN-8379-1) | Version confirmed; not run |
| Jinja2 | CVE-2025-27516 | `3.0.3-1ubuntu0.4` | [2025-03-11](https://ubuntu.com/security/notices/USN-7343-1) | Version confirmed; not run |
| Flask | CVE-2026-27205 | `3.0.2-1ubuntu1.1` | [2026-03-18](https://ubuntu.com/security/notices/USN-8104-1) | Version confirmed; not run |
| sqlparse | CVE-2026-54284 | `0.4.4-1ubuntu0.2` | [2026-09-23](https://ubuntu.com/security/notices/USN-8808-1) | Version confirmed; not run |
| PyJWT | CVE-2026-48523 | `2.10.1-4ubuntu1.1` | [2026-09-25](https://ubuntu.com/security/notices/USN-8823-1) | Version confirmed; not run |
| Pillow | CVE-2026-59198 | `9.0.1-1ubuntu0.5` | [2026-09-01](https://ubuntu.com/security/notices/USN-8690-1) | Version confirmed; not run |
| setuptools | CVE-2025-47273 | `68.1.2-2ubuntu1.2` | [2025-05-28](https://ubuntu.com/security/notices/USN-7544-1) | Version confirmed; not run |
| PyYAML | CVE-2020-14343 | `5.3.1-1ubuntu0.1` | [2021-05-10](https://ubuntu.com/security/notices/USN-4940-1) | Version confirmed; not run |
| Twisted | CVE-2026-42304 | `24.3.0-1ubuntu0.2` | [2026-06-03](https://ubuntu.com/security/notices/USN-8380-1) | Version confirmed; not run |
| UltraJSON | CVE-2026-32875 | `5.11.0-3ubuntu0.1` | [2026-04-28](https://ubuntu.com/security/notices/USN-8219-1) | Version confirmed; not run |

Start with Werkzeug, Marshmallow and the new Django language-cache issue. The pinned historical Pydantic and Scrapy pairs add version drift, but need older interpreter and dependency review. Marshmallow has a follow-up hardening commit after the selected performance fix; benchmark scope must say which changes are being compared.

For recent broad coverage, prioritize Requests, urllib3, Flask, PyJWT and Tornado next. Pillow, lxml, cryptography and UltraJSON introduce real native builds; a Python-only wrapper check cannot establish coverage of their native implementations. Twisted uses Trial and a multi-patch fix, so it should remain a pending runner and patch-series case until that boundary is reviewed.

Dates identify the linked publication, not necessarily the initial vulnerability disclosure. Older 2021–2025 cases are labeled by their real publication dates. Distribution revision suffixes matter: an old-looking upstream version may contain the official backport.

Public metadata was checked without credentials. Related subscription-only rows in some notices are not treated as freely reproducible inputs. All 16 selected distributor source descriptors were retrieved anonymously. Their PGP signatures have not been validated, and their listed source archives still need to be downloaded and verified before evaluation.

No target builds or tests were executed for this research. No new oracle, vulnerability payload or attack procedure was developed. Candidate discovery, input qualification, ordinary compatibility execution and model-generated backport success must be reported as separate denominators.

Machine-readable details: [catalogue.json](catalogue.json). Public source descriptor checks: [source-package-access.json](source-package-access.json).

The official [BackportBench corpus](https://github.com/coxhin/BackportBench/tree/a7bb4ed2632305f1c7ef0bc81cf6b751e5d4c292), described in the [research paper](https://arxiv.org/abs/2512.01396), supplies a separate, author-labeled historical pool: 264 Python backport pairs across 27 projects. It is recorded by the benchmark research team and is not added to this independently checked 21-library count. Most executable Python cases in that benchmark are Django; the diverse library candidates here complement that concentration.
