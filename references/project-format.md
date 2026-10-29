# 单一项目文件

Agent在用户项目目录写`film.json`，不要求用户手填。英文按`h3-prompt-writing`直接写入`prompt_en`，中文执行稿写入`prompt_zh`。脚本只展示和绑定，不重写提示词。

以下仅示意字段形状；应替换为实际创作内容，不当作完成品交付。

```json
{
  "title":"作品标题",
  "brief":"受众、风格、创作目标和已确认要求",
  "duration_seconds":60,
  "audio_mode":"h3_native",
  "script":"完整分场剧本、具体行动、对方回应及原句对白",
  "characters":[{
    "id":"A","name":"角色名","appearance":"稳定外观",
    "personality":"性格倾向，如何影响选择",
    "signature_actions":["能在故事中反复变化运用的招牌动作"],
    "locomotion":"移动与支撑方式",
    "deformation":"身体允许的夸张变化及程度",
    "voice":"年龄感、音域、音质、口音、语速、习惯"
  }],
  "assets":[{"id":"A_REF","kind":"image","path":"assets/A.png","role":"同一角色的外观、表情与关键姿势设定图；镜头按实际用途引用","prompt":"实际生图提示词"}],
  "segments":[{
    "id":"U01","mode":"Ref2VA","edit_seconds":7,"source_frames":175,
    "purpose":"本段推进的信息或行动",
    "shots":[{"id":"S01","duration_seconds":7,"action":"完整可见行动与反应","camera":"构图、运动和观看重点","dialogue":[{"character_id":"A","text":"原语言准确对白","delivery":"语气与表演"}]}],
    "references":[{"label":"Picture 1","asset_id":"A_REF"}],
    "prompt_zh":"完整中文声画执行稿",
    "prompt_en":"按H3 Skill写成的完整英文最终稿"
  }],
  "comfy":{"profile":"h3-ref2va","seed":42}
}
```

- 示例只有一单元，实际`edit_seconds`合计应等于目标时长。不要照搬示例角色、素材或镜数。
- 单元对应一次模型调用，`shots`是其中摄影镜头，可含多句对白。
- 原生音频与动作在英文中一起写，不指定外部TTS全轨。角色声线在每次任务的定义中复用。
- `personality`、`signature_actions`、`locomotion`、`deformation`为可选的角色表演字段；`signature_actions`可写文本或列表。报告展示已填写内容，旧项目不强制补字段、补图或达到固定表情/动作数量。
- 参考素材的`role`写清身份、表情、关键姿势或场景用途；一张综合设定图可复用，静态姿势不声明为完整步态。镜头引用只列实际使用的素材。
- `source_frames`依所选执行配置规划；帧率、格点、预算与尺寸规则由该配置声明。内置`h3-ref2va`的24fps示例中，7秒编辑可用175帧=7.291667秒源；余柄不塞新台词，为原生对白自然结束留足空间。
- 可选`continuity_from`引用前一单元ID，执行时提取实际剪出末帧，作为本次任务参考图动态绑定对应端口。预先在提示词中说明`Picture N`及用途；前期不伪造末帧预览。没有依赖就省略，不强制全片串行；素材输入层可按需增删加载器和参考端口，仍须满足模型数量上限。
- ID用字母数字、下划线或连字符。素材路径相对项目，也可为用户提供的绝对路径；HTML复制到旁边以离线查看。
- 有用户实际声音参考才加`kind=audio`及`Audio N`；图片/音频加载器及对应H3参考端口按本次素材数量动态增删、重绑，不复用未声明的旧素材。原生音频生成主干保持原样。视频参考可在报告展示，能否作为模型输入须由实际执行适配确认。
- `comfy.profile`选择已登记工作流名称或配置路径；连接默认从Skill的`local/comfy.json`读取，也可用`comfy.config`指定项目配置JSON。用户连接示例为`http://127.0.0.1:8188`，不把作者的局域网地址写成公共默认值。
- 保留旧的`comfy.workflow`来指定API节点字典；执行配置记录完整源图的`source_graph_sha256`。执行副本允许替换声明的任务输入，并动态适配参考素材加载器及H3对应端口；模型、LoRA名称和强度、采样器、优化、原生声画主干、尺寸选择器与公式保持。未知预期尺寸、歧义绑定、模型素材上限不足或不支持的流程先报缺项，不以改变模式名冒充支持。
- 配置入口、可选认证及两类API列表见[ComfyUI配置](comfy-configuration.md)。未连接ComfyUI也可完成文案和审阅草稿，实际GPU执行前须配置就绪。

## 报告与确认

```text
python scripts/report.py render --project <项目目录>
python scripts/report.py approve --project <项目目录> --user-confirmation "用户对这份报告的实际确认原话"
```

首次交`review/index.html`及`assets/`集中确认。缺素材/提示词可生成明确标注的草稿，不可审批执行；生成或打开报告不批准。

用户明确要求修改指定镜头并重新生成时，就地更新该镜内容后运行：

```text
python scripts/report.py repair --project <项目目录> --segments U01 --user-confirmation "用户的实际修复与重生成原话"
```

此命令同步报告并记录指定段的局部授权，不另等整片确认。`approval.json`按段绑定该段内容、实际引用素材及执行配置；未受影响段继续有效。共用素材或`continuity_from`变更只触及真实依赖它的段落。不能用用户的分析请求、旧项目授权或创建Skill指令代替本次GPU授权。

旧版整片审批仅在其原始完整摘要与HTML仍匹配时安全迁移；已过期的旧授权不能猜测恢复。旧任务图、记录和源片保留，已提交任务仍可采集。
