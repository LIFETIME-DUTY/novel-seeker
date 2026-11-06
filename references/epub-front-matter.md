# epub 前页、目录与阅读器坑（含 Apple 图书）

这些是被用户反复打回来的地方，逐条记住。

## 1. 前页顺序

```
cover.xhtml → titlepage.xhtml → intro.xhtml → 正文各章 → colophon.xhtml
```

spine 里必须是这个顺序。简介页要在**第一章之前、扉页之后**——用户明确要求过。

## 2. 扉页只放三样

```html
<body class="front">
  <div class="tp-title">书名</div>
  <div class="tp-sub">全　本</div>
  <div class="tp-author">作者　著</div>
</body>
```

不要平台名、不要字数、不要来源、不要标签、不要"精校版"字样。之前堆了这些，被要求全部删掉。

## 3. 内容简介页 = 简介正文 + 页脚两行

```html
<body class="intro">
  <h1 class="ct">内 容 简 介</h1>
  <div class="rule"></div>
  <p>…</p>
  <div class="intro-meta">
    <p class="meta-line">篇　幅：全 49 章（含番外），约 15.0 万字</p>
    <p class="meta-line">基　调：现实向 · 姐妹 · 救赎</p>
  </div>
</body>
```

页脚只留「篇幅」「基调」两项，不要作品名/作者/标签/来源。

## 4. 版权页

```html
<body class="colo">
  <h1 class="ct">版 权 页</h1>
  <div class="rule"></div>
  <p class="colo-row">书　　名　书名</p>
  <p class="colo-row">作　　者　作者</p>
  <p class="colo-row">全　　文　约 15.0 万字，共 49 章（含番外）</p>
  <div class="colo-sep"></div>
  <p class="colo-note">本书据网络连载整理校订。校订仅针对标点、分段、明显讹字与病句，力求文从字顺，未增删情节、未改动人物与事实。</p>
  <p class="colo-note">本电子书仅供个人阅读，不作商业用途。</p>
</body>
```

## 5. nav 与 toc.ncx 必须一致，且都要包含前置页 ⚠️

这是最容易漏的：epub3 里 `nav.xhtml` 有了条目、`toc.ncx` 只写了正文，按 NCX 导航的阅读器（Apple 图书就是）**看不到简介页**——用户在目录里翻不到，会以为文件做坏了。

两条命令自查：

```bash
python scripts/validate_epub.py x.epub --chapters norm.json    # 会比对 nav/ncx，并强制前置页必须进目录
```

正确形态：nav 是 ncx 的子序列（顺序一致），前几条是 `书名 / 内容简介 / 第1章…`。

**两级目录（部/卷）**：`book.json` 给 `parts` 或每章给 `part` 时，nav 用嵌套 `<ol>`、ncx 用嵌套 `navPoint`，`dtb:depth=2`。此时 **ncx 条目数会比 nav 多**（部节点 + 章节点各一条），这是正常的；校验器只要求"nav 每条都在 ncx 里且顺序一致"。

## 5b. 插图与「作者有话要说」

- `"figures": [{"after": 3, "file": "img/c01.jpg", "alt": "…", "caption": "图一"}]` → 在第 3 段后插 `<figure><img/><figcaption/></figure>`，图片写进 `OEBPS/img/` 并登记 manifest。`file` 用相对路径时以**源 chapters.json 所在目录**为基准（`normalize.py` 会把它转成绝对路径，之后换目录也不会丢图）。
- `"note": ["…"]` → 章末 `<aside class="author-note">`，带「作者有话要说」小标题，样式比正文小一号、灰一点；**txt 里则写成单独一段 `【作者有话要说】` + 正文**，读者一眼能看出这不是小说正文。
- 校验器比对正文时**排除** `<figure>` 与 `<aside>` 里的 `<p>`，否则段数会对不上。

## 5c. 超长章自动分节

单章超过 `--split-chars`（默认 5000 字）时按段落边界切 `<section class="chapter-part">`，CSS 给它 `.chapter-part { page-break-before: always }`（或在阅读器里各占一屏），但**不进 nav/ncx**。

交付时必须说明：*"第 X、Y 章太长，我在章内做了无标题分节，只为换页顺一点，目录里仍按原章。"* 否则用户会以为章节被切坏了。

## 5d. 不做封面（--no-cover）

不写 `OEBPS/images/cover.*` 与 `OEBPS/text/cover.xhtml`，spine 第一项是 `titlepage.xhtml`，`opf` 里也没有 `<meta name="cover">`。
校验器对此只报 `WARN`，不判失败。以后要补：`python scripts/inject_cover.py x.epub cover.jpg`（只改封面条目、自动转码成原格式 + 刷新 `dcterms:modified`，正文不动）。

## 5e. 简介页脚（篇幅/基调）

`book.json` 的 `intro_meta` 可以手写，但**不写也不会缺**：构建时按实际章数/字数自动生成

```
篇　幅：全 58 章（含 4 篇番外），约 20.7 万字
基　调：meta.tone，或 tags 前三个
```

版权页的章数一律用"全书章数"（含番外），不要再单独算"正文 N 章"——那是两套口径，容易自相矛盾。

## 5f. 章号重号与 --renumber

源站常见"两个第 37 话"或"第62章 一点题外话"这种混编。构建时的处理顺序是：

1. 先按 `EXTRA_RE`（番外/extra/后记/题外话/free talk/作者的话）判定附赠篇；
2. 正文按阅读顺序编「第 k 章」，附赠篇编「番外一、番外二…」；
3. `--renumber` 会把算出来的 display 真正写回（不加则沿用源站的 display），并打印重号列表；
4. `complete_check.py` 也会报 display/num 重号，构建后在 `validate_epub.py` 里还会核对"目录文案 = display　title"。

## 6. Apple 图书缓存 ⚠️

Apple 按 `dc:identifier` + `dcterms:modified` 判定"是不是同一版"。改了内容但 `dcterms:modified` 没变，它继续显示旧副本（用户会坚持"我没看到"）。

- 构建会自动写当前 UTC；`inject_cover.py` 换封面时也会自动刷新（同秒重复注入会往后挪 1 秒，保证一定变化），不想刷就 `--keep-modified`
- 若仍不更新：让用户从书库删除 → 退出 App → 重导入；再不行用 `--new-id` 换 `dc:identifier`（uuid4，相当于当新书导入；旧 id 会记在 `meta.prev_ids`）
- 交付时可给出体积与 md5 指纹，方便用户核对"拿到的是新版"

## 7. zip 结构

- `mimetype` 必须是**第一条**且 **STORED**（不压缩），内容 `application/epub+zip`
- 图片建议 STORED，其余 DEFLATED
- `META-INF/container.xml` → `OEBPS/content.opf`
- epub3：`<package version="3.0" unique-identifier="bookid">`，nav 的 `<item properties="nav">`，spine 带 `toc="ncx"`

## 8. 中文字体与排版

```css
body {
  font-family: "Source Han Serif SC", "Songti SC", "SimSun", serif;
  line-height: 1.9;
  text-align: justify;
}
p { margin: 0.5em 0; text-indent: 2em; orphans: 2; widows: 2; }
section.chapter { page-break-before: always; }
body.cover img { width: 100%; height: auto; display: block; }
```

- 首行缩进 2em、行高 1.9、段距 0.5em，是被用户认可的组合
- 章标题：`<h1 class="ct">第1章<span class="sub">仲未放得低？</span></h1>` + 分隔线
- 目录页去掉默认蓝色与有序编号：`nav#toc ol{list-style:none} nav#toc a{color:#333;text-decoration:none}`
- 场景分隔符段（原文单独一个 `-`）渲染成 `<p class="sep">＊　＊　＊</p>`

## 9. 验收动作

- 解包后用 `msedge --headless=new --screenshot` 截 cover/titlepage/intro/nav/正文各一张，肉眼过一遍
- `ebooklib` 读一遍：items / toc / spine 数目对得上
- 逐章 `<p>` 文本与源 JSON 逐字比对 0 处不符（`validate_epub.py` 已含）
