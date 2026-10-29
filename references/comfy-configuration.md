# ComfyUI配置与工作流目录

ComfyUI是可选执行模块。用户只要求剧本、分镜或提示词时，直接完成创作；需要生成或用户要求配置时，再使用这些入口。配置完成后复用，单镜快修不重复发现环境。

## AI首次配置

用户提供服务地址和从ComfyUI导出的API格式工作流JSON后，AI负责执行工具与编写所需配置，通常不要求用户运行命令或手填映射。已有配置可用时直接复用。

1. 读取已有连接和登记清单，解析上传API；新工作流按新名称导入，不覆盖无关旧配置。
2. 识别提示词、参考素材支路、种子、尺寸、帧数、原生声音及输出字段。脚本推断不足时，AI结合原图连线及节点schema编写单独的映射配置，通过`--mapping`导入；只补有依据的字段。当前通用执行适配为H3 Ref2VA，不把补映射当作任意模式适配。
3. 设置服务连接并选中刚导入的配置。执行离线检查；用户要求接入并检查时，再用`--online`只读核对服务。用户限定离线时不联网。
4. 用`list`和`apis`整理工作流清单、服务路由、选中配置、检查状态及真实缺项。不能从图或节点定义确定的事实集中询问，例如预期输出尺寸或模型素材上限；图中已有的模型、LoRA、采样参数直接保留。不用试跑视频代替配置检查。

参考图/音频加载器及H3对应参考端口可在执行副本中按本次素材数量动态增删、重绑。多个候选须由实际连线和用途判断；不支持的流程、缺失节点或模型如实报告，不凭名称猜兼容性，也不自行安装或替换用户环境。

以下为AI调用的工具顺序，用户不必手动执行：

```text
python scripts/comfy_setup.py import-workflow my-workflow-api.json --name my-h3
python scripts/comfy_setup.py configure --url http://127.0.0.1:8188 --profile my-h3
python scripts/comfy_setup.py list
python scripts/comfy_setup.py apis
python scripts/comfy_setup.py doctor --profile my-h3
```

`configure`保存连接和默认配置，`import-workflow`保存API图及推断配置，`list`以JSON列出已登记工作流及缺项，`doctor`默认只离线检查。普通画布JSON的`nodes`数组不是可执行API节点字典，须导出API格式。同一次接入需补映射时，由AI编写单独的映射JSON，更新刚导入的配置：

```text
python scripts/comfy_setup.py import-workflow my-workflow-api.json --name my-h3 --mapping my-h3-profile.json --replace
```

导入重名默认拒绝；同一次接入中为刚导入的配置补映射时，可用`--replace`更新该配置。替换已有无关配置需用户相应指令，否则另存新名称。原始源JSON保持不变。`configure`还支持`--timeout`、`--header-env HEADER=ENVVAR`以及作为预期尺寸的`--width`、`--height`。全局`--root`可指向独立Skill目录，用于隔离配置或测试。

需要核对服务器时明确增加`--online`：

```text
python scripts/comfy_setup.py doctor --profile my-h3 --online
```

在线检查只读取`/system_stats`和`/object_info`，报告所需节点、模型选项与参数是否兼容，不上传素材或运行样片。实际生成仍按项目授权和`submit --execute`执行。

## 保留上传API，只替换任务输入

上传原件和导入后的完整API图是事实基准，源图保持原样。执行副本允许替换任务输入，并对参考素材输入层作下面的限定变化；其他非素材节点、模型、LoRA名称和强度、采样与优化设置、原生声画主干、尺寸选择器和帧数公式保持。不得以“不相关”“不适合题材”或文件名含义为理由自行删除、替换或旁路模型与LoRA等主干节点。

执行配置声明任务输入字段的用途。任务可替换提示词、媒体文件名、时长或帧数、输出命名，以及用户明确要求的尺寸、种子等值。参考素材支路之外的链接保持；例如时长经过原有公式换算时，修改其声明的时长原语，不重写公式或改接H3长度端口。预期尺寸不能代替上游选择器。

**参考素材输入层是明确的结构例外。** 按本次实际图片、音频及连续末帧素材，动态添加、删除或复用`LoadImage`、`LoadAudio`节点，并增删、重绑对应的H3参考端口与素材支路连线。素材标签与实际输入一一对应，不把原图槽位数当固定容量，也不偷偷保留未声明的旧参考。该操作属于任务输入适配，不要求用户另行提供多端口API；仍不得改动其他非素材节点或生成主干。真正超出模型素材上限、绑定不明确或当前适配不支持时才报告具体缺项。用户另行明确要求修改生成主干等其他结构时，作为独立改图任务另存新版本，保留上传原件。

导入记录完整源图的规范化摘要`source_graph_sha256`。准备和提交阶段自动对比源快照与实际提交图，白名单包含已声明的任务输入值，以及上述参考素材加载器、对应H3参考端口与素材支路连线的结构变化；其他节点、字段、连线或参数变化阻止提交。该检查由程序完成，沿用现有快修路径，不增加人工复核表或二次整片审批。历史已提交快照保持原样；恢复或改正配置另存当前版本，不改写过去的执行证据。

## 文件与复用

- `config/comfy.example.json`是公开示例，默认本机回环地址；用户连接写入`local/comfy.json`。
- 内置配置在`profiles/`；用户导入的配置和原始API图放在`local/profiles/`、`local/workflows/`。`local/`被Git忽略，开源时不提交个人地址、绝对路径或凭据。
- 配置声明模式、参考素材输入支路、视频/原生声音输出、默认值及模型素材上限，并绑定源图摘要。原图参考端口数量可作为初始信息，不限制动态任务输入。上游尺寸选择器连接保持原样；预期尺寸未知时报告缺项，不退回固定尺寸。
- 只在工作流、实际绑定或相关运行环境变化后重新检查。检查状态和执行配置分开保存，避免一次状态更新使已授权镜头失效。

配置优先级为内置默认、`local/comfy.json`、`film.comfy.config`指定JSON、`film.comfy`显式值。`config`路径相对项目；`profile`可选登记名称或JSON路径，其`workflow`相对配置文件定位。旧的`film.comfy.workflow`仍可提供API图；同层没有显式`profile`时自动推断该图，避免沿用其他工作流的映射。详见[项目格式](project-format.md)。

可选认证以`headers_env`记录HTTP头与环境变量名的对应，凭据在运行时读取，不写进工作流、报告或日志。例如`{"Authorization":"COMFY_TOKEN"}`表示从该环境变量读取完整头值。AI只记录变量名，不要求用户把秘密贴进公开配置。

## 两种API清单

```text
python scripts/comfy_setup.py list
python scripts/comfy_setup.py apis
```

`list`列完整业务工作流：名称、模式、原图参考输入信息、模型图片/音频数量上限、输入输出、限制与配置/验证状态。当前通用执行适配为H3 Ref2VA，实际参考图和音频端口按任务素材动态绑定。其他模式可以登记，但适配未支持时必须明确标出，不能据提示词Skill支持就声称可执行。

`apis`列ComfyUI服务路由及用途，例如节点发现、素材上传、提交、查询和下载。`/object_info`表示节点定义，不能单凭它推断已存在完整的文生视频或图生视频工作流。

检查状态采用`needs_configuration`、`offline_ready`、`schema_compatible`等技术结论，不自动标记实跑成功。配置保存、离线检查、服务器兼容和真实生成成功分别报告；只有真实任务成功才可报告实跑成功。服务接口来源见[ComfyUI路由文档](https://docs.comfy.org/development/comfyui-server/comms_routes)。
