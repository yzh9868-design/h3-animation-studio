# H3 轻量动画工作室 · H3 Animation Studio

**从一个点子，做到可审阅的剧本、角色表演、分镜和中英 H3 提示词；确认后，用自己的 ComfyUI 工作流生成有声动画。**

[快速开始](#快速开始) · [AI自动配置 ComfyUI](#让ai自动配置-comfyui) · [单镜快修](#只改一个镜头) · [脚本入口](#脚本入口) · [English](#english)

![小兔捉迷藏：英语原声与中英字幕成片画面](examples/rabbit-hide-and-seek/frame-opening.png)

《小兔捉迷藏》是此前完成的约一分钟项目：小兔跑进森林找地方躲，蘑菇太小，藏进花丛后又忍不住打喷嚏。瓢虫找到它，小兔认真解释：“The flower has a cold.”

图中为实际成片画面。该项目包含英语原声及项目专用脚本制作的中英字幕。

## 这是做什么的

把创作和制作串起来的 AI Skill：你提供主题、受众、时长和参考，AI 写故事、设计表演、整理素材，交一份可以离线打开的 HTML 审阅包。

你确认后，再连接自己的 ComfyUI，逐段生成视频、保留 H3 原声，最后合成 MP4。已有镜头需要返工时，直接修改对应段落，复用其余内容。

- **角色从外形到表演一起设计**：性格、招牌动作、移动方式和允许的夸张变化共同参与剧情。
- **图像参考可以复用**：三视图、剪影、表情与动作整理成角色综合图，按故事需要取舍。
- **提示词可直接核对**：中文执行稿、英文 H3 稿和实际提交内容保持一致。
- **原生声画**：对白、环境声和动作声由 H3 同次生成；角色声线描述跨段复用。
- **ComfyUI 可选**：只做剧本、分镜或提示词时，可以先独立完成；需要视频时再配置。
- **AI自动接入**：提供服务地址与API工作流，AI完成导入、输入映射、连接设置和兼容检查，后续项目复用。
- **单镜快修**：已明确要求修复并重生成的镜头，直接更新、准备、提交，不重走整片创作审批。

适合动物动画、幼儿英语故事、角色喜剧，以及少角色、少场景的短片。对白、风格和故事结构由你的需求决定。

## 做法

| 阶段 | 做什么 | 交付 |
| --- | --- | --- |
| 理清故事 | 目标、角色选择、环境反馈、变化或笑点、结果 | 完整剧本与表演分镜 |
| 准备角色 | 外形、性格、声线、表情、动作与形态 | 可复用的角色和必要场景参考 |
| 写 H3 稿 | 把行动、镜头、原句对白和声音写进生成单元 | 完整中文与英文提示词 |
| 集中审阅 | 把剧本、分镜、实际素材和提示词放在一起 | `review/index.html` 与素材目录 |
| 确认后制作 | 准备、提交、查询、取回各段视频 | H3 原生声画镜头 |
| 合成与交付 | 按计划剪辑，保留各段原声 | MP4 与任务记录 |

首次提交前做一次联合检查。剧情与表演在写稿时收敛，不额外建立多轮复核表。

## 你需要

| 用途 | 准备 |
| --- | --- |
| 创作 | 能读取本地 Skill、编写文件并使用所需工具的 AI Agent |
| H3 提示词 | 单独安装、可被 Agent 读取的 `h3-prompt-writing` Skill |
| 参考图片 | Agent 可用的图像生成工具，或你提供的现有图片 |
| 运行脚本 | Python 3.10+；本仓库 Python 工具使用标准库 |
| 视频生成 | 自己的 ComfyUI 服务、H3 模型与所需自定义节点，以及匹配的 API 格式工作流 |
| 合成与媒体检查 | 可执行的 `ffmpeg` 和 `ffprobe` |

模型、图片服务和 GPU 资源由你的环境提供。ComfyUI 只安装了节点，不代表已经准备好完整、可运行的工作流。

## 安装成 Skill

[下载源码ZIP](https://github.com/yzh9868-design/h3-animation-studio/archive/refs/heads/main.zip)，解压后将文件夹命名为 `h3-animation-studio`；也可以克隆仓库：

```bash
git clone https://github.com/yzh9868-design/h3-animation-studio.git
```

将**整个 `h3-animation-studio` 文件夹**放进 Agent 的 Skill 目录，保留其中的 `scripts/`、`profiles/`、`references/` 和 `assets/`。

Codex 当前的标准本地目录如下；已有自定义 Skill 目录的环境继续使用原目录即可。[官方目录说明](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)

| 范围 | 目录 |
| --- | --- |
| 用户级 | `~/.agents/skills/h3-animation-studio/` |
| 仓库级 | `<项目根目录>/.agents/skills/h3-animation-studio/` |

Windows 的用户级目录对应 `%USERPROFILE%\.agents\skills\h3-animation-studio\`。

本仓库不包含 `h3-prompt-writing`；编写H3提示词前，请另行提供Agent可读取的该Skill目录。缺失时可先完成剧本、分镜及接口配置。安装完成后，在 Codex 中使用 `$h3-animation-studio`。其他 Agent 请按其 Skill 加载方式安装，并让它读取本目录的 [SKILL.md](SKILL.md)。

## 快速开始

先说清楚你想做什么：

> 使用 $h3-animation-studio，做一部约60秒的幼儿英语动画。
> 主角是小兔和瓢虫，在大森林里捉迷藏。
> 风格温暖、可爱，幽默靠身体动作和角色反应。
> 英语短句要清楚自然，先给我完整HTML审阅包。

AI 会整理剧本、角色及声线、表演分镜、必要参考素材与中英提示词。角色首次制作时，默认用一张综合图展示三视图、剪影、4–6种表情及3–4种动作；数量可裁减，已有素材直接复用。

打开项目里的 `review/index.html`，集中查看全部内容。确认后再说：

> 确认这份审阅包，使用已配置的工作流生成视频，完成后合成MP4。

也可以缩小范围：

> 只写剧本和分镜，先不生图、不生成视频。

> 这次只生成U01，其余镜头暂不提交。

一部约一分钟的短片会按行动和观看节奏拆成多个生成任务。任务长度由所选工作流决定，镜头不必等长。

## 让AI自动配置 ComfyUI

**推荐直接让AI按Skill完成接入。你提供地址和工作流，AI操作配置工具，无需自己编写映射JSON或逐条运行命令。** 配置只需在首次接入、切换工作流或相关环境变化时进行，后续镜头复用。

### 你只需提供

| 内容 | 示例或说明 |
| --- | --- |
| ComfyUI服务地址 | `http://127.0.0.1:8188`，也可以是可访问的局域网或远程服务 |
| API格式工作流JSON | 附加文件，或给AI可读取的本地文件路径 |
| 可选：认证环境变量名 | 服务需要认证时提供；密钥在本机设置，不写进公开文件 |

复制这段话，并附上工作流：

> 使用 $h3-animation-studio，帮我自动配置ComfyUI接口。  
> 服务地址是 http://127.0.0.1:8188，API工作流已附上。  
> 请读取Skill的配置说明，导入为my-h3并设为默认；自行识别和补齐能从工作流判断的输入输出映射。  
> 保留原模型、LoRA和采样设置，检查服务与节点兼容性，列出已接入工作流和服务API。  
> 最后告诉我哪些已配置、还有什么缺项；这次先不生成视频。

### AI会完成什么

| 步骤 | AI负责处理 |
| --- | --- |
| 读取与复用 | 读取Skill配置说明及已有本地配置，识别可复用工作流 |
| 导入与识别 | 保存上传API原件，识别提示词、参考素材、时长、尺寸、种子及声画输出绑定 |
| 补齐配置 | 根据原图连线及节点定义补映射，保存服务地址并选中本次工作流 |
| 检查兼容性 | 离线检查配置，再只读检查服务、节点及参数；不上传素材、不提交GPU任务 |
| 汇报与复用 | 列出工作流、服务接口、检查结果和真实缺项，后续生成直接调用 |

**自动配置由AI结合现有工具完成。** 脚本先推断常见H3 Ref2VA结构，AI处理有依据的映射补充；遇到无法从图和节点定义确定的事实，再集中询问，例如预期输出尺寸或模型素材上限。缺少节点、模型或当前适配不支持时，会明确指出，不能靠更换你的工作流来假装接入成功。

`my-api.json` 应是 ComfyUI 导出的 **API格式节点字典**。普通画布JSON里的 `nodes` 数组需要先在ComfyUI导出为API格式。只有节点列表、没有完整工作流时，AI会说明还缺什么。

### 后续直接用自然语言

> 列出当前已接入的工作流和ComfyUI服务API，说明各自支持什么。

> 使用my-h3生成已确认的动画，沿用现有连接，不重新配置。

> 换用我这次上传的新API工作流，另存为my-h3-v2；保留旧配置和原工作流参数。

详细操作与认证、映射说明见 [ComfyUI配置](references/comfy-configuration.md)。

<details>
<summary>手动配置命令（可选；也供AI调用）</summary>

在本 Skill 目录运行：

```bash
# 1. 导入API工作流，原文件保留
python scripts/comfy_setup.py import-workflow my-api.json --name my-h3

# 2. 设置连接并选中刚导入的工作流
python scripts/comfy_setup.py configure --url http://127.0.0.1:8188 --profile my-h3

# 3. 列出已登记的生成工作流与缺项
python scripts/comfy_setup.py list

# 4. 离线检查配置
python scripts/comfy_setup.py doctor --profile my-h3

# 5. 需要时只读检查服务器，不提交生成任务
python scripts/comfy_setup.py doctor --profile my-h3 --online
```

需要补映射时，由AI生成单独的配置JSON，使用 `import-workflow --mapping` 导入。宽高来自上游选择器的工作流，可声明预期输出尺寸，选择器原连线保持不变。

</details>

### 两种 API 列表

| 命令 | 列出的内容 |
| --- | --- |
| `python scripts/comfy_setup.py list` | 已登记的完整生成工作流、模式、输入范围、输出、限制和检查状态 |
| `python scripts/comfy_setup.py apis` | ComfyUI服务接口，例如节点发现、上传、提交、队列、历史和文件下载 |

`offline_ready` 表示离线配置检查通过，`schema_compatible` 表示服务器节点和参数兼容。真实任务成功后，才能报告实跑成功。

### 你的工作流如何被使用

**上传的 API 是执行基准，原件保持不变。**

- 任务输入可以替换：提示词、媒体文件名、时长、输出命名，以及明确指定的尺寸和种子等。
- 参考图、音频加载节点及对应 H3 参考端口，可随本次素材数量动态增删、复用和绑定。
- 模型、LoRA名称与强度、采样器、优化设置、时长公式、分辨率选择器及原生声画主干保留。
- 准备和提交阶段由程序检查差异，拦截输入适配范围之外的修改。

服务地址、私有工作流和检查记录保存在被 Git 忽略的 `local/`。认证配置只记录环境变量名，凭据在运行时读取。

## 只改一个镜头

直接指出问题和保留范围：

> U04里瓢虫走路变成了蹦跳，改成双脚交替落地的小步走。
> 角色、场景、对白和运镜都保持，只修U04并重新生成。

AI 会就地修改对应中英提示词、同步报告、记录本次局部授权，然后使用现有执行器重新生成该镜。其他未受影响镜头继续有效，旧片保留。

只有实际依赖前段末帧、共用素材或故事结果的后续镜头，才会被列为相关影响范围；扩大重生成范围需要对应指令。

只要求“分析问题”或“改文案”时，完成对应工作即可，不提交 GPU 任务。

## 脚本入口

平时可以让 AI 调用这些工具；项目内容统一保存在 `film.json`，无需用户手填。

| 工具 | 用途 |
| --- | --- |
| `scripts/comfy_setup.py` | 配置连接、导入工作流、查看清单和检查配置 |
| `scripts/report.py` | 渲染HTML、记录首次确认、同步单镜快修 |
| `scripts/comfy_run.py` | 规划、准备、提交、查询、取回与合成 |
| `scripts/workflow_adapter.py` | 按配置绑定输入，保护工作流生成主干 |

<details>
<summary>查看首次制作与单镜返工的命令示例</summary>

下列命令在 Skill 目录执行，`my-animation` 替换为已有项目目录。确认原话应来自用户的真实指令。

```bash
# 首次制作：离线规划、渲染审阅包
python scripts/comfy_run.py inspect --project "my-animation"
python scripts/report.py render --project "my-animation"

# 用户实际确认审阅包后
python scripts/report.py approve --project "my-animation" --user-confirmation "确认这份审阅包，开始生成"

# 按需对各段执行
python scripts/comfy_run.py prepare --project "my-animation" --segment U01
python scripts/comfy_run.py submit --project "my-animation" --segment U01 --execute
python scripts/comfy_run.py status --project "my-animation" --remote

# 任务完成后取回；全部所需段落下载后再合成
python scripts/comfy_run.py collect --project "my-animation" --segment U01
python scripts/comfy_run.py assemble --project "my-animation" --output output/film.mp4
```

已完成镜头需要重新生成时，先修改该段内容，再记录真实局部指令：

```bash
python scripts/report.py repair --project "my-animation" --segments U04 --user-confirmation "修好U04的走路动作并重新生成，其他段不动"
python scripts/comfy_run.py prepare --project "my-animation" --segment U04 --new-take
python scripts/comfy_run.py submit --project "my-animation" --segment U04 --execute
```

`--new-take` 归档已完成或明确失败的旧版本。在途或提交结果不确定的任务先查询状态，避免重复提交。

</details>

## 当前支持范围

| 项目 | 当前情况 |
| --- | --- |
| 剧本与动画表演 | 支持原创故事、角色动作、对白、声音及摄影设计 |
| 参考图 | 通过Agent可用图像工具制作，或复用现有素材 |
| H3提示词 | 由 `h3-prompt-writing` 按实际模式编写 |
| 通用视频执行 | 当前为 **H3 Ref2VA**，支持图片与可选音频参考 |
| 其他H3模式 | 可写提示词；执行需要相应工作流及适配支持 |
| MP4合成 | 拼接已收取镜头，保留H3原生音轨 |
| 字幕 | 可按需求另行制作；当前 `assemble` 命令没有内置转写、翻译或字幕烧录功能 |
| 系列制作 | 可复用角色、声线与素材，尚无独立系列管理和已拍情节去重系统 |

声线文字描述用于指导生成，实际音色一致性与表演效果需要看生成结果。耗时取决于素材准备、模型速度和队列；单镜快修的文案与提交准备以3–5分钟为目标，推理和排队另计。

## 项目里会留下什么

```text
my-animation/
├── film.json                  # 剧本、角色、素材、分镜和最终提示词
├── assets/                    # 角色、场景等项目素材
├── review/
│   ├── index.html             # 完整离线审阅包
│   └── assets/                # 审阅包引用的素材副本
├── approval.json              # 按镜头记录的用户确认
├── execution/
│   ├── state.json             # 真实任务ID与状态
│   └── jobs/                  # 各镜头源图快照、提交JSON和源片
└── output/
    └── film.mp4               # 合成成片
```

每次任务自动保存实际提交的 API JSON，方便核对参数、定位问题和断线恢复。日常生成复用固定脚本；不必逐镜编写新的 Python 调用文件。

## 进一步阅读

- [Skill入口](SKILL.md)
- [剧本、角色表演与H3桥接](references/authoring.md)
- [ComfyUI配置与API目录](references/comfy-configuration.md)
- [视频执行与任务恢复](references/comfyui.md)
- [项目文件格式](references/project-format.md)

本README的呈现方式参考了 [AI 动画单元剧](https://github.com/10291124jcjc-dotcom/ai-anime-series)。本文示例图来自本项目；H3创作与执行流程以本仓库文档及代码为准。

## English

H3 Animation Studio is an AI skill for animated shorts. Start with an idea, develop the script, character performance, references and bilingual H3 prompts, then review the complete offline HTML package.

After approval, use your own ComfyUI API workflow to generate native audiovisual clips and assemble an MP4. Explicit shot-repair requests use a local revision path and preserve unaffected shots.

The executor currently supports H3 Ref2VA. Reference-image and audio loaders can adapt dynamically, while the model, LoRAs, sampler and native generation backbone remain protected. Connection settings and private workflows live under the Git-ignored `local/` directory. Models, image tools and the separate `h3-prompt-writing` skill are supplied by your environment.

To connect ComfyUI, give the agent your server URL and exported API workflow JSON. The agent reads the skill, imports the workflow, completes supported input mappings, selects the profile and checks compatibility. Manual CLI commands are optional; configuration checks do not submit generation jobs.
