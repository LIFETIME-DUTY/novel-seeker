#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""正文真伪与水分的公共判据（供各 fetch 脚本复用，也可单独当体检工具）。

为什么需要它：有的站（不点名）在风控时会返回"能解开、但明文是随机汉字"的伪正文；
还有的站返回空串、只留标题、或把一章拆成几百字。只看长度会被骗，必须看"像不像人写的"。

三个指标：
  1. 常用字占比 = 汉字里落在常用字表内的比例。正常小说 ≈0.85–0.99，随机汉字串 ≈0.00–0.10。
  2. 字数/站点标注比例：站点若给了字数（kt），落在 0.7–1.55 之外就不可信。
  3. 标点密度 = 标点数/汉字数。正常叙事 ≥1/80；伪正文常几乎为 0。

用法（单独体检）:
    python textcheck.py _work/raw/chapters.json            # 逐章体检
    python textcheck.py _work/raw/chapters.json --kt-from _work/raw/chlist.json
    python textcheck.py some.txt --freq my_freq.json       # 自定义常用字表（JSON 数组）

在代码里用:
    from textcheck import looks_real
    ok, why = looks_real(text, kt=1349)         # → (True, "ok") / (False, "ratio 0.04")
"""
from __future__ import annotations

import argparse
import json
import re
import sys

# 常用字表（约 1000 字，按大致频次排列）。判"像不像中文正文"够用；
# 想更精确可传 --freq 一份用真实小说统计出来的字表（make_freq.py 可生成）。
COMMON_CHARS = (
    "的一是不了在人有我他这个们中来上大为和国地到以说时要就出会可也你对生能而子那得于着下自之年过发后作里"
    "用道行所然家种事成方多经么去法学如都同现当没动面起看定天分还进好小部其些主样理心她本前开但因只从想实"
    "日军者意无力它与长把机十民第公此已工使情明性知全三又关点正业外将两高间由问很最重并物手应战向头文体政"
    "美相见被利什二等产或新己制身果加西斯月话合回特代内信表化老给世位次度门任常先海通教儿原东声提立及比员"
    "解水名真论处走义各入几口认条平系气题活尔更别打女变四神总何电数安少报才结反受目太量再感建务做接必场件"
    "计管期市直德资命山金指克许统区保至队形社便空决治展马科司五基眼书非则听白却界达光放强即像难且权思王象"
    "完设式色路记南品住告类求据程北边死张该交规万取拉格望觉术领共确传师观清今切院让识候带导争运笑飞风步改"
    "收根干造言联持组每济车亲极林服快办议往元英士证近失转夫令准布始怎呢存未远叫台单影具罗字爱击流备兵连调"
    "深商算质团集百需价花党华城石级整府离况亚请技际约示复病息究线似官火断精满支视消越器容照须九增研写称企"
    "八功吗包片史委乎查轻易早曾除农找装广显吧阿李标谈吃图念六引历首医局突专费号尽另周较注语仅考落青随选列"
    "武红响虽推势参希古众构房半节土投某案黑维革划敌致陈律足态护七兴派孩验责营星够章音跟志底站严巴例防族供"
    "效续施留讲型料终答紧黄绝奇察母京段依批群项故按河米围江织害斗双境客纪采举杀攻父苏密低朝友诉止细愿千值"
    "仍男钱破网热助倒育属坐帝限船脸职速刻乐否刚威毛状率甚独球般普怕弹校苦创假久错承印晚兰试股拿脑预谁益阳"
    "若哪微尼继送急血惊伤素药适波夜省初喜卫源食险待述陆习置居劳财环排福纳欢雷警获模充负云停木游龙树疑层冷"
    "洲冲射略范竟句室异激汉村哈策演简卡罪判担州静退既衣您宗积余痛检差富灵协角占配征修皮挥胜降阶审沉坚善妈"
    "刘读啊超免压银买皇养伊怀执副乱抗犯追帮宣佛岁航优怪香著田铁控税左右份穿艺背阵草脚概恶块顿敢守酒岛托央"
    "户烈洋哥索胡款靠评版宝座释景顾弟登货互付伯慢欧换闻危忙核暗姐介坏讨丽良序升监临亮露永呼味野架域沙掉括"
    "舰鱼杂误湾吉减编楚肯测败屋跑梦散温困剑渐封救贵枪缺楼县尚毫移娘朋画班智亦耳恩短掌恐遗固席松秘谢鲁遇康"
    "虑幸均销钟诗藏赶剧票损忽巨炮旧端探湖录叶春乡附吸予礼港雨呀板庭妇归睛饭额含顺输摇招婚脱补谓督毒油疗旅"
    "泽材灭逐莫笔亡鲜词圣择寻厂睡博勒烟授诺伦岸奥唐卖俄炸载洛健堂旁宫喝借君禁阴园谋宋避抓荣姑孙逃牙束跳顶"
    "玉镇雪午练迫爷篇肉嘴馆遍凡础洞卷坦牛宁纸诸训私庄祖丝翻暴森塔默握戏隐熟骨访弱蒙歌店鬼软典欲萨伙遭盘爸"
    "扩盖弄雄稳忘亿刺拥徒姆杨齐赛趣曲刀床迎冰虚玩析窗醒妻透购替塞努休虎扬途侵刑绿兄迅套贸毕唯谷轮库迹尤竞"
    "街促延震弃甲伟麻川申缓潜闪售灯针哲络抵朱埃抱鼓植纯夏忍页杰筑折郑贝尊吴秀混臣雅振染盛怒舞圆搞狂措姓残"
    "秋培迷诚宽宇猛摆梅毁伸摩盟末乃悲拍丁赵硬麦蒋操耶阻订彩抽赞魔纷沿喊违妹浪汇币丰蓝殊献桌啦瓦莱援译夺汽"
    "烧距裁偏符勇触课敬哭懂墙袭召罚侠厅拜巧侧韩冒债曼融惯享戴童犹乘挂奖绍厚纵障讯涉彻刊丈爆乌役描洗玛患妙"
    "镜唱烦签仙彼弗症仿倾牌陷鸟轰咱菜闭奋庆撤泪茶疾缘播朗杜奶季丹狗尾仪偷奔珠虫驻孔宜艾桥淡翼恨繁寒伴叹旦"
    "愈潮粮缩罢聚径恰挑袋灰捕徐珍幕映裂泰隔启尖忠累炎暂估泛荒偿横拒瑞忆孤鼻闹羊呆厉衡胞零穷舍码赫婆魂灾洪"
    "腿胆津俗辩胸晓劲贫仁偶辑邦恢赖圈摸仰润堆碰艇稍迟辆废净凶署壁御奉旋冬矿抬蛋晨伏吹鸡倍糊秦盾杯租骑乏隆"
    "诊奴摄丧污渡旗甘耐凭扎抢绪粗肩梁幻菲皆碎宙叔岩荡综爬荷悉蒂返井壮薄悄扫敏碍殖详迪矛霍允幅撒剩凯颗骂赏"
    "液番箱贴漫酸郎腰舒眉忧浮辛恋餐吓挺励辞艘键伍峰尺昨黎辈贯侦滑券崇扰宪绕趋慈乔阅汗枝拖墨胁插箭腊粉泥氏"
    "彭拔骗凤慧媒佩愤扑龄驱惜豪掩兼跃尸肃帕驶堡届欣惠册储飘桑闲惨洁踪勃宾频仇磨递邪撞拟滚奏巡颜剂绩贡疯坡"
    "瞧截燃焦殿伪邻臭俩鹿巾"
)

PUNCT = set("，。、；：？！…—“”‘’（）《》〈〉「」『』【】·～￥%")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def load_freq(path: str | None) -> set[str]:
    """自定义常用字表：JSON 数组，或 {"top": [...]}。"""
    if not path:
        return set(COMMON_CHARS)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("top") or data.get("chars") or data.get("freq") or []
    if isinstance(data, dict):  # {字: 次数}
        data = list(data.keys())
    chars = "".join(str(x) for x in data)
    return set(chars) or set(COMMON_CHARS)


def han_count(text: str) -> int:
    return len(CJK_RE.findall(text))


def common_ratio(text: str, freq: set[str] | None = None) -> float:
    chars = CJK_RE.findall(text)
    if not chars:
        return 0.0
    freq = freq or set(COMMON_CHARS)
    return sum(1 for c in chars if c in freq) / len(chars)


def punctuation_density(text: str) -> float:
    """标点数 / 汉字数。"""
    n = han_count(text)
    if not n:
        return 0.0
    return sum(1 for c in text if c in PUNCT) / n


def looks_real(
    text: str,
    kt: int | None = None,
    freq: set[str] | None = None,
    ratio_min: float = 0.80,
    pd_min: float = 1.0 / 80,
    min_len: int = 200,
    max_len_ratio: float = 1.55,
    min_len_ratio: float = 0.70,
) -> tuple[bool, str]:
    """判断一段正文是不是"真的人写的"。返回 (ok, 原因)。"""
    t = (text or "").strip()
    n = han_count(t)
    if n < min_len:
        return False, f"too-short({n})"
    r = common_ratio(t, freq)
    if r < ratio_min:
        return False, f"ratio {r:.3f}"
    pd = punctuation_density(t)
    if pd < pd_min:
        return False, f"punct {pd:.3f}"
    if kt:
        ratio = n / kt
        if ratio > max_len_ratio:
            return False, f"too-long({n}/{kt}={ratio:.2f})"
        if ratio < min_len_ratio:
            return False, f"too-short-vs-kt({n}/{kt}={ratio:.2f})"
    return True, "ok"


def raw_of(text: str) -> str:
    return re.sub(r"\s", "", text or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--freq", default="")
    ap.add_argument("--kt-from", default="", help="站点章节表 JSON，含 kt/字数，按 cid 或 num 对齐")
    ap.add_argument("--ratio-min", type=float, default=0.80,
                    help="常用字占比下限（译文/古文可降到 0.75；默认 0.80）")
    ap.add_argument("--pd-min", type=float, default=1.0 / 80, help="标点密度下限（默认 1/80）")
    ap.add_argument("--min-len", type=int, default=200,
                    help="单章最少汉字数（默认 200；有极短公告章时降到 50）")
    ap.add_argument("--max-len-ratio", type=float, default=1.55, help="字数/kt 上限（默认 1.55）")
    ap.add_argument("--min-len-ratio", type=float, default=0.70, help="字数/kt 下限（默认 0.70）")
    args = ap.parse_args()

    kw = dict(ratio_min=args.ratio_min, pd_min=args.pd_min, min_len=args.min_len,
              max_len_ratio=args.max_len_ratio, min_len_ratio=args.min_len_ratio)

    freq = load_freq(args.freq)
    kt_map: dict = {}
    if args.kt_from:
        with open(args.kt_from, encoding="utf-8") as f:
            lst = json.load(f)
        if isinstance(lst, dict):
            lst = lst.get("list") or lst.get("chapters") or []
        for i, it in enumerate(lst, 1):
            k = it.get("cid") or it.get("id") or it.get("num") or i
            v = it.get("kt") or it.get("kt_number") or it.get("chars")
            if v:
                kt_map[k] = int(v)

    if args.path.endswith(".json"):
        with open(args.path, encoding="utf-8") as f:
            chapters = json.load(f)
        if isinstance(chapters, dict):
            chapters = chapters.get("chapters") or []
        bad = 0
        for ch in chapters:
            text = "\n".join(ch.get("paragraphs") or [])
            kt = ch.get("kt") or ch.get("kt_number") or kt_map.get(ch.get("num"))
            ok, why = looks_real(text, kt, freq, **kw)
            flag = "OK " if ok else "BAD"
            if not ok:
                bad += 1
            print(f"{flag} #{ch.get('num')} {ch.get('display','')} {ch.get('title','')} "
                  f"chars={han_count(text)} ratio={common_ratio(text, freq):.3f} "
                  f"pd={punctuation_density(text):.3f} {'' if ok else why}")
        print(f"\n总章节 {len(chapters)}  可疑 {bad}")
        return 0 if bad == 0 else 1

    with open(args.path, encoding="utf-8") as f:
        text = f.read()
    # txt 模式与 JSON 模式共用阈值；判成假文同样返回 1（否则当 txt 闸门用时会静默放行）
    ok, why = looks_real(text, None, freq, **kw)
    print(f"chars={han_count(text)} ratio={common_ratio(text, freq):.3f} "
          f"pd={punctuation_density(text):.3f} → {'OK' if ok else 'BAD: ' + why}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
