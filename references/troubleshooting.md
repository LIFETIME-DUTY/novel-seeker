# 排错手册（troubleshooting）

按症状查。每条都写"为什么"，因为下一个坑往往是同一个原因换个样子出现。

## 抓取

**抓到的是乱码/随机汉字（长佩）**
- 现象：解密成功但读起来是"的了吗是在不"这种随机字，长度约真实文本的 1.5–1.7 倍，或只有 24 字节（加密空串）。
- 原因：站点按**出口 IP** 风控，返回"合法密文 + 伪明文"。不是 UA、不是 fingerprint、不是无头浏览器。
- 处理：`python scripts/textcheck.py` 会判成 decoy。换出口（`--proxy`，一个 IP 通常只够 1–3 章）、放慢（30–90 秒/章）、或等冷却（几十分钟到几小时）。
- 别做：不要"重试到看起来像中文为止"——伪文本也是合法中文，肉眼分不出，只有常用字占比能分。

**解密出来是空串，或全是乱码**
- 原因：站点升级了前端，AES key/iv 变了（旧参数来自某个版本的 ReadPc.js）。
- 处理：用 `CHANGPEI_KEY` / `CHANGPEI_IV` 环境变量覆盖；或按 `references/sources.md` 重新推导（在 SPA 主包里搜 `new Le(`）。
- 判断是否 key 过期：密文长度正常（>1KB）但解出来不是汉字 → key/iv 问题；解出来是汉字但不通顺 → 是风控伪文本。

**晋江某一章抓到登录页/错误页**
- 现象：字数明显偏小（几百字），或含"登录""购买"字样，`ratio` 很低。
- 处理：该章标记为缺口，稍后重抓；不要混进正文。免费文也可能偶发风控。

**抓到一半停了**
- 检查是不是被管道杀了（`| head`、`| tail` 会 SIGPIPE）——长任务一律 `> log 2>&1 &` 或后台 job。
- 检查后台 job 是否还活着；断点续抓会跳过已有章，直接重跑即可。

**章节数对、字数不对**
- 常见原因：某个"番外/说明/公告"被当成正文抓了，或末章是作者的话。看 `kt`/字数分布，把非正文条目单独处理（保留但别算进正文统计）。

## 构建

**`nav.xhtml` 目录是蓝字带编号**
- 原因：nav 在 `OEBPS/` 根，样式表必须 `href="css/style.css"`；写成 `../css/style.css` 就会掉样式。
- 处理：`build_book.py` 已按位置生成正确 href；若是自己改过，检查这一行。

**正文 <p> 与源 JSON 对不上（校验报段数不一致）**
- 若用了插图或「作者有话要说」：校验器已排除 `<figure>` / `<aside>` 里的 `<p>`；若仍报错，看是不是 note 段落被当成了正文。
- 若差 1–2 段：多半是空段被丢弃（`normalize.py` 会丢空段，源 JSON 里如果有空串，两边要统一）。

**Apple 图书看不到简介页**
- 三个原因，按顺序查：① `toc.ncx` 没收录前置页（本流程的 `build_book.py` 会收录）；② 书是旧的，`dcterms:modified` 没变 → Apple 用缓存；③ `dc:identifier` 没变且 Apple 认死了旧版本。
- 处理：重建（自动刷新 modified）→ 从书架删除、退出 App、重开再导入 → 仍不行用 `--new-id` 换 identifier。

**换了封面，阅读器里还是旧图**
- 原因：只换了 zip 里的图片，`dcterms:modified` 没变，阅读器按缓存显示旧封面；或新图格式与 opf 里的 media-type 不符。
- 处理：用 `inject_cover.py`（默认会刷新 modified；同秒重复注入会往后挪 1 秒，保证一定变化）；若手工改过，确认 opf 里 `<meta property="dcterms:modified">` 已经变成新时间。
- Apple 上还要：删除旧书 → 退出 App → 重导入。

**目录里的标题和正文标题对不上**
- 有的书写"第1章 回国"，有的写"第一章 回国"；nav 文案由 `display　title` 生成，`validate_epub.py` 会逐条比对：数量不符或顺序不对直接 FAIL，文案不一致 WARN。
- 处理：统一用 `--renumber` 重排，或检查 `book.json`/章节 JSON 里的 `display` 与 `title` 是否有一处手改过。
- 重号（两个"第37章"）也会在同一处 WARN，`--renumber` 一并解决。

**目录缺页 / 顺序乱，但不想重建整本**
- 用 `python scripts/patch_epub.py 书.epub --fix-nav --refresh-modified`：按 spine 顺序重建 `nav.xhtml` + `toc.ncx`，并把扉页/简介/版权页补进目录；只改目录与 opf，不动正文。
- 改完必须跑 `validate_epub.py 书.epub`（纯结构体检，不需要源 JSON）。

**txt 与 epub 内容不一致**
- `python scripts/check_txt.py 书.txt 书.epub` 逐章逐段比对，直接指出第几章第几段不同。
- 常见原因：txt 漏了「作者有话要说」标记行、epub 有插图/分节、或两份里有一份是旧构建。不要靠肉眼抽查。

**导入后有封面但书架显示灰块**
- 检查 manifest 里封面条目有没有 `properties="cover-image"`，opf 里有没有 `<meta name="cover" content="cover-image"/>`（EPUB2 兼容），spine 第一项是不是封面页。

**长章分节后目录里出现一堆条目**
- 分节用 `<section class="chapter-part">`，**不进 nav/ncx**；如果出现了，检查是不是把分节当成了独立 xhtml 文件写进 spine。

## 审校

**改完回头看，发现"改得像另一个人写的"**
- 症状：留白被补成直白、方言被抹平、刻意的重复被"修好"、倒叙被理顺、指代换错了人。
- 原因：**没先读懂就开改**。只看到孤立一句，判断依据是"这句通不通顺"，而不是"这句在这本书里是什么意思"。
- 处理：停下，跑 `read_prep.py` 生成概览/人物/风格抽样，亲自读到能回答"这本书在写什么、谁在场、哪些是故意不写透的"，把 `reading_brief.md` 九节填满，再重做该卷（每卷 prompt 都要带这份 brief）。

**`reading_brief.md` 填不出来**
- 不是"材料不够"，是还没读到位。先读首章、末章、每卷首尾、`style.md` 抽的十段；再搜几个高频意象确认母题。
- 允许粗糙（一句话概就可以先写草稿），**不允许空着就开改**。

**分卷子代理把段落数改了 / 漏字**
- 让子代理"整段重写"是高危操作（漏抄从句）。规范里要求"只替换片段"；校验器会报"长度比"和"段数"。
- 处理：该段回退，重新按最小改动做。

**人名/数字/英文 token 校验误报**
- 原因是原文本来就有不一致（如 "TAAKI/TAKKI"、"主任/经理"）。先人工判定这是不是作者笔误：是笔误就统一并在台账里记一笔；不是就保留并把该 token 加进白名单说明。

**`check_part.py` 报"结构字段被改动"**
- `part`/`figures`/`note` 不该由审校碰。分卷稿里缺少这些键是正常的（合并时从源稿继承）；报错说明分卷稿里写了不一致的值，删掉即可。

**改完自己都不敢确认"没改意"**
- 跑 `make_diff.py` 出台账，逐条过"三问"（事实变了吗/语气变了吗/删掉还读得懂吗）。读得懂的改动就不该在本轮出现。

## 环境

**Windows 控制台报 UnicodeEncodeError**
- `set PYTHONIOENCODING=utf-8`（或用 `python -X utf8`）。

**用 heredoc/内联 python 打补丁把文件改坏**
- shell 会把 `\n` 折叠成真换行，f-string、正则、JSON 都会被打断。**改代码一律用文件编辑**（write/edit），不要 `python - <<EOF` 改源码。

**macOS / Linux**
- 脚本只用标准库 + requests/Pillow/numpy，路径都用 `os.path`/`pathlib`；唯一带系统路径的是 `make_cover.py` 的字体候选（Windows/macOS 几处 + Linux 常见 Noto/Source Han），可用 `--font 字体文件` 覆盖；`msedge` 截图那一步在 macOS 上换成 `screencapture` 或直接跳过（不影响校验）。

**`make_cover.py` 字体找不到**
- 脚本按候选列表找（Windows: 思源宋体/宋体；macOS: STSong/STHeiti；Linux: Noto Serif CJK / Source Han Serif / uming / wqy-zenhei）。全找不到时**直接报错退出**（不静默出方块字），显式传 `--font <字体文件>`。
- Linux 装字体：`apt install fonts-noto-cjk`（Debian/Ubuntu）或 `dnf install google-noto-serif-cjk-fonts`。
