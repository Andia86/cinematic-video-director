# Cinematic Video Director

A ready-to-run AI pre-production toolkit for short films. Give it a one-line story and it helps you break the story into a shot-by-shot storyboard, choose a cinematic color grade, and prepare the ffmpeg stitching command. The core is `director.py`, a zero-dependency Python command-line application. The companion `SKILL.md` captures the film-director methodology as an Agent Skill: the application executes, the Skill encodes the directorial workflow.

## Features

### 1. Storyboard generation (LLM API)

Provide a one-line story and a target duration. The tool splits the story into 10-second segments (rounding up) and asks an OpenAI-compatible chat model for a Markdown storyboard. Each row includes the plot, shot size, primary camera move, start frame, end frame, and color-tone notes.

The built-in storyboard rules are part of the methodology:

- Each segment carries one action or one emotional turn.
- The end frame of a segment should connect to the start frame of the next one.
- Characters, costumes, and locations stay consistent across segments.
- Multi-person scenes are limited to standoff, solo performance, or training-oriented action, not person-to-person fighting.

```bash
python3 director.py storyboard \
  "A martial-arts heroine practices swordplay alone in a bamboo forest at dawn, from opening stance through sword flowers to closing stance" \
  --duration 30 -o storyboard.md
```

A real generated example is available at [examples/storyboard_example.md](examples/storyboard_example.md) (generated with iFlytek Spark `spark-x2.6`).

### 2. Color card search (local, no API call)

The repository bundles a library of 1,200 FrameForge director color cards. Search by keyword, director, film title, card number, or exact card ID. The result shows the main card's number, ID, six-color HEX palette, and all 11 grading parameters, including `skinProtect` and `lookStrength`. Alternative cards are listed as well.

```bash
python3 director.py color "Wong Kar-wai"
python3 director.py color "Blade Runner"
python3 director.py color "#235"
python3 director.py color "original-y181-200"
```

Search behavior:

- Exact card ID first, then card number, then multi-keyword matching.
- Keywords use AND matching: every token must match the card's searchable text.
- `--limit` defaults to 8 candidates and is capped at 12.
- `--catalog` points to a different color-card library if needed.
- `-o/--output` writes the result to a Markdown file.

A real search result is available at [examples/color_card_example.md](examples/color_card_example.md) (keyword "雨夜", meaning "rainy night").

### 3. Stitch command export (ffmpeg grade and concat)

Generate the invocation of `scripts/stitch_grade.sh` for a given number of segments. By default the script stitches the clips and applies a unified cinematic grade (teal-orange look with a subtle vignette). With `--raw`, it only concatenates and re-encodes without changing the color, which is useful when the prompts already define the color style.

```bash
python3 director.py stitch --segments 3
# Output:
# bash scripts/stitch_grade.sh final.mp4 seg1.mp4 seg2.mp4 seg3.mp4

bash scripts/stitch_grade.sh final.mp4 seg1.mp4 seg2.mp4 seg3.mp4   # Run the actual stitch
```

Options:

- `--segments` (required): number of storyboard segments.
- `--output`: output file name, default `final.mp4`.
- `--pattern`: segment naming template, default `seg{i}.mp4`.
- `--raw`: concatenate and re-encode only, without color grading.
- `--save`: write the generated command and notes to a Markdown file.

`director.py` only exports the command. The actual ffmpeg work is done by `scripts/stitch_grade.sh`, which requires `ffmpeg` and `ffprobe` on your system. Output and segment file names are shell-quoted, so names containing spaces or special characters remain safe to run.

## Installation

Requirements:

- Python 3.9 or newer.
- No third-party Python packages. The application uses only the standard library.
- `ffmpeg` and `ffprobe` for the stitching script and frame extraction.
- An OpenAI-compatible LLM API key for storyboard generation. Color search and stitch-command export work offline.

```bash
git clone https://github.com/Andia86/cinematic-video-director.git
cd cinematic-video-director
```

## Configuration

The API key is read only from environment variables or a local `.env` file. No real key is stored in the repository.

```bash
cp .env.example .env
# Edit .env and replace DIRECTOR_API_KEY with your own key.

# Or export the variables directly:
export DIRECTOR_API_KEY=your_key
export DIRECTOR_API_BASE=https://maas-api.cn-huabei-1.xf-yun.com/v2   # default: iFlytek Spark
export DIRECTOR_MODEL=spark-x2.6
```

The endpoint is an OpenAI-compatible `/chat/completions` API. Set `DIRECTOR_API_BASE` and `DIRECTOR_MODEL` to any compatible service.

Environment variables already set in the shell take precedence over values in `.env`. The tool looks for `.env` in the current working directory first, then in the project root.

## Usage examples

Generate a storyboard:

```bash
python3 director.py storyboard "A courier crosses a rain-soaked neon city at night" --duration 30 -o storyboard.md
```

Search the local color-card library:

```bash
python3 director.py color "Fincher"
python3 director.py color "Fincher" --limit 5
python3 director.py color "#25" -o card.md
```

Export a stitch command:

```bash
python3 director.py stitch --segments 3
python3 director.py stitch --segments 3 --raw
python3 director.py stitch --segments 3 --output "final cut.mp4" --save stitch.md
```

## Tests

The test suite lives in `tests/test_director.py` and uses only the Python standard library `unittest` and `unittest.mock`. It contains 67 unit tests, all passing.

```bash
python3 -m unittest discover -s tests
```

The tests cover:

- Empty keywords and invalid argument boundaries.
- Color-card search: exact matches, empty results, and result limits.
- Stitch command generation, including `shlex` quoting and invalid templates.
- Segment-count calculation and mock API scenarios: success, non-JSON response, HTTP error, and missing API key.
- `load_catalog` failures: missing markers, insufficient columns, and CRLF input.
- `.env` loading: BOM handling and empty keys.

## Project structure

```text
cinematic-video-director/
├── director.py                     # CLI application (storyboard / color / stitch)
├── .env.example                    # API key configuration template
├── SKILL.md                        # Methodology Skill: storyboard → continuation → grade → stitch
├── skill.yaml                      # Skill metadata
├── README.md                       # Chinese README
├── README_EN.md                    # English README
├── scripts/
│   └── stitch_grade.sh             # ffmpeg concat and unified grade script
├── references/
│   └── frameforge_color_cards.md   # 1,200 director color cards and search notes
├── examples/
│   ├── storyboard_example.md       # Generated storyboard example
│   └── color_card_example.md       # Color-card search example
└── tests/
    └── test_director.py            # Standard-library unittest suite (67 tests)
```

## License

MIT. See [LICENSE](LICENSE).

The color-card library is compiled from FrameForge V2.6 data. Film titles and author names are used only to search for visual inspiration; they are not claimed to be official studio LUTs.
