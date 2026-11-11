#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""director.py 的单元测试。

仅使用 Python 标准库（unittest / unittest.mock），不引入任何第三方依赖。

运行：
    python3 -m unittest discover -s tests -v
"""

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import director  # noqa: E402  （必须先补齐 sys.path）


CATALOG_BEGIN = "<!-- FRAMEFORGE_CATALOG_BEGIN -->"
CATALOG_END = "<!-- FRAMEFORGE_CATALOG_END -->"
CATALOG_HEADER = (
    "| 编号 | ID | 作者 | Author | 名称 | Title | 年份 | 年代 | 标签 | 色板 | "
    "配方 | 参数 | 分区目标 | 布光 |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | "
    "--- | --- | --- |"
)


def _row(
    index=1,
    card_id="wes-grand-budapest",
    director_cn="韦斯·安德森",
    director_en="Wes Anderson",
    film="布达佩斯大饭店",
    film_en="The Grand Budapest Hotel",
    year="2014",
    era="2010年代",
    tags="粉彩复古 / 复古",
    palette="#2B1B2D,#7C3154,#D8899A,#F0C7B6,#B9C9A8,#F4E6C7",
    recipe="pastelRose",
    params="0.12,14,12,-12,8,-10,12,10,6,86,72",
    tones="S=#2B1B2D,M=#7C3154,H=#D8899A",
    lighting="低调顶光",
):
    """构造一行合法的 14 列色卡表格行。"""
    cells = [
        index, card_id, director_cn, director_en, film, film_en, year, era,
        tags, palette, recipe, params, tones, lighting,
    ]
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _catalog(rows):
    """把若干色卡行包装成带起止标记的完整色卡库文本。"""
    return "\n".join([CATALOG_BEGIN, CATALOG_HEADER, *rows, CATALOG_END]) + "\n"


def _capture_stdout():
    buf = io.StringIO()
    return contextlib.redirect_stdout(buf), buf


class _FakeResponse:
    """模拟 urllib.request.urlopen 的上下文管理器返回值。"""

    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DirectorTest(unittest.TestCase):
    """director.py 的单一测试类，覆盖全部公开函数与命令行入口。"""

    # ------------------------------------------------------------ 测试基础设施
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmp = Path(self._tmpdir.name)

    @contextlib.contextmanager
    def _chdir(self, path):
        old = os.getcwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(old)

    def _write_catalog(self, rows, name="catalog.md", encoding="utf-8"):
        path = self.tmp / name
        path.write_text(_catalog(rows), encoding=encoding)
        return path

    def _card(self, index=1, card_id="wes-grand-budapest", tags=None,
              tone_roles=None, lighting="", palette=None):
        return {
            "index": index,
            "id": card_id,
            "director": "韦斯·安德森",
            "director_en": "Wes Anderson",
            "film": "布达佩斯大饭店",
            "film_en": "The Grand Budapest Hotel",
            "year": 2014,
            "era": "2010年代",
            "tags": list(tags if tags is not None else ["粉彩复古", "复古"]),
            "palette": list(palette if palette is not None else ["#2B1B2D", "#7C3154"]),
            "recipe": "pastelRose",
            "grade": {k: i for i, k in enumerate(director.GRADE_KEYS)},
            "tone_roles": dict(tone_roles or {}),
            "lighting": lighting,
        }

    # ============================================================ load_catalog
    def test_load_catalog_parses_card_fields(self):
        path = self._write_catalog([
            _row(index=7, card_id="nolan-dark-knight", director_cn="诺兰 &amp; 团队",
                 year="2008", tags="钢蓝写实 / 都市夜景",
                 palette="#080D12,#182733,#304552,#6A7478,#A58C6B,#D3C7AD",
                 recipe="steelBlue", params="-0.12,-24,-3,22,-14,-18,-8,2,12,82,78",
                 tones="S=#080D12,H=#D3C7AD", lighting="低调侧光"),
        ])
        cards = director.load_catalog(path)

        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(card["index"], 7)
        self.assertEqual(card["id"], "nolan-dark-knight")
        self.assertEqual(card["director"], "诺兰 & 团队")
        self.assertEqual(card["director_en"], "Wes Anderson")
        self.assertEqual(card["film"], "布达佩斯大饭店")
        self.assertEqual(card["film_en"], "The Grand Budapest Hotel")
        self.assertEqual(card["year"], 2008)
        self.assertEqual(card["era"], "2010年代")
        self.assertEqual(card["tags"], ["钢蓝写实", "都市夜景"])
        self.assertEqual(card["palette"],
                         ["#080D12", "#182733", "#304552", "#6A7478", "#A58C6B", "#D3C7AD"])
        self.assertEqual(card["recipe"], "steelBlue")
        self.assertEqual(list(card["grade"].keys()), director.GRADE_KEYS)
        self.assertEqual(card["grade"]["exposure"], -0.12)
        self.assertEqual(card["grade"]["lookStrength"], 78)
        self.assertEqual(card["tone_roles"], {"S": "#080D12", "H": "#D3C7AD"})
        self.assertEqual(card["lighting"], "低调侧光")

    def test_load_catalog_accepts_crlf_line_endings(self):
        text = _catalog([_row(index=1), _row(index=2, card_id="wes-moonrise")])
        path = self.tmp / "crlf.md"
        path.write_text(text.replace("\n", "\r\n"), encoding="utf-8", newline="")

        cards = director.load_catalog(path)

        self.assertEqual([c["index"] for c in cards], [1, 2])
        self.assertEqual(cards[1]["id"], "wes-moonrise")

    def test_load_catalog_accepts_utf8_bom(self):
        path = self._write_catalog([_row(index=3, card_id="wes-french-dispatch")],
                                   name="bom.md", encoding="utf-8-sig")

        cards = director.load_catalog(path)

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["index"], 3)
        self.assertEqual(cards[0]["id"], "wes-french-dispatch")

    def test_load_catalog_rejects_missing_markers(self):
        path = self.tmp / "no_marker.md"
        path.write_text("\n".join([CATALOG_HEADER, _row()]) + "\n", encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            director.load_catalog(path)
        self.assertIn("起止标记", str(ctx.exception))

    def test_load_catalog_rejects_markers_out_of_order(self):
        path = self.tmp / "reversed.md"
        path.write_text(
            "\n".join([CATALOG_END, CATALOG_HEADER, _row(), CATALOG_BEGIN]) + "\n",
            encoding="utf-8",
        )

        with self.assertRaises(ValueError) as ctx:
            director.load_catalog(path)
        self.assertIn("起止标记", str(ctx.exception))

    def test_load_catalog_rejects_short_row(self):
        cells = _row().strip().strip("|").split("|")
        short_row = "| " + " | ".join(c.strip() for c in cells[:-1]) + " |"
        self.assertNotEqual(short_row, _row())
        path = self._write_catalog([short_row])

        with self.assertRaises(ValueError) as ctx:
            director.load_catalog(path)
        self.assertIn("期望 14 列", str(ctx.exception))
        self.assertIn("实际 13 列", str(ctx.exception))

    def test_load_catalog_rejects_bad_param_json(self):
        path = self._write_catalog([_row(params="not-json")])

        with self.assertRaises(ValueError) as ctx:
            director.load_catalog(path)
        self.assertIn("参数列解析失败", str(ctx.exception))

    def test_load_catalog_rejects_wrong_param_count(self):
        path = self._write_catalog([_row(params="1,2,3")])

        with self.assertRaises(ValueError) as ctx:
            director.load_catalog(path)
        self.assertIn("期望 11", str(ctx.exception))
        self.assertIn("实际 3", str(ctx.exception))

    def test_load_catalog_rejects_bad_year(self):
        path = self._write_catalog([_row(year="20x4")])

        with self.assertRaises(ValueError) as ctx:
            director.load_catalog(path)
        self.assertIn("年份非法", str(ctx.exception))
        self.assertIn("20x4", str(ctx.exception))

    def test_load_catalog_rejects_empty_catalog(self):
        path = self._write_catalog([])

        with self.assertRaises(ValueError) as ctx:
            director.load_catalog(path)
        self.assertIn("色卡库为空", str(ctx.exception))

    # ============================================================ search_cards
    def test_search_cards_empty_term_returns_empty(self):
        self.assertEqual(director.search_cards([self._card()], ""), [])

    def test_search_cards_whitespace_term_returns_empty(self):
        self.assertEqual(director.search_cards([self._card()], "   \t "), [])

    def test_search_cards_exact_id_is_case_insensitive(self):
        cards = [self._card(1, "Wes-Grand-Budapest"), self._card(2, "wes-moonrise")]

        rows = director.search_cards(cards, "wes-grand-budapest")

        self.assertEqual([c["index"] for c in rows], [1])

    def test_search_cards_by_number_variants(self):
        cards = [self._card(1, "a"), self._card(2, "b")]

        for term in ("2", "#2", "编号2", "编号 2"):
            with self.subTest(term=term):
                rows = director.search_cards(cards, term)
                self.assertEqual([c["index"] for c in rows], [2])

    def test_search_cards_requires_all_tokens(self):
        cards = [
            self._card(1, "wes-grand-budapest", tags=["粉彩复古", "复古"]),
            self._card(2, "nolan-dark-knight", tags=["钢蓝", "夜景"]),
        ]

        rows = director.search_cards(cards, "wes 复古")

        self.assertEqual([c["index"] for c in rows], [1])

    def test_search_cards_no_match_returns_empty(self):
        self.assertEqual(director.search_cards([self._card()], "根本不存在的关键词"), [])

    def test_search_cards_limit_is_capped_at_max(self):
        cards = [self._card(i, "card-%d" % i, tags=["common"]) for i in range(1, 16)]

        self.assertEqual(len(director.search_cards(cards, "common", limit=100)),
                         director.MAX_SEARCH_RESULTS)
        self.assertEqual(len(director.search_cards(cards, "common")), 8)

    def test_search_cards_limit_zero_is_clamped_to_one(self):
        cards = [self._card(i, "card-%d" % i, tags=["common"]) for i in range(1, 4)]

        for limit in (0, -5):
            with self.subTest(limit=limit):
                self.assertEqual(len(director.search_cards(cards, "common", limit=limit)), 1)

    # ============================================================ format_card
    def test_format_card_renders_all_sections(self):
        card = self._card(tone_roles={"S": "#111111", "M": "#222222", "H": "#333333"},
                          lighting="顶光 + 侧逆光")

        text = director.format_card(card)

        self.assertIn("## 主卡：编号 1｜wes-grand-budapest｜布达佩斯大饭店（韦斯·安德森，2014）", text)
        self.assertIn("- 标签：粉彩复古 / 复古", text)
        self.assertIn("- 六色色板：#2B1B2D、#7C3154", text)
        self.assertIn("- 分区目标（暗部/中间调/高光）：S=#111111、M=#222222、H=#333333", text)
        self.assertIn("| exposure | 0 |", text)
        self.assertIn("| lookStrength | 10 |", text)
        self.assertIn("- 布光方案：顶光 + 侧逆光", text)

    def test_format_card_omits_optional_sections_when_absent(self):
        text = director.format_card(self._card(tone_roles={}, lighting=""))

        self.assertNotIn("分区目标", text)
        self.assertNotIn("布光方案", text)
        self.assertIn("| 参数 | 值 |", text)

    # ============================================================ cmd_color
    def test_cmd_color_empty_keyword_reports_no_match(self):
        path = self._write_catalog([_row(index=1), _row(index=2, card_id="wes-moonrise")])
        args = argparse.Namespace(keyword="", limit=8, catalog=str(path), output=None)

        redirect, buf = _capture_stdout()
        with redirect:
            code = director.cmd_color(args)

        self.assertEqual(code, 0)
        self.assertIn("共 2 张", buf.getvalue())
        self.assertIn("没有匹配", buf.getvalue())

    def test_cmd_color_prints_primary_and_alternatives(self):
        path = self._write_catalog([
            _row(index=1, card_id="wes-one"),
            _row(index=2, card_id="wes-two", film="月升王国"),
            _row(index=3, card_id="wes-three", film="法兰西特派"),
        ])
        args = argparse.Namespace(keyword="wes", limit=8, catalog=str(path), output=None)

        redirect, buf = _capture_stdout()
        with redirect:
            code = director.cmd_color(args)

        out = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("# 色卡检索：wes", out)
        self.assertIn("## 主卡：编号 1｜wes-one", out)
        self.assertIn("## 备选", out)
        self.assertIn("编号 2｜wes-two", out)
        self.assertIn("编号 3｜wes-three", out)

    def test_cmd_color_limit_one_omits_alternatives(self):
        path = self._write_catalog([
            _row(index=1, card_id="wes-one"),
            _row(index=2, card_id="wes-two"),
        ])
        args = argparse.Namespace(keyword="wes", limit=1, catalog=str(path), output=None)

        redirect, buf = _capture_stdout()
        with redirect:
            director.cmd_color(args)

        self.assertIn("## 主卡：编号 1", buf.getvalue())
        self.assertNotIn("## 备选", buf.getvalue())

    def test_cmd_color_missing_catalog_file(self):
        args = argparse.Namespace(keyword="wes", limit=8,
                                  catalog=str(self.tmp / "missing.md"), output=None)

        with self.assertRaises(SystemExit) as ctx:
            director.cmd_color(args)
        self.assertIn("色卡库文件不存在", str(ctx.exception))

    def test_cmd_color_invalid_catalog(self):
        path = self.tmp / "broken.md"
        path.write_text("没有标记的色卡库\n", encoding="utf-8")
        args = argparse.Namespace(keyword="wes", limit=8, catalog=str(path), output=None)

        with self.assertRaises(SystemExit) as ctx:
            director.cmd_color(args)
        self.assertIn("色卡库读取失败", str(ctx.exception))
        self.assertIn("起止标记", str(ctx.exception))

    def test_cmd_color_writes_output_file(self):
        path = self._write_catalog([_row(index=1, card_id="wes-one")])
        out_file = self.tmp / "color.md"
        args = argparse.Namespace(keyword="wes-one", limit=8, catalog=str(path),
                                  output=str(out_file))

        redirect, buf = _capture_stdout()
        with redirect:
            code = director.cmd_color(args)

        self.assertEqual(code, 0)
        self.assertIn("已写入 {}".format(out_file), buf.getvalue())
        self.assertIn("# 色卡检索：wes-one", out_file.read_text(encoding="utf-8"))

    # ============================================================ cmd_stitch
    def test_cmd_stitch_builds_command(self):
        args = argparse.Namespace(segments=2, output="final.mp4", pattern="seg{i}.mp4",
                                  raw=False, save=None)

        redirect, buf = _capture_stdout()
        with redirect:
            code = director.cmd_stitch(args)

        out = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("```bash\nbash scripts/stitch_grade.sh final.mp4 seg1.mp4 seg2.mp4\n```", out)
        self.assertIn("预期成片总时长 ≈ 20 秒", out)
        self.assertIn("默认：拼接并统一套电影色调", out)

    def test_cmd_stitch_quotes_values_with_spaces(self):
        args = argparse.Namespace(segments=2, output="final cut.mp4",
                                  pattern="seg {i}.mp4", raw=False, save=None)

        redirect, buf = _capture_stdout()
        with redirect:
            director.cmd_stitch(args)

        out = buf.getvalue()
        self.assertIn(
            "bash scripts/stitch_grade.sh 'final cut.mp4' 'seg 1.mp4' 'seg 2.mp4'", out)

    def test_cmd_stitch_raw_flag_and_note(self):
        args = argparse.Namespace(segments=1, output="out.mp4", pattern="s{i}.mp4",
                                  raw=True, save=None)

        redirect, buf = _capture_stdout()
        with redirect:
            director.cmd_stitch(args)

        out = buf.getvalue()
        self.assertIn("bash scripts/stitch_grade.sh --raw out.mp4 s1.mp4", out)
        self.assertIn("--raw：只拼接重编码", out)
        self.assertIn("≈ 10 秒", out)

    def test_cmd_stitch_rejects_invalid_segment_count(self):
        for segments in (0, -1):
            with self.subTest(segments=segments):
                args = argparse.Namespace(segments=segments, output="out.mp4",
                                          pattern="seg{i}.mp4", raw=False, save=None)
                with self.assertRaises(SystemExit) as ctx:
                    director.cmd_stitch(args)
                self.assertIn("--segments 必须 >= 1", str(ctx.exception))

    def test_cmd_stitch_rejects_empty_output(self):
        args = argparse.Namespace(segments=1, output="", pattern="seg{i}.mp4",
                                  raw=False, save=None)

        with self.assertRaises(SystemExit) as ctx:
            director.cmd_stitch(args)
        self.assertIn("--output 不能为空", str(ctx.exception))

    def test_cmd_stitch_rejects_empty_pattern(self):
        args = argparse.Namespace(segments=1, output="out.mp4", pattern="",
                                  raw=False, save=None)

        with self.assertRaises(SystemExit) as ctx:
            director.cmd_stitch(args)
        self.assertIn("--pattern 不能为空", str(ctx.exception))

    def test_cmd_stitch_rejects_invalid_templates(self):
        for pattern in ("seg{j}.mp4", "seg{i.mp4", "seg{}.mp4"):
            with self.subTest(pattern=pattern):
                args = argparse.Namespace(segments=1, output="out.mp4", pattern=pattern,
                                          raw=False, save=None)
                with self.assertRaises(SystemExit) as ctx:
                    director.cmd_stitch(args)
                message = str(ctx.exception)
                self.assertIn("模板无效", message)
                self.assertIn(repr(pattern), message)

    def test_cmd_stitch_saves_file(self):
        save = self.tmp / "stitch.md"
        args = argparse.Namespace(segments=3, output="film.mp4", pattern="take{i}.mp4",
                                  raw=False, save=str(save))

        redirect, buf = _capture_stdout()
        with redirect:
            director.cmd_stitch(args)

        text = save.read_text(encoding="utf-8")
        self.assertIn("# 拼接命令（3 段）", text)
        self.assertIn("bash scripts/stitch_grade.sh film.mp4 take1.mp4 take2.mp4 take3.mp4", text)
        self.assertIn("≈ 30 秒", text)
        self.assertIn("已写入 {}".format(save), buf.getvalue())

    # ======================================================== cmd_storyboard
    def _storyboard_args(self, **overrides):
        params = {"story": "雨夜追逐", "duration": 30, "model": None, "output": None}
        params.update(overrides)
        return argparse.Namespace(**params)

    def test_cmd_storyboard_rejects_empty_story(self):
        for story in ("", "   "):
            with self.subTest(story=story):
                with self.assertRaises(SystemExit) as ctx:
                    director.cmd_storyboard(self._storyboard_args(story=story))
                self.assertIn("故事不能为空", str(ctx.exception))

    def test_cmd_storyboard_rejects_invalid_duration(self):
        for duration in (0, -10):
            with self.subTest(duration=duration):
                with self.assertRaises(SystemExit) as ctx:
                    director.cmd_storyboard(self._storyboard_args(duration=duration))
                self.assertIn("--duration 必须 >= 1 秒", str(ctx.exception))

    def test_cmd_storyboard_requires_api_key(self):
        with mock.patch.object(director, "load_dotenv"), \
                mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit) as ctx:
                director.cmd_storyboard(self._storyboard_args())
        message = str(ctx.exception)
        self.assertIn("未找到 API Key", message)
        self.assertIn("DIRECTOR_API_KEY", message)

    def test_cmd_storyboard_success_uses_env_and_writes_output(self):
        out_file = self.tmp / "storyboard.md"
        env = {
            "DIRECTOR_API_KEY": "secret-key",
            "DIRECTOR_API_BASE": "https://api.test/v1",
            "DIRECTOR_MODEL": "env-model",
        }
        with mock.patch.object(director, "load_dotenv") as load_dotenv, \
                mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(director, "call_chat_api",
                                  return_value="| 1 | 00:00-00:10 | 开场 |") as api:
            redirect, buf = _capture_stdout()
            with redirect:
                code = director.cmd_storyboard(
                    self._storyboard_args(duration=31, output=str(out_file)))

        self.assertEqual(code, 0)
        load_dotenv.assert_called_once_with()
        api.assert_called_once()
        api_key, api_base, model, messages = api.call_args.args
        self.assertEqual(api_key, "secret-key")
        self.assertEqual(api_base, "https://api.test/v1")
        self.assertEqual(model, "env-model")
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("10 秒分镜", messages[0]["content"])
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("正好 4 段", messages[1]["content"])
        self.assertIn("总时长 31 秒", messages[1]["content"])
        self.assertIn("故事：雨夜追逐", messages[1]["content"])

        text = out_file.read_text(encoding="utf-8")
        self.assertIn("# 分镜表", text)
        self.assertIn("- 目标时长：31 秒（4 段 × 10 秒）", text)
        self.assertIn("- 模型：env-model", text)
        self.assertIn("| 1 | 00:00-00:10 | 开场 |", text)
        self.assertIn("已写入 {}".format(out_file), buf.getvalue())

    def test_cmd_storyboard_segment_rounding_boundaries(self):
        cases = [(1, 1), (10, 1), (11, 2), (20, 2), (21, 3), (30, 3), (31, 4)]
        env = {"DIRECTOR_API_KEY": "secret-key"}

        for duration, expected in cases:
            with self.subTest(duration=duration):
                with mock.patch.object(director, "load_dotenv"), \
                        mock.patch.dict(os.environ, env, clear=True), \
                        mock.patch.object(director, "call_chat_api",
                                          return_value="ok") as api:
                    redirect, _ = _capture_stdout()
                    with redirect:
                        director.cmd_storyboard(
                            self._storyboard_args(story="故事", duration=duration))
                prompt = api.call_args.args[3][1]["content"]
                self.assertIn("正好 {} 段".format(expected), prompt)
                self.assertIn("总时长 {} 秒".format(duration), prompt)

    def test_cmd_storyboard_defaults_model_and_api_base(self):
        env = {"DIRECTOR_API_KEY": "secret-key"}
        with mock.patch.object(director, "load_dotenv"), \
                mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(director, "call_chat_api", return_value="ok") as api:
            redirect, buf = _capture_stdout()
            with redirect:
                director.cmd_storyboard(self._storyboard_args(duration=10))

        _, api_base, model, _ = api.call_args.args
        self.assertEqual(api_base, director.DEFAULT_API_BASE)
        self.assertEqual(model, director.DEFAULT_MODEL)
        self.assertIn("- 模型：{}".format(director.DEFAULT_MODEL), buf.getvalue())

    def test_cmd_storyboard_model_argument_overrides_env(self):
        env = {"DIRECTOR_API_KEY": "secret-key", "DIRECTOR_MODEL": "env-model"}
        with mock.patch.object(director, "load_dotenv"), \
                mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(director, "call_chat_api", return_value="ok") as api:
            redirect, _ = _capture_stdout()
            with redirect:
                director.cmd_storyboard(self._storyboard_args(model="arg-model"))

        self.assertEqual(api.call_args.args[2], "arg-model")

    # ============================================================ call_chat_api
    def test_call_chat_api_success_builds_request(self):
        body = json.dumps({"choices": [{"message": {"content": "分镜内容"}}]}).encode("utf-8")
        messages = [{"role": "user", "content": "hi"}]

        with mock.patch.object(director.urllib.request, "urlopen",
                               return_value=_FakeResponse(body)) as urlopen:
            content = director.call_chat_api("key-1", "https://api.test/v1/", "model-x",
                                             messages, timeout=7)

        self.assertEqual(content, "分镜内容")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.test/v1/chat/completions")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer key-1")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "model-x")
        self.assertEqual(payload["messages"], messages)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["temperature"], 0.7)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 7)

    def test_call_chat_api_appends_path_only_once(self):
        body = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode("utf-8")

        with mock.patch.object(director.urllib.request, "urlopen",
                               return_value=_FakeResponse(body)) as urlopen:
            director.call_chat_api("k", "https://api.test/v1/chat/completions", "m", [])

        self.assertEqual(urlopen.call_args.args[0].full_url,
                         "https://api.test/v1/chat/completions")

    def test_call_chat_api_rejects_invalid_base(self):
        for base in ("", "ftp://api.test/v1", "api.test/v1"):
            with self.subTest(base=base):
                with self.assertRaises(SystemExit) as ctx:
                    director.call_chat_api("k", base, "m", [])
                self.assertIn("API 地址无效", str(ctx.exception))

    def test_call_chat_api_http_error(self):
        error = urllib.error.HTTPError(
            "https://api.test/v1/chat/completions", 401, "Unauthorized", {},
            io.BytesIO(b'{"error":"invalid key"}'),
        )
        with mock.patch.object(director.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(SystemExit) as ctx:
                director.call_chat_api("k", "https://api.test/v1", "m", [])

        message = str(ctx.exception)
        self.assertIn("HTTP 401", message)
        self.assertIn("invalid key", message)

    def test_call_chat_api_network_error(self):
        with mock.patch.object(director.urllib.request, "urlopen",
                               side_effect=urllib.error.URLError("boom")):
            with self.assertRaises(SystemExit) as ctx:
                director.call_chat_api("k", "https://api.test/v1", "m", [])

        self.assertIn("网络", str(ctx.exception))
        self.assertIn("boom", str(ctx.exception))

    def test_call_chat_api_timeout(self):
        with mock.patch.object(director.urllib.request, "urlopen",
                               side_effect=TimeoutError("slow")):
            with self.assertRaises(SystemExit) as ctx:
                director.call_chat_api("k", "https://api.test/v1", "m", [], timeout=3)

        self.assertIn("超时", str(ctx.exception))
        self.assertIn("3s", str(ctx.exception))

    def test_call_chat_api_value_error(self):
        with mock.patch.object(director.urllib.request, "urlopen",
                               side_effect=ValueError("bad url")):
            with self.assertRaises(SystemExit) as ctx:
                director.call_chat_api("k", "https://api.test/v1", "m", [])

        self.assertIn("请求地址无效", str(ctx.exception))
        self.assertIn("bad url", str(ctx.exception))

    def test_call_chat_api_os_error(self):
        with mock.patch.object(director.urllib.request, "urlopen",
                               side_effect=OSError("disk")):
            with self.assertRaises(SystemExit) as ctx:
                director.call_chat_api("k", "https://api.test/v1", "m", [])

        self.assertIn("网络", str(ctx.exception))
        self.assertIn("disk", str(ctx.exception))

    def test_call_chat_api_non_json_response(self):
        with mock.patch.object(director.urllib.request, "urlopen",
                               return_value=_FakeResponse(b"<html>oops</html>")):
            with self.assertRaises(SystemExit) as ctx:
                director.call_chat_api("k", "https://api.test/v1", "m", [])

        self.assertIn("无法解析为 JSON", str(ctx.exception))

    def test_call_chat_api_invalid_utf8_response(self):
        with mock.patch.object(director.urllib.request, "urlopen",
                               return_value=_FakeResponse(b"\xff\xfe\xff")):
            with self.assertRaises(SystemExit) as ctx:
                director.call_chat_api("k", "https://api.test/v1", "m", [])

        self.assertIn("无法解析为 JSON", str(ctx.exception))

    def test_call_chat_api_bad_structure(self):
        for body in (b'{"choices": []}', b'{"choices": [{}]}', b"[]"):
            with self.subTest(body=body):
                with mock.patch.object(director.urllib.request, "urlopen",
                                       return_value=_FakeResponse(body)):
                    with self.assertRaises(SystemExit) as ctx:
                        director.call_chat_api("k", "https://api.test/v1", "m", [])
                self.assertIn("结构异常", str(ctx.exception))

    def test_call_chat_api_empty_content(self):
        for content in ("   ", 123, None):
            with self.subTest(content=content):
                body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
                with mock.patch.object(director.urllib.request, "urlopen",
                                       return_value=_FakeResponse(body)):
                    with self.assertRaises(SystemExit) as ctx:
                        director.call_chat_api("k", "https://api.test/v1", "m", [])
                self.assertIn("内容为空", str(ctx.exception))

    # ============================================================== load_dotenv
    def test_load_dotenv_loads_values_and_skips_invalid_lines(self):
        (self.tmp / ".env").write_text(
            "\ufeff# 注释\n\n=空键\nA1=v1\nB1='quoted'\nC1=\"double\"\n"
            "D1=  spaced  \n这一行没有等号\n",
            encoding="utf-8",
        )

        with mock.patch.dict(os.environ, {}, clear=True), self._chdir(self.tmp):
            director.load_dotenv()

            self.assertEqual(os.environ.get("A1"), "v1")
            self.assertEqual(os.environ.get("B1"), "quoted")
            self.assertEqual(os.environ.get("C1"), "double")
            self.assertEqual(os.environ.get("D1"), "spaced")
            self.assertNotIn("空键", os.environ)

    def test_load_dotenv_does_not_override_existing_values(self):
        (self.tmp / ".env").write_text("A1=file-value\n", encoding="utf-8")

        with mock.patch.dict(os.environ, {"A1": "keep-me"}, clear=True), \
                self._chdir(self.tmp):
            director.load_dotenv()

            self.assertEqual(os.environ["A1"], "keep-me")

    def test_load_dotenv_prefers_cwd_file(self):
        cwd_dir = self.tmp / "cwd"
        root_dir = self.tmp / "root"
        cwd_dir.mkdir()
        root_dir.mkdir()
        (cwd_dir / ".env").write_text("A=from-cwd\n", encoding="utf-8")
        (root_dir / ".env").write_text("A=from-root\nB=root-only\n", encoding="utf-8")

        with mock.patch.object(director, "ROOT", root_dir), \
                mock.patch.dict(os.environ, {}, clear=True), self._chdir(cwd_dir):
            director.load_dotenv()

            self.assertEqual(os.environ["A"], "from-cwd")
            self.assertNotIn("B", os.environ)

    def test_load_dotenv_without_file_is_noop(self):
        cwd_dir = self.tmp / "cwd"
        root_dir = self.tmp / "root"
        cwd_dir.mkdir()
        root_dir.mkdir()

        with mock.patch.object(director, "ROOT", root_dir), \
                mock.patch.dict(os.environ, {}, clear=True), self._chdir(cwd_dir):
            director.load_dotenv()

            self.assertEqual(dict(os.environ), {})

    def test_load_dotenv_read_os_error(self):
        (self.tmp / ".env").write_text("A=1\n", encoding="utf-8")

        with mock.patch.object(director, "ROOT", self.tmp / "root"), \
                mock.patch.object(Path, "read_text", side_effect=OSError("boom")), \
                mock.patch.dict(os.environ, {}, clear=True), self._chdir(self.tmp):
            with self.assertRaises(SystemExit) as ctx:
                director.load_dotenv()

        self.assertIn("读取", str(ctx.exception))
        self.assertIn("boom", str(ctx.exception))

    def test_load_dotenv_read_unicode_error(self):
        (self.tmp / ".env").write_text("A=1\n", encoding="utf-8")
        error = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

        with mock.patch.object(director, "ROOT", self.tmp / "root"), \
                mock.patch.object(Path, "read_text", side_effect=error), \
                mock.patch.dict(os.environ, {}, clear=True), self._chdir(self.tmp):
            with self.assertRaises(SystemExit) as ctx:
                director.load_dotenv()

        self.assertIn("不是有效的 UTF-8 文本", str(ctx.exception))

    # ======================================================= _write_or_print
    def test_write_or_print_prints_to_stdout(self):
        redirect, buf = _capture_stdout()
        with redirect:
            director._write_or_print("hello", None)

        self.assertEqual(buf.getvalue(), "hello\n")

    def test_write_or_print_writes_file(self):
        path = self.tmp / "out.md"
        redirect, buf = _capture_stdout()
        with redirect:
            director._write_or_print("hello", str(path))

        self.assertEqual(path.read_text(encoding="utf-8"), "hello")
        self.assertIn("已写入 {}".format(path), buf.getvalue())

    def test_write_or_print_failure_raises_system_exit(self):
        with self.assertRaises(SystemExit) as ctx:
            director._write_or_print("hello", str(self.tmp))

        self.assertIn("写入文件失败", str(ctx.exception))

    # ===================================================================== main
    def test_main_stitch_subcommand(self):
        redirect, buf = _capture_stdout()
        with redirect:
            code = director.main(["stitch", "--segments", "2", "--output", "out.mp4"])

        self.assertEqual(code, 0)
        self.assertIn("bash scripts/stitch_grade.sh out.mp4 seg1.mp4 seg2.mp4",
                      buf.getvalue())

    def test_main_color_subcommand(self):
        path = self._write_catalog([_row(index=1, card_id="wes-one")])
        redirect, buf = _capture_stdout()
        with redirect:
            code = director.main(["color", "wes", "--catalog", str(path)])

        self.assertEqual(code, 0)
        self.assertIn("# 色卡检索：wes", buf.getvalue())

    def test_main_requires_subcommand(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as ctx:
                director.main([])

        self.assertEqual(ctx.exception.code, 2)

    def test_load_dotenv_skips_key_rejected_by_os_environ(self):
        # 含 NUL 的键会让 os.environ.setdefault 抛 ValueError，应被跳过而不中断加载。
        (self.tmp / ".env").write_text("BAD\0KEY=bad\nOK1=fine\n", encoding="utf-8")

        with mock.patch.dict(os.environ, {}, clear=True), self._chdir(self.tmp):
            director.load_dotenv()

            self.assertEqual(os.environ.get("OK1"), "fine")
            self.assertFalse(any(k.startswith("BAD") for k in os.environ))

    def test_load_catalog_rejects_unterminated_row(self):
        # 行首是 "| 数字 | " 但结尾缺少竖线，应命中行格式检查而不是被静默跳过。
        path = self._write_catalog([_row()[:-2]])

        with self.assertRaises(ValueError) as ctx:
            director.load_catalog(path)
        self.assertIn("色卡行格式错误", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)