# 交付前清单（checklist）

两条原则：**能自动查的别用眼睛看；要给人看的必须真打开看一次。**

## A. 机器闸门（全绿才算过）

```bash
python tests/run_smoke.py                                        # 链路自测（改过脚本就跑）
python scripts/normalize.py raw.json -o norm.json --report norm.txt
python scripts/complete_check.py（重号/断号会 FAIL；确认是原著编号重复才加 --allow-dup） raw.json --declared-chapters 58 --declared-chars 206862
python scripts/build_book.py norm.json --meta book.json -n "书名（抓取版）"
python scripts/validate_epub.py "书名（抓取版）.epub" --chapters norm.json --strict-platform
python scripts/complete_check.py norm.json                      # 构建后再跑一次（看 display 重号）
python scripts/final_check.py norm.json --names 甲,乙,丙
```

- [ ] mimetype 第一条且 STORED；全部 XML 可解析
- [ ] spine：封面（或扉页）→ 扉页 → 简介 → 正文 → 版权页
- [ ] 前置页在 nav **和 ncx** 里都有
- [ ] **目录文案 = `display　title`**，且 display/num 不重号（重号用 `--renumber`）
- [ ] 每章正文 `<p>` 与源 JSON 逐字一致（0 处不符）
- [ ] `<img>` 全部存在；声明 cover-image 就有 cover.xhtml
- [ ] 全库无来源平台字样（`--strict-platform`）
- [ ] txt 与 epub 的章节数、段落数一致
- [ ] 有 `dcterms:modified` 且是本次构建时间；换过封面的话必须已刷新（`inject_cover` 默认会刷）

## B. 三端自检（真打开看）

| 端 | 怎么看 | 重点 |
|---|---|---|
| Apple 图书（macOS/iOS） | 导入后看「书库」缩略图与「目录」 | 封面是否显示、**简介页能不能点开**、目录是否有编号/蓝字、正文首行缩进 |
| Android 阅读器（静读天下 / ReadEra / 微信读书） | 打开 → 目录 → 随机一章 | 中文断行、行距、章首是否另起页、图片是否显示 |
| Windows（Calibre / Edge 打开解包目录） | Calibre 里看「元数据」「目录」 | 书名/作者/语言、封面、ncx 是否完整；Edge 直接开 `OEBPS/text/ch001.xhtml` 看排版 |

三端都要看的四件事：**封面满版无白边、目录能从扉页/简介点进去、正文缩进 2em、章与章之间确实换页**。

## C. 内容核对（人看）

- [ ] **审校前**：`python scripts/check_reading.py _work/reading/reading_brief.md` 通过（九节填满；「留白」一节允许写「本书几乎没有明显留白」+依据，留空只会 WARN 不阻塞）
- [ ] **审校中**：每一卷的 prompt 里都带了 `reading_brief.md`；改动与「留白清单」「人物表」冲突的一律回退
- [ ] 首章首段、末章末段与源站一致（首尾最容易缺）
- [ ] 章数 = 源站章数；番外一篇不缺
- [ ] 扉页只有书名/全本/作者；简介页没有来源字样；版权页篇幅数字与正文实算一致
- [ ] 有插图/「作者有话要说」的话，位置对（图在第 N 段后、note 在章末）
- [ ] 长章分节的章节，目录里仍然只有一章（分节不进目录）

## D. 交付话术（缺一不可）

- [ ] 来源（主源 + 副源）与版本（连载版/出版版、完结与否）
- [ ] 字数、章节数、番外数
- [ ] 做了哪些处理（规范化、审校档位与改动段数、封面来源与概念）
- [ ] **哪些是刻意保留的**（作者风格：`？？？`、`……`、单句成段、不加引号的对话、口语词）
- [ ] 有分节时说明「无标题分节是自动切分，不进目录」
- [ ] 备份路径与清理结果（书目录只剩成品）

## E. 清理

- [ ] `_work/`、临时截图、`.bak` 文件不在书目录
- [ ] 封面归档到 `封面/<书名>/`：主版 + 备选 + README（尺寸/概念/与 epub 内嵌同 sha1）
- [ ] 原件备份在 `%TEMP%`（Windows）或 `/tmp`（macOS/Linux），路径告诉用户
