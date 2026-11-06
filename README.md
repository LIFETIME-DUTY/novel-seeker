# novel-seeker

把一本中文网络小说从书名做成能读的 **txt + epub**：搜源定位 → 抓全并验真 → 规范化排版 → 构建前页与目录 → （可选）不改原意的资深编辑审校 + 全量质检。

这个 skill 是从几本真实成书的流程里抽出来的（家庭现实、都市悬疑、娱乐圈、县城现实各一本），每一步都写清了"为什么"，因为这条路上真正的坑是：**来源混杂、反爬返回假正文、审校容易改坏作者原意、epub 目录与阅读器缓存**。

---

## 安装

DSH / 兼容 Agent Skills 的环境：

```bash
# 方式一：git clone 后放进 skills 目录
git clone <本仓库地址> ~/.dsh/skills/novel-seeker

# 方式二：下载 zip 解压
unzip novel-seeker.zip -d ~/.dsh/skills/

# 方式三：Windows 资源管理器
#   把 novel-seeker 文件夹整个放进 %USERPROFILE%\.dsh\skills\
```

放好后目录应为 `~/.dsh/skills/novel-seeker/SKILL.md`。确认加载：

```bash
python ~/.dsh/skills/novel-seeker/tests/run_smoke.py     # 应输出 ALL PASS
```

## 依赖

**核心流程零第三方依赖**：Python 3.10+ 即可跑规范化、构建、校验、审校、质检（`normalize` / `build_book` / `validate_epub` / `check_txt` / `patch_epub` / `read_prep` / `apply_pron` / `make_diff` / `complete_check` / `final_check` / `textcheck`）。

按需安装（只有对应环节需要）：

| 功能 | 需要 | 缺失时的表现 |
|---|---|---|
| 抓取晋江 | `requests` | 脚本直接报错并提示 `pip install requests` |
| 抓取长佩 | `requests` + `pycryptodome` | 同上 |
| 生成封面 / 换封面转格式 | `Pillow` + `numpy` | 报错提示；可用 `--no-cover` 或官方图 + `inject_cover.py` 跳过 |
| socks5 代理 | `PySocks` | 仅 socks 代理不可用 |

```bash
python -m pip install requests pycryptodome Pillow numpy PySocks   # 全装
```

> 解压后**不装任何依赖**也能直接跑通测试与成书主流程，可自行验证：
> `python tests/run_bare.py`（它会屏蔽 Pillow/numpy/requests 再跑那两套测试，应输出 `BARE OK`）。

## 目录结构

```
novel-seeker/
├── SKILL.md                     # 主流程（阶段 0–7），先读这个
├── README.md                    # 本文件
├── requirements.txt
├── .gitignore
├── references/
│   ├── workflow.md              # 各阶段的命令与清单
│   ├── proofreading.md          # 审校规范（含「先读懂」与「不改原意」硬约束）
│   ├── epub-front-matter.md     # 封面/扉页/简介/目录/版权页的字段与顺序
│   ├── sources.md               # 各站抓取要点、真伪四指标、长佩解密
│   ├── cover-brief.md           # 原创封面怎么想、三种封面选项
│   ├── troubleshooting.md       # 症状 → 原因 → 处理
│   └── checklist.md             # 交付前三端自检清单
├── scripts/                     # 21 个可执行脚本（见下表）
└── tests/
    ├── run_smoke.py             # 全链路冒烟（35 项断言，自造 6 章书）
    └── verify_review_fixes.py   # 回归：把踩过的 P0 bug 固化成断言（18 项）
```

## 脚本一览

| 阶段 | 脚本 | 作用 |
|---|---|---|
| 抓取 | `fetch_jjwxc.py` | 晋江：搜索 / 书页 + 章节表 / 逐章正文（含真伪提示、`--log`） |
| 抓取 | `fetch_changpei.py` | 长佩：搜索 / 章节表 / 逐章正文（AES 解密、`--proxy`、`--log`） |
| 抓取 | `textcheck.py` | 判真假正文（常用字占比 / 字数比 / 标点密度 / 长度），txt 与 JSON 都可用 |
| 抓取 | `complete_check.py` | 完整性：章数、字数、重号、断号、重复标题 |
| 规范化 | `normalize.py` | 脏标点、规避符还原（白名单）、省略号/破折号、直引号、章节编号里的点 |
| 构建 | `build_book.py` | 生成 txt + epub3（封面/扉页/简介/部卷两级目录/插图/作者有话要说/长章分节/版权页） |
| 构建 | `make_cover.py` | 程序化原创封面（渐变 + 书名 + 作者，无平台字样） |
| 构建 | `inject_cover.py` | 给已有 epub 换封面（自动转码、刷新 `dcterms:modified`） |
| 构建 | `patch_epub.py` | 给**任意** epub 改扉页/简介/版权页/修 nav+ncx，不需要源 JSON |
| 审校 | `read_prep.py` | 生成《先读懂》材料：大纲、人物表、风格样本、九节 brief 模板 |
| 审校 | `check_reading.py` | 九节 brief 闸门（留白节允许"本书没有明显留白"声明，只 WARN） |
| 审校 | `check_part.py` | 分卷校验：段数、人名、数字、英文、相似度、缺章/越界 |
| 审校 | `merge_parts.py` | 合并分卷稿（按源顺序，结构字段从源稿继承） |
| 审校 | `apply_pron.py` | 应用人称指代修订（白名单校验，拒绝项不写正式输出） |
| 审校 | `pron_scan.py` | 指代异常扫描（L3 性别冲突 / L2 群体冲突 / L1 段首代词 / L4 无人名代词） |
| 审校 | `merge_parts.py` → `make_diff.py` | 生成审校 diff 台账（逐段增删 + 类型统计） |
| 质检 | `validate_epub.py` | 结构 + 目录一致性 + 图片存在 + 正文逐字比对（可选 `--chapters`） |
| 质检 | `check_txt.py` | txt ↔ epub 逐章逐段比对 |
| 质检 | `final_check.py` | 专名/数字/英文一致性与残留问题体检（`--strict` 有非零退出码） |
| 工具 | `make_freq.py` | 用一本正常书统计常用字，供判真使用 |
| 工具 | `_common.py` | 共享常量（结构字段 `part`/`figures`/`note`） |

## 快速开始（最小路径）

```bash
export PYTHONIOENCODING=utf-8          # Windows 中文输出必须

# 1. 定位书源（示例：晋江搜索）
python scripts/fetch_jjwxc.py search "书名"

# 2. 抓正文（长佩需要 --proxy 或等风控冷却）
python scripts/fetch_changpei.py chapters --nid 12345 -o _work/raw --log _work/fetch.log

# 3. 判真 + 完整性
python scripts/textcheck.py _work/raw/chapters.json
python scripts/complete_check.py _work/raw/chapters.json --declared-chapters 58

# 4. 规范化
python scripts/normalize.py _work/raw/chapters.json -o _work/norm/chapters.json

# 5. 构建（封面可选；不做封面加 --no-cover）
python scripts/build_book.py _work/norm/chapters.json --meta _work/book.json \
    -n "书名（抓取版）" --outdir . --extras-from 55

# 6. 质检
python scripts/validate_epub.py "书名（抓取版）.epub" --chapters _work/norm/chapters.json --strict-platform
python scripts/check_txt.py "书名（抓取版）.txt" "书名（抓取版）.epub"
```

审校（可选）见 `SKILL.md` 阶段 7：**先 `read_prep.py` 读懂 → 填 `reading_brief.md` → `check_reading.py` 过闸门 → 才允许切卷**。

## 测试

```bash
python tests/run_smoke.py            # 35 项：自造 6 章书跑完整链路
python tests/verify_review_fixes.py  # 18 项：历史 P0 bug 回归
python tests/run_bare.py             # 零依赖环境自检（屏蔽 Pillow/numpy/requests 再跑上面两套）
```

两套都应为 `ALL PASS`。`run_smoke.py -v` 打印每步输出，`--keep` 保留临时目录供检查。

## 已知限制

- `fetch_jjwxc.py` / `fetch_changpei.py` 只做过代码审读 + 小样本实跑，站点改版会失效（长佩 AES 参数可 `CHANGPEI_KEY`/`CHANGPEI_IV` 覆盖）。
- `textcheck.py` 的阈值是经验值（真实书常用字占比 ≈0.92，伪文本 ≈0.07），自建语料可用 `make_freq.py` 校准。
- `pron_scan.py` 是提示器，不是判官：命中不等于错，需要看上下文。
- macOS / Linux 未实机验证；`make_cover.py` 需要系统里有中文字体（找不到会报错，用 `--font` 指定）。
- 只处理**中文网络小说**。PDF / Office / 纯格式转换不要用这个 skill。

## 版本

- 2026-11：首版。含 21 个脚本、7 篇参考、2 套测试；独立审查发现的 9 个 P0 与主要 P1 已修复并固化为回归。
