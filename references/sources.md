# 书源搜寻、交叉比对与反爬应对

## 找源顺序

1. **先确认书**：书名 + 作者 → 搜书页（豆瓣/百科/出版信息/作者微博），确认章节数、番外篇名、主角名。同名书极多，别跳过这步。
2. **找连载源站**：多数中文 GL/言情首发在晋江、长佩，也可能在其它站。用站内检索确认 `novel_id`。
3. **列副源**：贴吧/论坛转载、TXT 站、书摘站、公众号。副源不追求全文，只要能与主源对字数、抽段比对即可。
4. 判定"主源"的标准：章节最全、有番外、文本最干净。

## 晋江（jjwxc）

- 检索走 AJAX：`/search/search_ajax.php?action=search&keywords=<kw>&type=1&version=1&getfull=1`，返回 JSON，含 `novelid`/`authorname`。
- 章节页：`/onebook.php?novelid=<id>&chapterid=<n>`；正文在 `<div id="paragraph_comment_content">`。
- 编码 `gb18030`。节流 1.5–2 秒。
- 免费文 `jurisdiction` 为空；入 V 章节正文会是购买提示——**停下告知用户**。
- 目录从作品页 `onebook.php?novelid=<id>` 里抓 `chapterid=<n>` 链接即可。

## 长佩（gongzicp）

- 阅读站是 `www.gongzicp.com`（Vue SPA）；接口必须走**同源代理** `/webapi/...`，直连 `api1.gongzicp.com` 会返回「访问异常/缺少参数」。
- 必需头：`Authorization: Basic <SPA 主包里的串>`、`Client: pc|h5`、普通 UA/Referer。
- 接口：
  - `GET /webapi/search/novels?k=<kw>&page=1`
  - `GET /webapi/novel/chapterGetList?nid=<id>`（过滤 `chapter_type=="more"` 的哨兵项）
  - `GET /webapi/novel/chapterGetInfo?cid=<id>&server=0`
- 正文用 AES-CBC/PKCS7，key/iv 在 SPA 主包里由一个小类算出来（本 skill 的 `fetch_changpei.py` 已写死解出的值）。
- **风控**：`data.check >= 2` 时返回的仍是合法密文，但明文是随机汉字（伪文本）。判真四指标见下。伪文本按 cid 预生成并缓存，长度常是真文的 1.7 倍。
- 同一出口 IP 连续请求会被降级（先是伪文本，后是 24 字节的"加密空串"）。换出口/等冷却。免费文也会被限，不是登录墙。
- 出现滑块验证码（阿里云 v2）时**不要尝试绕过**，告诉用户。

## 判真四闸门（统一 `scripts/textcheck.py`）

| 指标 | 阈值 | 说明 |
|---|---|---|
| 常用字占比 | ≥0.80 | 内置约 1000 常用字即可跑；有 `freq_common.json`（`make_freq.py` 用一本正常书生成 top-1500）时更准。真实小说 ≈0.92，随机汉字 ≈0.07，混 8% 生僻字 ≈0.83 |
| 字数 / 站点 kt | 0.7–1.55 | 站点标注与真实字数口径不同，用区间不用等值 |
| 标点密度 | ≥1/80 字 | 伪文本几无标点 |
| 可见字符数 | ≥200 | 短章（作者附言）单独放行，别用同一把尺 |

四条全过才落盘。任何一条不过 → 记为失败，退避重试或换出口。

命令行：`python scripts/textcheck.py _work/raw/chapters.json`（逐章打印 ratio/pd/结论）。

## 正文解密的版本风险（长佩）

`fetch_changpei.py` 里的 AES key/iv 来自某一版前端：

```
KEY = u0LRrbu$Enm84koA      # atob("dTBMUnJidSRFbg==") + parseInt("4d5a6c8",14).toString(36) + "A"
IV  = $h$b3!iGzsYnnshj      # "$h$b3!" + ("iGzsYn" + parseInt("165455",14).toString(32))
```

站点升级前端后可能换参数，症状是：密文长度正常但解出来是乱码/空串。处理：
1. 先用环境变量覆盖试用：`CHANGPEI_KEY=… CHANGPEI_IV=…`；
2. 重新推导：在 SPA 主包（`assets/index.*.js`）里搜 `new Le(`，取两个实参，按上面两条公式换算；
3. 若连主包都换了加密方式，退回"换站/找镜像"路线，不要硬啃。

## 规避符还原

站点会自我审查：`傻.逼`、`傻/逼`、`鸡/巴`、`做/爱`、`高／潮`、`他.妈`、`D.a.mn`。规范化阶段还原（`normalize.py` 已含规则），注意别误伤小数与英文缩写。

## 常见失败与处理

| 现象 | 原因 | 处理 |
|---|---|---|
| 正文是随机汉字 | 反爬伪文本 | 判真四指标（`textcheck.py`）；换出口/等冷却 |
| content 只有 24 字节 | 限流空串 | 视同失败，冷却重试 |
| 章节页 404 | URL 形如 `/read-<cid>.html`，别拼错 | 从书目页 href 取真实链接 |
| 字数比站点少很多 | 漏章/番外未列 | 对比目录条数，副源补 |
| 有章节一直失败 | 该章过短（如作者附言 100 字） | 放宽长度闸门，但保留常用字与标点判据 |

## 节流与长任务

- 1.5–3 秒/章，遇限流指数退避（8s → ×1.35，上限 45s）
- 断点续抓：每章落盘，重跑跳过已有
- 长任务写日志文件，**不要 `| head`**（SIGPIPE 会杀掉进程）
- 后台跑：`python fetch_xxx.py … > _work/fetch.log 2>&1 &`
