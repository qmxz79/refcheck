# RefCheck — Reference Auditor

自动化验证参考文献是否真实存在，发现重复引用，匹配正文引用与文献列表，并对疑似造假的引用自动推荐真实替换论文。

## 功能

| 功能 | 说明 |
|------|------|
| ✅ **存在性检查** | 通过 CrossRef → PubMed → Semantic Scholar 三级验证 |
| 🔁 **重复检测** | 自动发现重复引用（DOI 相同或作者+年份相同） |
| 📝 **引用完整性** | 匹配正文中的 in-text citation 与参考文献列表 |
| 💡 **假引用替换建议** | 对无法验证的引用，提取关键词搜索 PubMed，推荐真实论文 |
| 📄 **支持 .docx** | 直接解析 Word 文档的参考文献章节 |

## 快速使用

### 安装依赖

```bash
pip install biopython requests python-docx
```

### 验证单个 DOI

```bash
python scripts/verify.py doi 10.1038/nature12373
```

### 验证单个 PMID

```bash
python scripts/verify.py pmid 12345678
```

### 验证引用列表

```bash
cat refs.txt | python scripts/verify.py list
```

`refs.txt` 格式示例：

```
10.1038/nature12373
10.1126/science.1058040
Smith J, et al. A novel biomarker for cancer detection. J Med. 2023.
```

### 验证 Word 论文

```bash
python scripts/verify.py docx "path/to/thesis.docx"
```

## 输出报告

生成 Markdown 报告，包含：

```
# Reference Audit Report

## Summary
- Confirmed real: 2
- Not found (suspicious): 1
- Duplicate pairs: 0
- Unmatched citations: 1

## Potentially Fake/Hallucinated References
| # | Raw text | Suggested replacement |
|---|----------|----------------------|
| 1 | 10.1234/fake-doi... | [Marth C (2019) Immunotherapy in ovarian cancer...](https://pubmed...) |

## All References
| # | Reference | Status | Source | DOI/PMID |
|---|-----------|--------|--------|----------|
| 1 | 10.1038/nature12373... | ✅ | CrossRef | 10.1038/nature12373 |
| 2 | 10.1234/fake-doi... | ❌ | none | - |
```

## 验证流程

```
输入 → 解析引用
  ├─ DOI → CrossRef API (最可靠)
  ├─ PMID → PubMed E-utilities
  └─ 标题/作者 → PubMed → Semantic Scholar
       ↓ 未找到
  标记为可疑 → 提取关键词 → 搜索PubMed推荐替换
```

## 作为 Pi Agent Skill 使用

将此目录添加到 `~/.pi/agent/settings.json` 的 `skills` 列表中：

```json
{
  "skills": [
    "skills/refcheck"
  ]
}
```

触发关键词：`"verify references"`、`"check references"`、`"验证参考文献"`、`"fake reference"`

## 技术栈

- [Biopython](https://biopython.org/) — PubMed E-utilities 接口
- [CrossRef REST API](https://api.crossref.org/) — DOI 解析
- [Semantic Scholar API](https://www.semanticscholar.org/product/api) — 标题/作者搜索
- [python-docx](https://python-docx.readthedocs.io/) — Word 文档解析

## License

MIT
