# 工作流细节与话术

## 目录约定

```
书名/
├── 书名（抓取版）.txt
├── 书名（精校版）.epub            # 审校后
├── _work/
│   ├── book.json                  # 元信息
│   ├── raw/chapters.json          # 原始抓取
│   ├── norm/chapters.json         # 规范化后
│   ├── proof/out/p1…             # 审校分卷
│   ├── proof/merged.json          # 合并稿
│   └── out/                       # 构建产物
└── 封面/书名/
    ├── 书名-主版（已采用）.jpg
    ├── 书名-备选·<概念>.jpg
    └── README.md
```

## 阶段命令序列

```bash
# 0 建库
mkdir -p _work/{raw,norm,proof/out,out}
# 写 _work/book.json（书名/作者/简介/tags/cover）

# 1 抓取（以晋江为例）
python scripts/fetch_jjwxc.py search "书名"
python scripts/fetch_jjwxc.py book <novelid> -o _work/raw/chapters.json --log _work/fetch.log

# 1b 完整性核对（章数/字数/重号/断号/空章）
python scripts/complete_check.py _work/raw/chapters.json --declared-chapters 58 --declared-chars 206862

# 2 规范化
python scripts/normalize.py _work/raw/chapters.json -o _work/norm/chapters.json --report _work/norm/report.txt

# 3 构建（源站章号有重号时加 --renumber）
python scripts/build_book.py _work/norm/chapters.json --meta _work/book.json -n "书名（抓取版）" --outdir . [--renumber]

# 4 封面（可选）
python scripts/make_cover.py "书名" "作者" --gradient night --out _work/cover.jpg
python scripts/inject_cover.py "书名（抓取版）.epub" _work/cover.jpg   # 会顺带刷新 dcterms:modified

# 5 质检
python scripts/validate_epub.py "书名（抓取版）.epub" --chapters _work/norm/chapters.json --strict-platform
python scripts/check_txt.py "书名（抓取版）.txt" "书名（抓取版）.epub"   # txt 与 epub 逐段一致
python scripts/complete_check.py _work/norm/chapters.json --declared-chapters 58 --declared-chars 206862
python scripts/complete_check.py _work/norm/chapters.json
python scripts/final_check.py _work/norm/chapters.json --out _work/体检.md
```

## 构建阶段三件易漏事项

1. **重号**：源站常见"两个第 37 话"。加 `--renumber` 会按阅读顺序重排正文、把尾部附赠篇编成「番外一…」，并打印重号警告；不加就原样保留。
2. **txt 里的「作者有话要说」**：章末附言写成单独一段 `【作者有话要说】` + 正文，和小说正文区分开（epub 里是 `<aside class="author-note">`）。
3. **页脚自动生成**：`book.json` 不写 `intro_meta` 时，构建会按实际章数/字数自动生成「篇　幅 / 基　调」两行；写了就用写的。

## 交付时说的话（模板）

> 《书名》（作者）已经抓全：**N 章 / X 万字**，和站点标注比对一致；来源是 <主源>，另外用 <副源> 交叉核对过字数与抽样段落。
> 产出两份：`书名（抓取版）.txt` 与 `书名（抓取版）.epub`（正文一致，epub 多了封面与版式；扉页/简介/目录/版权页都已按统一格式做好）。**两份一起给**——本流程不提供"只要 txt"，你要 txt 的话 epub 留着不用就行。
> 版本说明：抓的是 <连载版/出版版>，<完结/连载中>，番外 <N> 篇。
> （有长章分节时补一句）其中第 X、Y 章太长，我在章内做了无标题分节，只为阅读器换页顺一点，目录里仍按原章。
> 需要的话我可以再做一轮审校（轻/重两档，见下），或者只出一份体检报告（不动文）。

## 抓取阶段的结束提示（重要）

抓取完成时必须主动给出下一步，而不是等用户问：

> 如果你要更干净，可以做一轮审校，分两档。**两档共同的底线是：绝对不改作者原意**——情节、事实、语气、留白都不动，只修形式错误（缺标点、错别字、该用问号的地方用了句号）。
> 两档开始前，我都会**先把全书读懂**（生成章节概览、人物候选表、风格抽样，写一份理解备忘），再按这份理解去改——否则很容易把留白补成直白、把方言改掉。
> **轻型**——确定性排版 + 一遍通读，按 12 类形式错误最小改动，每处记录原/改/理由，改完做语义回读。
> **重型**——包含轻型全部内容，另加：开头 1–2 章人工精修做黄金范例、**按章数切卷（每卷 8–12 章，卷数 = ⌈总章数÷10⌉）**并行（每卷都带着理解备忘）、每卷机器校验、合并后全量质检 + 独立语义复核 + 抽检、人称指代专项（`pron_scan.py`）、改动台账（`make_diff.py`）、争议项清单交你裁决。
> 也可以只做质检（只出报告，不动文）。要哪个？

## 审校前置（不许跳）

```bash
python scripts/read_prep.py _work/norm/chapters.json -o _work/reading
# 然后人读 + 填满 _work/reading/reading_brief.md（九节）
python scripts/check_reading.py _work/reading/reading_brief.md
```

`check_reading.py` 不通过，就不要切卷、不要开改：除「留白」外任一节空着是 FAIL；「留白」一节空着只 WARN（留白不是每本都有——确实没有就写一句「本书几乎没有明显留白」+依据，但必须专门想过）。每卷的分卷 prompt 必须带上这份备忘。

## 完整性核对清单

- [ ] `complete_check.py` 全绿（或只有可解释的 WARN：章节数区间、字数偏差、附赠篇短）
- [ ] 章节数 = 站点目录条数（含番外、Free Talk、作者附言）
- [ ] 总字数与站点标注差 < 3%（`complete_check.py --tolerance` 可调紧；站方字数常含标题与空白，差值偏大未必是缺章）
- [ ] 最后三章标题对得上
- [ ] 每章段数 > 0，无空章
- [ ] 抽样 3 章与站点原文规范化后逐字相等
- [ ] display/num 不重复（重复就 `--renumber`）

## 交叉比对清单

- [ ] 副源字数/章节数与主源接近（差 < 2%）
- [ ] 抽 3–5 段逐字对比（差异多半是错字或删改，记录下来但以主源为准）
- [ ] 若副源多出章节（缺章补全），以副源补齐并在交付说明里注明
