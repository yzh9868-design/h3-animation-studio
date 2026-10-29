# ComfyUI执行

仅在需要生成视频时读取本文件。创作文案与HTML审阅可以独立完成；首次选用或导入工作流见[配置说明](comfy-configuration.md)。已配置的项目直接复用，单镜快修不重新配置环境。

当前通用适配执行H3 Ref2VA，支持图片及用户自供音频参考，保留原生声画。其他H3模式可编写提示词，但需要相应执行适配；导入任意JSON并不等于已支持其模式或视频参考。

执行配置声明节点输入输出映射、帧率、源帧格点、尺寸与参考数量限制。内置`h3-ref2va`配置的例子为24fps、length从5起按17递增，源时长4—15秒；该格点内可用107—345帧。其他工作流按自身声明核对，不把这个示例当作所有模型的规则。

执行以用户上传的完整API图为基准。在执行副本中替换声明的任务输入，并按素材数量动态增删、重绑参考图/音频加载器与H3参考端口；该例外只作用于参考素材输入层。模型、LoRA名称与强度、采样器、优化设置、原生声画主干、时长公式及尺寸选择器保持原样。宽高若来自上游选择器，期望尺寸用于检查输出，不能覆盖原连接。不得按名称或与题材是否相关自行删除LoRA等主干节点。源图摘要和差异约束见[配置说明](comfy-configuration.md)；`prepare`核对实际`/object_info`，节点存在或参数兼容不代表效果已实测。

先离线检查所选配置和源时长规划：

```text
python scripts/comfy_run.py inspect --project PROJECT
```

源时长与编辑时长单列。`source_frames`按所选配置明确写入；作者把对白和行动安排在剪出点前，额外尾柄只保持末态，不用任意裁切、变速或补帧补救超时。配置和最终稿就绪后更新报告，再集中确认首次执行；已授权局部快修沿用下面短路径。

首次确认实际HTML包后，用`report.py approve`记录原话和批准段落。后续用户明确要求某段修复并重新生成，就地修改该段、同步中英文，再运行：

```text
python scripts/report.py repair --project PROJECT --segments U01 --user-confirmation "用户的实际修复与重生成原话"
```

此命令同步报告并记录局部授权，不等待再次确认整片。只有获准的段落可执行：

```text
python scripts/comfy_run.py prepare --project PROJECT --segment U01
python scripts/comfy_run.py submit --project PROJECT --segment U01 --execute
python scripts/comfy_run.py status --project PROJECT --remote
python scripts/comfy_run.py collect --project PROJECT --segment U01
python scripts/comfy_run.py assemble --project PROJECT --output output/film.mp4
```

- `prepare`核对本段授权、引用、时长及配置，上传并回下载核对素材，保存源图快照并冻结执行副本；不提交GPU。输入绑定和输出采集依据所选配置，不依赖固定节点编号。自动检查只允许声明的任务输入值，以及参考素材加载器和对应H3参考端口的动态增删、重绑；其余节点、参数与连线必须保持。
- `submit --execute`核对本段摘要、源快照、冻结图和素材，并再次执行输入差异检查；非白名单变化阻止提交。无关段落变更不使本段失效，共用素材及真实连续依赖变更只影响相关段。POST前记录不确定状态；网络中断先查队列/history，绝不重复POST。必要时用`collect --prompt-id ID`恢复，绑定前必须与冻结图完全匹配。
- 状态保存在`execution/state.json`，每个take的图、记录、源片和剪出末帧保存在`execution/jobs/<段落ID>_<随机ID>/`。在途或结果不确定的任务不能覆盖；失败不自动重试。
- 尚未提交的准备记录可用`prepare --replace-prepared`更新并归档。已完成或明确失败的旧take，在新的明确修复与重生成授权下用`prepare --new-take`归档后重做，保留原段ID和旧证据。
- `collect`、`status`读取已冻结任务，不要求后续草稿仍获批。采集只做来源、可解码性、音视频流、帧数、尺寸、时长及剪出末帧检查，不做AI审片。
- 只有声明`continuity_from`的段落等待指定前段，按实际素材数量动态绑定该段实际剪入最后一帧。`continuity_picture`、提示词标签和真实图片输入一致；原图参考端口数不是本次任务容量上限，仍须满足模型素材上限。同步检查上游定义及实际选中take/末帧，不把新上游与失效旧下游静默拼接，扩大重生成须对应授权。
- 配置验证原生音频从采样器经音频解码进入视频输出的实际连接，该生成主干保持原样。默认不生成TTS、不混外轨；音频参考是独立的素材输入支路，按本次实际素材增删加载器和对应参考端口，不偷偷复用未声明旧参考。
- `assemble`逐段验证授权与所选源片，再按批准的剪辑窗合成。默认不覆盖已有成片，技术通过后交用户审查版，不据此宣称剧情、声音或动作已验收。

普通固定素材、固定工作流的单镜快修，以3—5分钟完成文案和提交准备为目标，非时间保证。上传、服务异常、排队和推理单列耗时；报告同步由脚本完成，不另设人工复核阶段。旧版审批只在原摘要与HTML有效时安全迁移，已过期时不臆造授权。
