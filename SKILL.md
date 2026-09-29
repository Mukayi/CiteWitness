---
name: citewitness
description: >-
  Audit and write LaTeX/BibTeX citations strictly from retrieved records (arXiv API, Crossref, DBLP,
  proceedings indexes, paper full text), never from memory: finds hallucinated papers, fabricated or
  misspelled author names, wrong venues (workshop vs main conference), wrong years, and sentences that
  attribute claims a paper does not make; generates new .bib entries only from fetched metadata. Use whenever
  the user asks to check, verify, audit, fix, add or write references, citations, bib entries, related work,
  or mentions 引用 / 参考文献 / 文献 / bib / cite / 幻觉.
---

# CiteWitness — 每条引用都有记录作证（零幻觉的引用审查与撰写）

一条参考文献里的每个字段——标题、作者、年份、发表处、页码、arXiv 号——都必须来自一条**抓取到的记录**，并能给出记录的 URL。
凭记忆写出的作者名单是这类工作里最常见的幻觉（同一实验室不同论文的作者串行、拼错姓、漏人），其次是把工作坊海报写成主会论文。
本 skill 的脚本只用 Python 标准库、只走 https、只读不改。

## 零幻觉守则（不可逾越）

1. **不从记忆填写任何字段。** 作者、标题、年份、会议、卷期页码、arXiv 号、DOI 一律复制自记录；记录里没有的字段就不写。
2. **发表处只认论文集证据。** arXiv 记录的 comment 写 "Accepted by X" 只是作者声明，可写进 `note`；`booktitle` / `journal` 必须由论文集索引页（PMLR 卷页、NeurIPS/ICLR proceedings、CVF Open Access）、OpenReview 的 venue 字段或 Crossref 的 container-title 确认。**工作坊 ≠ 主会**：icml.cc / neurips.cc 的 virtual 页面会把工作坊海报也列出来，要看清 "Poster in Workshop"。
3. **找不到就不引。** 三个来源（arXiv、Crossref、DBLP）都搜不到的论文，明确告诉用户"未找到，不能引用"，不要猜一个近似的。
4. **归因要有原文。** 正文里"X 提出 / X 报告 / 与 X 一致"的每一处，都要在该论文的全文里找到支撑句并在报告里引用；找不到就标 UNVERIFIED 并建议删改。
5. **改 bib 时只粘贴脚本输出的字段值**（`verify_bib.py` 报告末尾的 "Field values copied from the matched records" 或 `fetch_entry.py` 的输出），并保留 `% source: <url> fetched <date>` 注释。
6. **报告里区分三档证据**：【实测】读过记录或原文；【推断】依摘要或二手页面；【未核实】来源不可达或未找到。不要把【推断】写成事实。

## 工作流 A：审查已有的 tex + bib

```
Progress:
- [ ] 1 清点：哪些键被引用、哪些缺失、哪些未用；每处引用的上下文
- [ ] 2 逐条核对 bib：标题 / 作者 / 年份 / 发表处
- [ ] 3 未确认的发表处：查论文集索引或 OpenReview
- [ ] 4 归因核对：正文对每篇论文的说法是否在原文里
- [ ] 5 出报告；只在用户要求时改 bib
```

**步骤 1** — 清点（读 tex 与 bib，不联网）：

```bash
python scripts/cites.py --bib main.bib --tex main.tex "sec/*.tex" "fig/*.tex" --json /tmp/cites.json
```

输出被引键、缺失键（会导致编译失败）、未引用条目，以及每个键的 `file:line` 与上下文句子（步骤 4 用）。

**步骤 2** — 核对 bib（联网；30 条约 40 s，arXiv 之间会自动间隔 3 s）：

```bash
# --index 可选、可重复：条目声称的论文集索引页，用于确认 booktitle
python scripts/verify_bib.py main.bib --keys <被引键...> \
    --index https://proceedings.mlr.press/v267/ \
    --md /tmp/bib_report.md --json /tmp/bib_report.json
```

每条给出 PASS / WARN / FAIL：
- FAIL：找不到记录、标题不符、作者名单有**记录里不存在的名字**或漏人或顺序不同。报告末尾给出从记录复制的正确字段值。
- WARN：发表处未被任何记录确认、年份差一（arXiv 上传年 vs 会议年，正常）、作者用 `others` 截断、团体作者、预印本条目已有正式发表处可升级。
- 标题 ratio 在 .80–.90 且开头相同，通常是论文改过名（arXiv 用简称、论文集用全称）：以论文集里的标题为准。

**步骤 3** — 发表处未确认时，去论文集索引或 OpenReview 找标题：

```bash
python scripts/webgrep.py --url https://proceedings.mlr.press/v267/ "<标题的几个词>"
python scripts/webgrep.py --url https://openreview.net/forum?id=<id> "Workshop|Poster|Oral|Spotlight"
```

`0 hit(s)` 是证据：标题不在主会论文集里，就不能写 `booktitle = {ICML}`。常用索引页见 [reference.md](reference.md)。

**步骤 4** — 归因核对。对 `/tmp/cites.json` 里每条上下文，抽出被归因的说法，在原文里找：

```bash
python scripts/webgrep.py --arxiv 1706.03762 "scaled dot-product attention"
```

把支撑句原文抄进报告；找不到 → UNVERIFIED，并建议改写或删引用。

**步骤 5** — 报告（模板见下）。默认**不改 bib**；用户要求修改时，只替换报告给出的字段值，每条上方加 `% source:` 注释，不动其他条目。

## 工作流 B：新写一条引用

1. 先搜候选，**不自动选择**：
   ```bash
   python scripts/fetch_entry.py --title "Attention Is All You Need"
   ```
   看 ratio、作者、年份、venue evidence，确认是用户要的那篇（同名工作、v1/v2、不同年份的同名论文都可能出现）。
2. 用确定的标识符生成条目：
   ```bash
   python scripts/fetch_entry.py --arxiv 1512.03385 --key resnet          # arXiv：全作者名单，journal=arXiv preprint
   python scripts/fetch_entry.py --doi 10.1109/TIP.2003.819861 --key ssim  # Crossref 自带的 BibTeX
   python scripts/fetch_entry.py --dblp-key conf/nips/VaswaniSPUJGKP17 --key attention
   ```
   arXiv 条目**不会**自动填 `booktitle`；comment / journal_ref 以 `%` 注释形式给出。要写会议名，先按工作流 A 步骤 3 确认，再手动把 `@article` 改成 `@inproceedings` 并填 `booktitle`。
3. 把条目连同 `% source:` 注释一起写入 bib；再跑一遍 `verify_bib.py --keys <新键>` 应为 PASS 或仅有"年份差一"的 WARN。
4. 正文里引用它时，说法必须来自你读过的原文（`webgrep.py --arxiv <id> --dump /tmp/paper.txt` 后阅读），不要转述二手摘要。

## 报告模板

```markdown
## 引用审查：<bib 文件>（<日期>）
被引 N 条，缺失 M 条，未用 K 条。核对来源：arXiv API / Crossref / DBLP（<可达情况>）/ 索引页 <url>。

| 键 | 结论 | 问题 | 依据 |
|---|---|---|---|
| `resnet` | FAIL | 作者名单含记录里不存在的 "John Smith" | https://arxiv.org/abs/1512.03385 |
| `dit` | FAIL | booktitle=NeurIPS，Crossref 记录为 ICCV 2023 | https://doi.org/10.1109/iccv51070.2023.00387 |
| `attention` | WARN | NeurIPS 2017 未被任何记录确认，需查 papers.nips.cc | - |
| ... | PASS | - | ... |

### 归因核对
- `attention`（sec/method.tex:42）"使用缩放点积注意力"：原文 §3.2.1 "Scaled Dot-Product Attention" 【实测】
- ...

### 建议修改（字段值均复制自记录）
- `resnet`: author = {Kaiming He and Xiangyu Zhang and Shaoqing Ren and Jian Sun}
```

## 已知陷阱

- 同一实验室的系列论文作者高度重叠，凭记忆极易把 A 文的作者写到 B 文上——这正是脚本按记录逐姓比对的原因。
- arXiv 版本间会改标题、改作者顺序；以最新版为准，并注明版本号。
- arXiv 版与会议定稿的作者名单可能不同（多一人或少一人并不罕见）。脚本会在 arXiv comment 里带作者自写 bibtex 时自动比对并降级为 WARN；引用哪个版本就用那个版本的名单，并在报告里写明差异。
- 期刊印刷年份可比 arXiv 晚一到两年；有卷期页码的期刊条目按出版社记录核年份。
- 标题里的连字符 / 大小写差异（Video-Gen vs VideoGen）会让索引页搜索漏掉，`webgrep.py` 用去空格的模式再试一次。
- 年份：arXiv 12 月上传、次年会议发表，差一年是正常的；差两年以上要查。
- DBLP、Semantic Scholar 在部分网络环境不可达（脚本会写"unreachable"）；Crossref 对 NeurIPS 早年论文无记录（用 papers.nips.cc）。
- 团体作者（"Wan Team"）与 50 人以上的作者名单：按目标 venue 的样式处理，但名字仍须来自记录。

## 附加资料

- 数据源、API 形式、论文集索引页地址与限流：[reference.md](reference.md)
