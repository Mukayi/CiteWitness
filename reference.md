# 数据源与查证手段（CiteWitness）

所有请求走 https；`scripts/bibtools.py` 对同一主机自动限速（arXiv 3 s、其余 1 s）。

## 元数据 API

| 来源 | 形式 | 给出 | 备注 |
|---|---|---|---|
| arXiv API | `https://export.arxiv.org/api/query?id_list=ID1,ID2&max_results=N`；标题搜索 `search_query=ti:"..."` | 标题、全作者、上传日期、`arxiv:comment`（常含 "Accepted by X"）、`arxiv:journal_ref`、`arxiv:doi` | 一次最多几十个 id；`http://` 会被 CDN 拒绝，必须 https。comment 是作者自述，不算论文集证据 |
| Crossref | `https://api.crossref.org/works/<DOI>`；搜索 `works?query.bibliographic=<title>&rows=5`；BibTeX：`works/<DOI>/transform/application/x-bibtex` | 标题、作者、`container-title`（会议 / 期刊全名）、`event.name`、年份、卷期页 | CVF（CVPR/ICCV）、IEEE、ACM、Springer、PMLR 大多有 DOI；NeurIPS 早年论文没有 |
| DBLP | `https://dblp.org/search/publ/api?q=<title>&format=json&h=5`；BibTeX：`https://dblp.org/rec/<key>.bib?param=1` | venue 缩写（ICML、NeurIPS、CoRR…）、年份、作者 | 同一论文常有 CoRR 与会议两条；部分网络不可达 |
| Semantic Scholar（可选） | `https://api.semanticscholar.org/graph/v1/paper/search?query=<title>&fields=title,authors,year,venue,externalIds` | venue、arXiv/DOI 映射 | 未登录 100 次 / 5 min；脚本未接入，需要时手动 curl |
| OpenReview | `https://openreview.net/forum?id=<id>`（页面含 venue 字段，如 "ICLR 2025 Poster"、"ES-FoMo III"） | 接收类型（Poster/Oral/Spotlight/Workshop） | 用 `webgrep.py --url` 抓取 |

## 论文集索引页（确认 booktitle 的证据）

| 会议 | 索引页 | 用法 |
|---|---|---|
| ICML | `https://proceedings.mlr.press/v<卷>/`（ICML 2025 = v267，2024 = v235，2023 = v202） | `verify_bib.py --index <url>` 或 `webgrep.py --url <url> "<标题片段>"`；页面约 3–4 MB |
| NeurIPS | `https://papers.nips.cc/paper_files/paper/<年>`；`https://proceedings.neurips.cc/paper_files/paper/<年>` | 同上 |
| ICLR | `https://proceedings.iclr.cc/paper_files/paper/<年>`；OpenReview venue 字段 | 同上 |
| CVPR / ICCV / ECCV | `https://openaccess.thecvf.com/<CVPR2026>?day=all` | 同上；Crossref 也有 DOI |
| MLSys / EMNLP / ACL | `https://proceedings.mlsys.org/paper_files/paper/<年>`；`https://aclanthology.org/` | 同上 |
| 会议 virtual 站（icml.cc / neurips.cc / iclr.cc `/virtual/<年>/poster/<id>`） | 列出主会**和工作坊**海报 | 只能当线索，页面写 "Poster in Workshop: ..." 的不是主会 |

## 全文（归因核对）

- `https://arxiv.org/html/<id>`：多数 2024 年后的论文有 HTML 版；`webgrep.py --arxiv <id> "<pattern>"` 直接抓取并 grep。
- 没有 HTML 版时 `webgrep.py` 退回摘要页；此时需要用 Shell 下载 PDF 并用 `pdftotext`（若已安装）转文本再 grep。
- 项目主页（`*.github.io`）常写 "Accepted by NeurIPS 2025 as a Spotlight"，可作辅助证据【推断】，正式证据仍以论文集为准。

## 比对规则（verify_bib.py 内置）

- 标题：去 TeX 命令与花括号、ASCII 折叠、小写、仅保留字母数字，`difflib` ratio ≥ .90 视为同一篇；索引页匹配额外去掉空格以容忍连字符差异。
- 作者：按姓（最后一个 token，ASCII 折叠）比对序列；bib 以 `others` 截断时只比前缀；单一团体作者对 > 10 人名单只给 WARN。
- 年份：差 1 记 note（arXiv 上传年 vs 会议年），差 ≥ 2 记 FAIL。
- 发表处：bib 的 `booktitle` / `journal` 提取会议 token（ICML、NeurIPS、ICLR、CVPR、ICCV、ECCV、EMNLP、ACL、AAAI、MLSys、TPAMI、TIP、IEEE Access、Operations Research、Euro-Par），在 arXiv comment / journal_ref、Crossref container / event、DBLP venue、`--index` 页面中找同义词；都没有则 WARN；证据里出现 "workshop" 而 bib 写主会则 FAIL。

## 退出码

`verify_bib.py`：0 全 PASS，1 有 WARN，2 有 FAIL。`cites.py`：有缺失键返回 1。
