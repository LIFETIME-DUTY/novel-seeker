---
name: novel-seeker
description: 把一本中文网络小说从书名做成可读的 txt + epub（或对已按本流程做过的 epub 做升级）：搜源定位、抓全并验真、规范化排版、补封面/扉页/内容简介/目录/版权页，可选做一轮不改原意的资深编辑审校与全量质检。当用户说「帮我抓/下载/搜某本小说」「把这本做成 txt 和 epub」「做一个精校版」「给这本书换封面/加版权页/补简介」「这本小说审校一下」时使用。只做通用电子书转换（PDF/Office 转格式、纯排版）时不要用本 skill。
---

# Novel Seeker

把一个书名变成能读的书：**定位来源 → 抓全并验真 → 规范化 → 构建 txt + epub →（可选）审校与质量检查**。

审校必先读懂：不是通读序言那种"懂"，而是要能说出这本书在写什么、谁在场、哪些地方作者故意不写透，然后才允许切卷改动（见"阶段 7 · 第 0 步"）。

这个 skill 来自几本真实成书的完整流程（家庭现实、都市悬疑、娱乐圈、县城现实各一本），每步后面都写着"为什么"，因为中文网络小说这条路上真正的问题是：来源混杂、反爬给假文本、审校容易改坏原意、epub 目录与阅读器缓存。

## 何时该用

- 用户给书名，想拿到 txt / epub / 精校版
- 用户已有 epub，想换封面、加版权页、补简介、修目录
- 用户想"审校"一本小说（补标点、改病句），且要求不改原意

## 先确认三件事（缺就问，别猜）

1. **书名 + 作者**。同名书极多（单字、两字的书名尤其爱撞），先确认是同一本再动手。
2. **封面要不要做**；要做的话，**原创**还是**官方封面**，还是**不做封面**。三个选项都要把差别讲清楚（见"阶段 4"）。
3. **审校档位**。用户没提就不做，但抓取完成后要主动提示并解释两档（见"阶段 7"）。

另外两点不要问、直接按默认做，但要在交付时说明：
- **抓取阶段固定交付 txt + epub 两份**（内容一致，epub 多封面与版式），不提供"只要 txt"的选项；用户如果只要 txt，把 epub 留着不给他即可。
- **部/卷、插图、"作者有话要说"**：源站有就保留（见"阶段 3"），没有就不造。

其余（平台、分卷、命名）按下面的默认值走，不必逐条问。

环境准备：**核心流程零第三方依赖**（构建、校验、规范化、审校、质检都只用标准库），`python -m pip install -r requirements.txt` 只是给抓取与生成封面用。Windows 建议设 `PYTHONIOENCODING=utf-8`。第一次用或改完脚本，先跑 `python tests/run_smoke.py`；想确认"没装任何依赖也能用"，跑 `python tests/run_bare.py`（应输出 `BARE OK`）。

---

## 阶段 0 · 定位与建库

目标：确认"这本书到底是哪一本、正文在哪、有多长"。

1. 先搜书名，再核对：作者、简介、主角名、章节数、番外篇名、是否已出版（出版信息可交叉验证）。
2. **核对版本**（这一步最容易省掉，然后整本抓错）：
   - 是**连载版**还是**出版版/修订版**？两者章数、番外、删改都可能不同（有的书出版后重写了结局）。
   - 站点显示**连载中还是完结**？完结的话，最后一章的日期要早于今天；连载中就问用户要不要等。
   - 番外是否齐全（作者常在番外里写"番外一/二"，但站上可能缺一两个）。
   - 豆瓣/百科的目录、字数与站上对不对得上；对不上就说明手里的是另一个版本。
   - 结论写进 `book.json` 的 `version_note`，交付时告诉用户"抓的是哪个版本"。
3. 找到**连载源站**（晋江、长佩、其它），确认是否免费、是否需要登录。
4. **广泛搜来源，不只一家**：把能读到正文的站点都列出来，取完整性最好的一家当**主源**，其余当**副源**（至少一家）用于交叉比对。理由：单源会缺章、串行、被反爬塞假文本。
5. 建工作目录，源码与产物分离：

```
_work/
├── raw/           # 原始抓取 JSON（每章一段一条）
├── norm/          # 规范化后的 JSON
├── proof/         # 审校分卷稿与合并稿
└── out/           # 构建产物（txt/epub）

（skill 自带的脚本在 skill 目录的 scripts/ 下，直接调用，不用拷进 _work/。）
```

6. 元信息落到 `book.json`，后续脚本都读它：

```json
{
  "title": "书名",
  "author": "作者",
  "source_primary": "https://…",
  "sources_secondary": ["https://…"],
  "series_note": "完结 / 全本",
  "tags": ["现实向", "姐妹"],
  "tone": "现实向 · 姐妹 · 救赎",        # 可选：简介页脚「基调」；不给则用 tags 前三个
  "intro": ["段落1", "段落2"],
  "colophon_note": "本书据网络连载整理校订。校订仅针对标点、分段、明显讹字与病句，力求文从字顺，未增删情节、未改动人物与事实。",
  "chapters": "raw/chapters.json"
}
```

`raw/chapters.json` 结构（后续所有脚本都认这个形状）：

```json
[
  {"num": 1, "title": "仲未放得低？", "display": "第1章", "paragraphs": ["…", "…"]},
  {"num": 55, "title": "Free Talk", "display": "番外一", "paragraphs": ["…"]}
]
```

`display` 与 `title` 分开存：正文写「第1章」，目录要能显示「番外一」「番外·初秋」这类，互不影响。

结构化字段（都可选，`build_book.py` 认）：
- `"part": "上卷"`（或 `book.json` 里给 `"parts": [{"label":"上卷","from":1,"to":40}, …]`）→ 目录做**两级**（部/卷 → 章）。
- `"figures": [{"after": 3, "file": "img/ch01-1.jpg", "alt": "雨夜的门", "caption": "图一"}]` → 在第 3 段后插一张图（图片随 epub 一起打包）。
- `"note": ["今晚更得晚，抱歉……"]` → 章末「作者有话要说」区块。
这三个字段属于"结构"，审校脚本会校验它们不被改动（见阶段 7）。

## 阶段 1 · 取文（最容易翻车的地方）

三条硬关卡，缺一条就会交付一本残书或假书：

1. **完整性**：抓完跑一遍
   ```
   python scripts/complete_check.py _work/raw/chapters.json --declared-chapters 58 --declared-chars 206862
   # 重号/断号现在默认 FAIL；确认是原著重复编号时才加 --allow-dup 降级为 WARN
   ```
   它会报章数/字数差、重号（真实书里出现过两个「第37话」）、断号、重复标题、空章，并打印末三章标题供人工对照站点。字数差在 ±3% 内通常只是标点/空白口径（实例：声明 206,862，抓到 207,081，差 219）。
2. **真伪**：有的站（长佩）在风控时返回"加密但解密后是随机汉字"的伪正文。判真统一用一个脚本 `scripts/textcheck.py`：常用字占比 ≥0.80（内置约 1000 常用字，有 `freq_common.json` 时用统计基准）、字数与站点标注比例落在 0.7–1.55、标点密度 ≥1/80 字、可见字符 ≥200。四个指标任一不过就当失败，**同一章重试/换出口**，千万别把假文本存进去。
   - 标定参考：真实小说常用字占比 0.917、标点密度 0.169；随机汉字伪文 0.072；混 8% 生僻字 0.834（说明 0.80 的线留了余量）。
   - 逐章体检：`python scripts/textcheck.py _work/raw/chapters.json`
3. **规避符还原**：`傻.逼`、`傻/逼`、`鸡/巴`、`做/爱`、`高／潮`、`D.a.mn` 这类站点自我审查产物要还原（这是清理，不是改文）。

其他要点：
- 编码按站点来（晋江 `gb18030`，多数新站长佩 UTF-8）；解码失败先试编码，不要直接替换字符。
- 抓取节流 1–2 秒/章；长任务用后台 job + 日志文件（`--log` 参数带书名与时间戳，避免并发覆盖），**不要用管道 `| head`**（缓冲满 SIGPIPE 会杀掉任务）。
- 断点续抓：每章落盘，重跑跳过已有章。
- 出口被风控时：换代理再试（`--proxy http://127.0.0.1:1080`），一个出口通常只够 1–3 章。
- 遇到登录墙/付费/验证码：**停下来告诉用户**，把已拿到的范围与缺口说清楚，让用户决定（他可能另有来源）。不做绕过。

站点实现细节见 `references/sources.md`，脚本见 `scripts/fetch_jjwxc.py`、`scripts/fetch_changpei.py`。

**交叉比对**：副源只做低成本校验——字数与章节数是否接近，再抽 3–5 段逐字比。副源版本常与主源不同（错字、删改），不做全文 diff，噪声太大。

## 阶段 2 · 规范化（确定性，零主观）

```
python scripts/normalize.py _work/raw/chapters.json -o _work/norm/chapters.json
```

规则可枚举：半角标点→全角（仅当紧邻汉字）、`...`/`….`→`……`、`--`→`——`、引号方向、汉字之间的多余空格、零宽字符、连续空段、`。。`→`。`、规避符还原。

规避符还原也要克制：`傻.逼`/`做.爱`/`他.妈` 这类站点自我审查的写法可以还原（那是作者的原文），但**不要碰** `38.7`、`v1.0`、`D.C.` 这类正常点号——判据是"点号两侧是汉字且去掉后仍是常用脏话/敏感词"。还原的目的是恢复作者写的字，不是替作者补写。

**不要在这一步做任何"改写"**：断句、语序、同义词都属于阶段 7，混进来就再也说不清哪里被改过。

## 阶段 3 · 构建 txt + epub

```
python scripts/build_book.py _work/norm/chapters.json --meta _work/book.json -n "书名（抓取版）" --outdir .
```

常用可选：`--no-cover`（不做封面）、`--new-id`（换 `dc:identifier`，让 Apple 当新书导入，旧 id 自动记进 `meta.prev_ids`）、`--split-chars 5000`（单章超长时自动切节，0 表示不切）、`--renumber`（按阅读顺序重排章号并修正重号，尾部附赠篇编成「番外一…」——源站有重号时必须加；**输出 `<文件名>.renumbered.json` + `<文件名>.renumber_map.json`，不改你的源文件**）、`--extras-from N`（从第 N 章起算附赠篇；标题里没有「番外」字样时用它，别让程序猜）。

输出两份，**必须同时给**，内容一致，epub 只是多封面与版式（见 `references/workflow.md` 的交付说明）：

- `书名（抓取版）.txt`：UTF-8 BOM；前置 `书名 / 作者　著 / 全　本 / ==== / 内容简介 / 段落… / 页脚两行 / ====`，然后每章「第N章　标题」，段间空行；章末「作者有话要说」写在前带 `【作者有话要说】` 标记，不会和正文混淆。
- `书名（抓取版）.epub`：EPUB3；`mimetype` 第一条且 STORED；`container.xml`、`content.opf`、`nav.xhtml`、`toc.ncx`、`css/style.css`、`text/` 每章一文件。
- 用户选了**不做封面**时，构建加 `--no-cover`：不写 `images/cover.<ext>` 与 `text/cover.xhtml`，spine 第一项是扉页；校验器对此只报 WARN（无封面书可忽略），不判失败。

**前页顺序固定**（这个顺序是被用户反复调整出来的）：

```
cover → titlepage → intro → 正文各章 → colophon
```

（不做封面时最前面没有 cover，从 titlepage 开始。）

- 扉页：只有书名、「全　本」、作者　著。**不要**堆平台名、字数、来源、标签。
- 内容简介：简介正文 + 页脚两行（`篇　幅：全 N 章（含 M 篇番外），约 X 万字` / `基　调：…`）。**不写 `intro_meta` 时脚本会按实际章数字数自动生成**，`基　调` 取 `meta.tone` 或 `tags` 前三个。简介**不能**写来源平台。
- 版权页：书名、作者、篇幅 + 两段说明（据网络连载整理校订、仅供个人阅读）。

**目录必须与 nav 完全一致，且必须包含前置页**——`toc.ncx` 少了扉页/简介，Apple 图书就"看不到简介页"，这次真踩过。`build_book.py` 同时生成 nav 与 ncx；两级目录时 ncx 会比 nav 多出部/卷节点（正常），校验器按"nav 每条都在 ncx 里且顺序一致"判。

**长章自动分节**：一章超过 `--split-chars`（默认 5000 字）时，按段落边界切成 `<section class="chapter-part">`，**不进目录**（否则目录被 40 个"第12章·2"塞满）。构建时会打印哪几章被切了，交付时必须告诉用户：

> 这本里有几章太长（第 X、Y 章），我在章内做了无标题分节，只是让阅读器换页更顺，目录里还是按原章走。

其余可选结构（部/卷、插图、作者有话要说）见"阶段 0"的字段说明；`references/epub-front-matter.md` 有完整版式与 CSS。

## 阶段 4 · 封面（要问，不要默认做）

抓取默认**清除一切来源字样**（「晋江文学城」「长佩文学」「自制精校版」之类）。给用户的选项要讲清楚，**必须包含"不做封面"**，三个选项并列：

- **程序化原创**：用 PIL 按"主旨或一个令人印象深刻的情节"设计。常用做法：把书名里的关键一个字做质感处理（烧蚀/水渍/刻痕）；家庭题材用"一扇亮着灯的窗"；城市题材用"天际线 + 水面倒影"；县城/底层题材用"铁门缝里的一线灯"。优点是不撞车、能贴合内容；缺点是要迭代，效果依赖设计。
- **官方封面**：直接取站方插图或出版封面。优点是"作者认可"；缺点是分辨率常不够（300×400）、常带平台字样或 3D 书模，需要去字与放大。
- **不做封面**：epub 不生成封面页与 `images/cover.*`，spine 第一项直接是扉页；`build_book.py` 加 `--no-cover`。要说清后果：**多数阅读器书架会显示书名占位或灰块**（Apple 图书会自己生成一个纯色+书名的缩略图），不影响正文阅读；txt 本来就没有封面。以后想加，用 `inject_cover.py` 直接补，正文不用重做。

问法示例：「封面要做吗？三选一：① 我按内容原创一张（贴合主旨，需要几轮迭代）；② 用官方封面（可能要放大、去平台字样）；③ 不做封面（阅读器会显示书名占位，以后随时能补）。」

无论做哪种（或不做），正文构建都不受影响：封面只是 epub 的一个可选条目与一页。

做的话按 `references/cover-brief.md` 的硬约束（尺寸与书槽位一致、必须有书名/作者、缩略图可读性自检、去字不能留接缝）。

脚本：`scripts/make_cover.py`（底图 + 文字层；找不到系统中文字体时用 `--font 字体文件` 指定）、`scripts/inject_cover.py`（把新封面写回已有 epub：只改封面条目，**自动把新图转成原封面格式**（保证 media-type 与扩展名一致），**并自动刷新 `dcterms:modified`**——否则阅读器会继续显示旧封面；epub 被阅读器占用时会报错退出，不会留半成品）。

## 阶段 5 · 质量闸门

```
python scripts/validate_epub.py "书名（抓取版）.epub" --chapters _work/norm/chapters.json --strict-platform
python scripts/check_txt.py "书名（抓取版）.txt" "书名（抓取版）.epub"   # txt 与 epub 必须逐段一致
python scripts/final_check.py _work/norm/chapters.json --strict     # --strict 才有非零退出码
python scripts/complete_check.py _work/norm/chapters.json          # 完整性（章数/重号/断号）

已经交付过、源 JSON 已清理的 epub，可以只做结构体检：`validate_epub.py 书.epub`（不给 --chapters）。
想给**任意** epub 改前页/修目录：`patch_epub.py 书.epub --titlepage --intro-file 简介.md --fix-nav --refresh-modified`。
```

必须全过：

- zip 结构、mimetype 首条 STORED、全部 XML 可解析
- manifest ↔ spine ↔ nav ↔ ncx 一致，spine 第一项是封面（无封面时是扉页）
- **前置页（扉页/简介）出现在 nav 与 ncx 里**（否则 Apple 看不到简介页）
- **`<img>` 引用的图片都在包里**、声明了 cover-image 就必须有 `text/cover.xhtml`
- 每章 `<p>` 文本与源 JSON **逐字**一致（0 处不符；图注与「作者有话要说」不算正文段）
- **目录文案 = 章节标题**（`display　title`），且 `display` 不重号；不一致会 WARN，重号会提示用 `--renumber`
- 无平台字样残留（`--strict-platform`）、无图片以外的外部引用
- txt 与 epub 章节数、段落数一致

排版还要看一眼：`msedge --headless=new --screenshot` 截图封面/扉页/简介/目录/正文/番外各一张，确认缩进、行距、标题层级；再按 `references/checklist.md` 过一遍**三端自检**（Apple 图书 / Android 阅读器 / Windows 上的 Edge 或 Calibre 各开一次）。

**Apple 图书的坑**：改过内容但 `dcterms:modified` 没变，Apple 会继续显示缓存里的旧副本。每次构建都刷新 `dcterms:modified`；若仍不更新，用 `--new-id` 换 `dc:identifier`（相当于当新书导入）。详见 `references/epub-front-matter.md`、`references/troubleshooting.md`。

## 阶段 6 · 交付

- 抓取版命名 `书名（抓取版）.txt/.epub`；审校后命名 `书名（精校版）.txt/.epub`（或沿用户既有命名习惯）。
- 封面归档到 `封面/<书名>/`：`书名-主版（已采用）.jpg` + `书名-备选·<概念>.jpg` + `README.md` 记尺寸/概念/与 epub 内嵌封面同 sha1。
- 中间文件（`_work/`、临时截图、备份 epub）清掉，书目录只留成品；备份放 `%TEMP%` 并告知路径。
- 交付前过一遍 `references/checklist.md`（含三端自检 + 交付话术清单）。
- 交付时一句话说清：来源、字数与章节数、做了哪些处理、哪些是刻意保留的。

## 阶段 7 ·（可选）审校 —— 两档都要讲明白再问

### 第 0 步：先读懂，再动笔（两档都要，不能跳）

审校出错的根因，往往不是标点知识不够，而是**没读懂这句在说什么**——于是把留白补成直白、把方言改成普通话、把作者刻意的重复当错字、把倒叙理顺。

所以在切卷/开改之前，必须做完这四件事，并把结果写成 `_work/reading/reading_brief.md`：

1. `python scripts/read_prep.py _work/norm/chapters.json -o _work/reading`（已存在的 `reading_brief.md` 默认不覆盖，要重写加 `--force`，会先备份 `.bak`）——生成全书概览（每章字数/段数/首句）、候选人物名（需人工确认）、以及五类风格抽样段落（最长/最短/对话/破折号/省略号各 2 段）。
2. **亲自读完**：至少读首章、末章、每卷首尾、以及 `style.md` 抽出的段落。长篇做不到逐字读，但必须做到能回答"这本书在写什么、谁在场、谁在说话"。
3. 填满 `reading_brief.md` 的九节：一句话 / 主线 / 人物表 / 叙述方式 / 语言与语气（含**刻意重复清单**）/ 反复意象 / **留白清单** / 本作审校红线 / 三句自检。
4. `python scripts/check_reading.py _work/reading/reading_brief.md` 过闸门：除「留白」外的节空着 → FAIL，不许开改。

**关于留白**：留白不是每本书都有，但**必须专门想过**。确实没有的，就在第 7 节写一句「本书几乎没有明显留白」+ 依据（叙述直给 / 结尾闭合 / 心理全交代），闸门会接受并提示；留空会被 WARN。判断法是问自己：**这段作者为什么不多写一句？** 答案若是"想留想象空间 / 故意不说破 / 让读者自己补"，那就是留白，改动时不许替作者补上、也不许解释它。

**这份备忘是切卷的准入条件**：每一卷的分卷任务都必须带上它（连同该卷源文），否则子代理只能靠孤立的句子做判断，必然改意。填不出哪一节，就回去读，不要开始切卷。

### 最高约束（两档通用，任何情况不得突破）

**绝对不允许改变作者原意，或文章所表达的含义。** 这一条高于"改得通顺""改得好看""符合规范"，也高于任何改动率指标。

「原意」不是只看字面事实，它有三层：

1. **事实层**：谁、何时、何地、做什么、什么因果、什么程度。
2. **语气层**：作者的态度——确定还是猜测、心疼还是讽刺、克制还是直白。限定词（几乎/大概/也许/似乎）、句末助词（吧/啊/呢/罢了）、停顿与破折号都算。
3. **留白层**：作者故意不写透的地方。留白是写法，不是缺陷。

最危险的六类隐性改意（字面通顺，机器抓不到）：删或换限定词、改句末助词、把含蓄说白、把留白补全、改因果/责任方向、把短句合并掉作者靠断句制造的节奏。

每处改动过三问，任一"是"就撤回：**事实变了吗？语气变了吗？删掉这个改动还读得懂吗？**（读得懂就不该改）

只许改"形式错误"（缺标点、错别字、衍字、该用问号用了句号），不许改"表达选择"（节奏、用词偏好、留白、口音）。作者写得"不好读"不等于写错。

### 怎么向用户讲

抓取交付时主动提示，话术可照这个说：

> 书已经能读了。如果要更干净，我可以再做一轮审校，分两档。**两档的共同底线是：绝对不改你的作者的原意**——情节、事实、语气、留白一律不动，只修形式错误（缺标点、错别字、该用问号的地方用了句号这类）。
> **轻型**——确定性排版 + 一遍通读，按 12 类形式错误最小改动；每处改动都记录原句/改句/理由，改完再语义回读一遍。适合源文本来就干净的书，耗时短。
> **重型**——包含轻型全部，另外：我先亲手精修 1–2 章做"黄金范例"，再**按章数切卷（每卷 8–12 章，卷数由总章数决定：100 章 ≈ 10 卷、50 章 ≈ 5 卷、200 章 ≈ 18 卷）**并行，每卷过机器校验（段数/人名/数字/英文 token/相似度），合并后全量质检 + 独立语义复核 + 人称指代专项，拿不准的一律不改、列成争议清单交你裁决。适合长期收藏，耗时明显更长。
> 要哪一档？或者先只做质检（只出体检报告，不动文）？

细节见 `references/proofreading.md`；校验器 `scripts/check_part.py`、合并 `scripts/merge_parts.py`、全量诊断 `scripts/final_check.py`。

审校四条硬约束：

- **先读懂再动笔**（见「第 0 步」）：`reading_brief.md` 九节填满之前不许切卷；每卷 prompt 必须带这份备忘。读不懂这句在说什么，就不许改这句。
- **不得改意**（见上）：不确定就保留 + 进争议清单；理由里不许出现"更顺""更好听"。
- **子代理必须限 token**：每个分卷 prompt 只给"审校规范 + 该卷源文 + 输出格式"，明确"只回 JSON，不要解释过程"，**每批 8–12 章**（旧版"按字数切 5–6 卷"与"不超过 10 章"是自相矛盾的：62 万字的书切 5 卷，一卷 35 章，必爆 token）。卷数 = ⌈总章数 ÷ 10⌉。
- **只做最小改动**：段数、段序、人名、数字、英文 token 一律不许变；机器先卡一遍，人再抽查。第一版就漏抄过一个从句——是校验器抓出来的，不是肉眼。**但校验器防不了悄悄改意**，所以两档都必须做语义回读：只看"意思是否等价"，不看"是否更顺"。
- **改完留 diff**：`python scripts/make_diff.py 原.json 改后.json -o diff.md`，逐段 `[-删-][+增+]` + 按类型统计（标点/指代/断句/字词/其他）。用户问"你到底改了啥"时，这张表就是答案。

配套脚本：`textcheck.py`（真伪体检）、`pron_scan.py`（人称指代四级扫描：L3 性别冲突 / L2 建议核对 / L1 段首代词可抽样 / L4 承接提示）、`apply_pron.py`（只允许"代词→人名"的机械应用，其余进拒绝清单）、`make_diff.py`（改动台账）、`complete_check.py`（完整性核对）。

---

## 绝对不要做的事

- 不绕过登录、付费、验证码；遇到就停下告知用户。
- **不在没读懂的前提下动正文**：`reading_brief.md` 九节没填满，不许切卷、不许改一句。
- **不改变作者原意**（事实、语气、留白三层都不许动）——这条比"通顺"重要，也比改动率指标重要；拿不准就保留。
- 不删改情节、不合并拆分段落、不换同义词"提升文笔"、不把 `「」` 改成 `“”`、不把 `——` 改成逗号。
- 不把来源平台写进封面、扉页、简介、版权页。
- 不在用户没要求时动正文（只抓取就只规范化，不"顺手润色"）。

## 速查

| 任务 | 命令 |
|---|---|
| 自测（first run） | `python tests/run_smoke.py` |
| 审校前置：读懂 | `python scripts/read_prep.py _work/norm/chapters.json -o _work/reading`（然后填 `reading_brief.md`），再过 `python scripts/check_reading.py _work/reading/reading_brief.md`（留白节可写「几乎无明显留白」+依据，空着只 WARN） |
| 逐章真伪体检 | `python scripts/textcheck.py _work/raw/chapters.json`（`--ratio-min/--pd-min/--min-len` 可调） |
| 完整性核对 | `python scripts/complete_check.py raw.json --declared-chapters 58 --declared-chars 206862` |
| 规范化 | `python scripts/normalize.py raw.json -o norm.json` |
| 构建 | `python scripts/build_book.py norm.json --meta book.json -n "书名（抓取版）" --outdir .` |
| 构建（不要封面） | `python scripts/build_book.py norm.json --meta book.json -n "书名（抓取版）" --no-cover` |
| 构建（换 identifier，治 Apple 缓存） | `python scripts/build_book.py norm.json --meta book.json -n 书名 --new-id` |
| 构建（重排章号/重号） | `python scripts/build_book.py norm.json --meta book.json -n 书名 --renumber` |
| 校验 | `python scripts/validate_epub.py x.epub --chapters norm.json --strict-platform` |
| 校验（纯结构，无源 JSON） | `python scripts/validate_epub.py x.epub` |
| txt↔epub 一致性 | `python scripts/check_txt.py x.txt x.epub` |
| 改任意 epub 前页/修目录 | `python scripts/patch_epub.py x.epub --titlepage --intro-file 简介.md --fix-nav --refresh-modified` |
| 体检 | `python scripts/final_check.py norm.json --names 甲,乙,丙 [--strict]` |
| 指代扫描 | `python scripts/pron_scan.py norm.json --female 甲,乙 --male 丙 -o 指代.md` |
| 应用指代修订 | `python scripts/apply_pron.py norm.json edits.json --names 甲,乙,丙 -o fixed.json` |
| 改动台账 | `python scripts/make_diff.py 原.json 改后.json -o diff.md` |
| 分卷校验 | `python scripts/check_part.py _work/proof/out/p1 3-15 --src norm.json` |
| 合并分卷 | `python scripts/merge_parts.py _work/proof/out -o _work/proof/merged.json --src norm.json` |
| 生成封面 | `python scripts/make_cover.py 书名 作者 --gradient night --out cover.jpg` |
| 换封面 | `python scripts/inject_cover.py x.epub cover.jpg` |

排错见 `references/troubleshooting.md`；交付前清单见 `references/checklist.md`。
