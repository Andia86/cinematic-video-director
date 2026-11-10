# 短片导演助手 · Cinematic Video Director

一个能直接跑起来的 AI 短片前期工具：给一句话故事，它帮你拆分镜、定色调、备好拼接命令。主体是零第三方依赖的 Python 命令行应用 `director.py`，配套一份完整的「电影短片导演」方法论 Skill（`SKILL.md`）——应用负责执行，Skill 负责把导演经验固化成流程。

## 功能

### 1. 分镜生成（调大模型 API）

输入一句话故事和目标时长，按每段 10 秒拆成分镜表：每段含剧情、景别、主运镜、起幅、落幅、色调口径，输出 Markdown 表格。分镜规则内置了方法论的硬约束：每段只装一个动作或一次情绪转折、相邻段落幅接起幅、多人场面只做对峙/单人表演/训练向（不写人对人打斗）。

```bash
python3 director.py storyboard "一位功夫女侠清晨在竹林里独自练剑，从起势、剑花到收势" --duration 30 -o storyboard.md
```

真实输出示例：[examples/storyboard_example.md](examples/storyboard_example.md)（讯飞 Spark spark-x2.6 实测生成）

### 2. 色卡检索（本地，不调 API）

内置 1200 张 FrameForge 导演色卡库，按关键词、导演、片名、编号或精确 ID 检索，返回主卡的编号、ID、六个 HEX 色板和全部 11 项调色参数（含肤色保护 skinProtect、调色强度 lookStrength），另附备选卡。

```bash
python3 director.py color "雨夜"
python3 director.py color "王家卫"
python3 director.py color "编号235"
```

实测输出：[examples/color_card_example.md](examples/color_card_example.md)

### 3. 拼接命令导出

按分镜段数生成拼接脚本 `scripts/stitch_grade.sh` 的调用命令：默认拼接并统一套电影色调（青橙调＋轻微暗角）；加 `--raw` 只拼接重编码、不动颜色（提示词已指定色调风格时用）。

```bash
python3 director.py stitch --segments 3
# 输出：bash scripts/stitch_grade.sh final.mp4 seg1.mp4 seg2.mp4 seg3.mp4
bash scripts/stitch_grade.sh final.mp4 seg1.mp4 seg2.mp4 seg3.mp4   # 真正拼接
```

## 安装

只需要 Python 3.9+（仅用标准库，无需 pip 安装任何包）。拼接功能另需系统装有 `ffmpeg` / `ffprobe`。

```bash
git clone https://github.com/Andia86/cinematic-video-director.git
cd cinematic-video-director
```

## 配置 API Key

Key 只从环境变量或本地 `.env` 读取，仓库里不保存任何真实 Key：

```bash
cp .env.example .env   # 然后把 DIRECTOR_API_KEY 换成你自己的 Key
# 或直接 export：
export DIRECTOR_API_KEY=你的Key
export DIRECTOR_API_BASE=https://maas-api.cn-huabei-1.xf-yun.com/v2   # 默认讯飞 Spark
export DIRECTOR_MODEL=spark-x2.6
```

接口是 OpenAI 兼容的 `/chat/completions`，把 `DIRECTOR_API_BASE` / `DIRECTOR_MODEL` 换成任意兼容服务即可，不绑死一家。

## 设计说明（方法论 Skill）

`SKILL.md` 是配套的 Agent Skill，把短片生产固化成一条流水线：

**分镜拆分 → 逐段续拍 → 色卡定调 → 拼接调色**

核心特性：

- **正脸锚点**：参考图是三视图拼图时先裁出正脸特写作第一参考，只喂拼图会让生成模型只抓发色、雀斑这类类型特征，五官神似度明显更差。
- **尾帧锚点**：用 ffmpeg 抽上一段最后一帧作下一段首帧参考，上下文续拍管剧情人设，尾帧锚点管接缝处的构图、姿势、光线咬合。
- **色调一致性校准**：各段独立生成不锁白平衡与曝光，拼接前先并排比对抽帧，偏色段用 `colortemperature`＋`eq` 拉回基准段再进拼接。
- **1200 张导演色卡库**：`references/frameforge_color_cards.md`，每卡含六色色板与 11 项参数；选卡时库值与适配建议分开写，不编造 ID、HEX 或参数；落地 ffmpeg 时按语义近似换算，不声称逐像素一致。
- **外置调色面板理念**：调色不靠嘴说，靠用户自己动手拉的滑杆/按钮控制；其中**保护肤色（skinProtect）**与**调色强度（lookStrength）**是最优先的两个调节项——环境可以往冷里压，脸必须留在暖轴上。本仓库另有配套的「导演色卡调节面板」交互作品与之联动（面板本体不在本仓库内）。

三条质量红线：防人物错乱重复、防物体穿模、人物与场景一致性逐段抽帧验片，不过关的段单独重拍、不带瑕疵进拼接。

## 目录结构

```
cinematic-video-director/
├── director.py                     # 命令行应用主体（storyboard / color / stitch）
├── .env.example                    # Key 配置模板（真实 .env 不入库）
├── SKILL.md                        # 方法论 Skill：分镜→续拍→定调→拼接全流程
├── skill.yaml                      # Skill 元数据
├── scripts/
│   └── stitch_grade.sh             # ffmpeg 拼接＋统一调色脚本
├── references/
│   └── frameforge_color_cards.md   # 1200 张导演色卡库（含内置检索器说明）
└── examples/
    ├── storyboard_example.md       # 分镜生成实测输出（Spark spark-x2.6）
    └── color_card_example.md       # 色卡检索实测输出（关键词「雨夜」）
```

## 依赖

- Python 3.9+（标准库 `urllib` 调 API，无第三方包）
- ffmpeg / ffprobe（仅拼接与抽帧验片时需要）
- 一个 OpenAI 兼容的大模型 API Key（分镜生成功能需要；色卡检索与拼接导出离线可用）

## License

MIT，见 [LICENSE](LICENSE)。色卡库为 FrameForge V2.6 数据整理，电影名与作者名仅用于检索视觉灵感，不声称为片方官方 LUT。
