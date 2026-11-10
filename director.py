#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""短片导演助手（Cinematic Video Director Assistant）

一个零第三方依赖的命令行工具（Python 3 标准库），把「电影短片导演」方法论
落成三个能直接跑的功能：

1. storyboard  输入一句话故事 + 目标时长，调用大模型 API（OpenAI 兼容
               /chat/completions）按每段 10 秒拆分镜表，输出 Markdown 表格。
2. color       本地检索内置的 1200 张 FrameForge 导演色卡库，按关键词
               返回主卡的编号 / ID / 六个 HEX / 11 项参数，不调 API。
3. stitch      按分镜段数生成 scripts/stitch_grade.sh 的拼接命令示例。

API Key 只从环境变量读取（DIRECTOR_API_KEY），也支持在当前目录放一个
.env 文件（格式见 .env.example）。代码与仓库里不保存任何真实 Key。
"""

import argparse
import html
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_API_BASE = "https://maas-api.cn-huabei-1.xf-yun.com/v2"
DEFAULT_MODEL = "spark-x2.6"
DEFAULT_CATALOG = ROOT / "references" / "frameforge_color_cards.md"
GRADE_KEYS = [
    "exposure", "temperature", "tint", "contrast", "saturation",
    "highlights", "shadows", "fade", "grain", "skinProtect", "lookStrength",
]


# ---------------------------------------------------------------- .env 加载
def load_dotenv():
    """把同目录或当前目录 .env 里的 KEY=VALUE 读进环境变量（不覆盖已有值）。"""
    for cand in (Path.cwd() / ".env", ROOT / ".env"):
        if cand.is_file():
            for line in cand.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))
            break


# ---------------------------------------------------------------- 功能 1：分镜生成
STORYBOARD_SYSTEM = (
    "你是一位电影短片导演，擅长把故事拆成可逐段生成的 10 秒分镜。"
    "规则：每段只装一个动作或一次情绪转折；相邻段的落幅要能接上下一段的起幅；"
    "人物、服装、场景在各段保持一致；多人场面不安排人对人打斗，只做对峙、"
    "单人表演或训练向动作；每段写明色调口径。"
)

STORYBOARD_USER_TMPL = """把下面的故事拆成正好 {n} 段、每段 10 秒的分镜表（总时长 {duration} 秒）。

故事：{story}

只输出一张 Markdown 表格，不要任何额外解释。表头固定为：
| 段号 | 时间 | 剧情 | 景别 | 主运镜 | 起幅 | 落幅 | 色调口径 |
主运镜从推、拉、摇、移、跟拍、环绕里选一种。色调口径写清这一段的主色调与肤色处理。"""


def call_chat_api(api_key, api_base, model, messages, timeout=120):
    url = api_base.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "stream": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise SystemExit(f"API 调用失败 HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        raise SystemExit(f"API 调用失败（网络）: {e.reason}")
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise SystemExit("API 返回结构异常：" + json.dumps(data, ensure_ascii=False)[:500])


def cmd_storyboard(args):
    load_dotenv()
    api_key = os.environ.get("DIRECTOR_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "未找到 API Key：请先设置环境变量 DIRECTOR_API_KEY，"
            "或在本目录创建 .env（参考 .env.example）。"
        )
    api_base = os.environ.get("DIRECTOR_API_BASE", DEFAULT_API_BASE)
    model = args.model or os.environ.get("DIRECTOR_MODEL", DEFAULT_MODEL)
    n = max(1, math.ceil(args.duration / 10))
    prompt = STORYBOARD_USER_TMPL.format(n=n, duration=args.duration, story=args.story)
    content = call_chat_api(
        api_key, api_base, model,
        [{"role": "system", "content": STORYBOARD_SYSTEM},
         {"role": "user", "content": prompt}],
    )
    header = (
        f"# 分镜表\n\n- 故事：{args.story}\n- 目标时长：{args.duration} 秒"
        f"（{n} 段 × 10 秒）\n- 模型：{model}\n\n"
    )
    out = header + content.strip() + "\n"
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"已写入 {args.output}")
    else:
        print(out)
    return 0


# ---------------------------------------------------------------- 功能 2：色卡检索
def load_catalog(path):
    """解析色卡库 Markdown（复用库文件内置检索器的解析逻辑）。"""
    text = Path(path).read_text(encoding="utf-8")
    body = text.split("\n<!-- FRAMEFORGE_CATALOG_BEGIN -->\n", 1)[1] \
               .split("\n<!-- FRAMEFORGE_CATALOG_END -->", 1)[0]
    cards = []
    for line in body.splitlines():
        if not re.match(r"^\| \d+ \| ", line):
            continue
        x = [html.unescape(t.strip()) for t in line.strip().strip("|").split("|")]
        nums = [json.loads(v) for v in x[11].split(",")]
        if len(x) != 14 or len(nums) != 11:
            raise ValueError("色卡行格式错误")
        tones = dict(re.findall(r"([SMH])=(#[0-9A-Fa-f]{6})", x[12]))
        cards.append(dict(
            index=int(x[0]), id=x[1], director=x[2], director_en=x[3],
            film=x[4], film_en=x[5], year=int(x[6]), era=x[7],
            tags=x[8].split(" / "), palette=x[9].split(","),
            recipe=x[10], grade=dict(zip(GRADE_KEYS, nums)),
            tone_roles={k: tones[k] for k in ("S", "M", "H") if k in tones},
            lighting=x[13],
        ))
    return cards


def search_cards(cards, term, limit=8):
    """复用库内检索器逻辑：精确 ID > 编号 > 多关键词同时匹配。"""
    q = term.strip().casefold()
    exact = [c for c in cards if c["id"].casefold() == q]
    if exact:
        return exact
    number = re.fullmatch(r"(?:编号\s*|#)?(\d+)", q)
    if number:
        return [c for c in cards if c["index"] == int(number.group(1))]
    tokens = q.split()
    result = []
    for c in cards:
        hay = " ".join([c["id"], c["director"], c["director_en"], c["film"],
                        c["film_en"], c["era"], *c["tags"], c["lighting"]]).casefold()
        if all(t in hay for t in tokens):
            result.append(c)
    return result[: max(1, min(12, limit))]


def format_card(c):
    lines = [
        f"## 主卡：编号 {c['index']}｜{c['id']}｜{c['film']}（{c['director']}，{c['year']}）",
        "",
        "- 标签：" + " / ".join(c["tags"]),
        "- 六色色板：" + "、".join(c["palette"]),
    ]
    if c["tone_roles"]:
        role = "、".join(f"{k}={v}" for k, v in c["tone_roles"].items())
        lines.append(f"- 分区目标（暗部/中间调/高光）：{role}")
    lines.append("- 11 项参数（FrameForge 原始刻度）：")
    lines.append("")
    lines.append("| 参数 | 值 |")
    lines.append("| --- | --- |")
    for k in GRADE_KEYS:
        lines.append(f"| {k} | {c['grade'][k]} |")
    if c["lighting"]:
        lines += ["", f"- 布光方案：{c['lighting']}"]
    return "\n".join(lines)


def cmd_color(args):
    catalog = args.catalog or DEFAULT_CATALOG
    if not Path(catalog).is_file():
        raise SystemExit(f"色卡库文件不存在：{catalog}")
    cards = load_catalog(catalog)
    rows = search_cards(cards, args.keyword, args.limit)
    if not rows:
        print(f"色卡库（共 {len(cards)} 张）里没有匹配「{args.keyword}」的卡，换个关键词试试。")
        return 0
    out = [f"# 色卡检索：{args.keyword}\n", format_card(rows[0])]
    if len(rows) > 1:
        out.append("\n## 备选")
        for c in rows[1:]:
            out.append(f"- 编号 {c['index']}｜{c['id']}｜{c['film']}（{c['director']}）"
                       f"｜色板 {'、'.join(c['palette'])}")
    text = "\n".join(out) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"已写入 {args.output}")
    else:
        print(text)
    return 0


# ---------------------------------------------------------------- 功能 3：拼接命令导出
def cmd_stitch(args):
    segs = [args.pattern.format(i=i) for i in range(1, args.segments + 1)]
    parts = ["bash", "scripts/stitch_grade.sh"]
    if args.raw:
        parts.append("--raw")
    parts.append(args.output)
    parts.extend(segs)
    cmd = " ".join(parts)
    note = ("（--raw：只拼接重编码、不动颜色，用于提示词已指定色调风格的片子）"
            if args.raw else
            "（默认：拼接并统一套电影色调＋轻微暗角）")
    text = (f"# 拼接命令（{args.segments} 段）\n\n```bash\n{cmd}\n```\n\n{note}\n"
            f"预期成片总时长 ≈ {args.segments * 10} 秒，运行后脚本会回读实际时长核对。\n")
    if args.save:
        Path(args.save).write_text(text, encoding="utf-8")
        print(f"已写入 {args.save}")
    else:
        print(text)
    return 0


# ---------------------------------------------------------------- 入口
def main(argv=None):
    p = argparse.ArgumentParser(
        prog="director.py",
        description="短片导演助手：分镜生成（API）＋色卡检索（本地）＋拼接命令导出",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("storyboard", help="输入一句话故事，调 API 生成分镜表")
    sp.add_argument("story", help="一句话故事")
    sp.add_argument("--duration", type=int, default=30, help="目标总时长（秒），默认 30")
    sp.add_argument("--model", default=None, help="模型名，默认读 DIRECTOR_MODEL 或 spark-x2.6")
    sp.add_argument("--output", "-o", default=None, help="把结果写入该 Markdown 文件")
    sp.set_defaults(func=cmd_storyboard)

    cp = sub.add_parser("color", help="本地检索 1200 张导演色卡")
    cp.add_argument("keyword", help="关键词，如：雨夜 / 王家卫 / 编号235 / 精确ID")
    cp.add_argument("--limit", type=int, default=8, help="最多返回候选数，默认 8")
    cp.add_argument("--catalog", default=None, help="色卡库路径，默认 references/frameforge_color_cards.md")
    cp.add_argument("--output", "-o", default=None, help="把结果写入该 Markdown 文件")
    cp.set_defaults(func=cmd_color)

    tp = sub.add_parser("stitch", help="按段数导出 stitch_grade.sh 拼接命令")
    tp.add_argument("--segments", type=int, required=True, help="分镜段数")
    tp.add_argument("--raw", action="store_true", help="只拼接不动颜色")
    tp.add_argument("--output", default="final.mp4", help="成片文件名，默认 final.mp4")
    tp.add_argument("--pattern", default="seg{i}.mp4", help="片段命名模板，默认 seg{i}.mp4")
    tp.add_argument("--save", default=None, help="把命令说明写入该 Markdown 文件")
    tp.set_defaults(func=cmd_stitch)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
