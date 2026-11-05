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
  "assets":[
    {"id":"A_REF","kind":"image","path":"assets/A.png","role":"角色身份与固定比例，动作来自本单元故事板","prompt":"实际生图提示词"},
    {"id":"SET_REF","kind":"image","path":"assets/set.png","role":"统一实际场景主参考","prompt":"实际生图提示词"},
    {"id":"SB_U01","kind":"image","path":"assets/U01-storyboard.png","role":"本单元六宫格动作、摄影和时间规划","derived_from":["A_REF","SET_REF"],"prompt":"引用上述真实素材制作六格的实际生图提示词"}
  ],
  "segments":[{
    "id":"U01","mode":"Ref2VA","edit_seconds":7,"source_frames":175,
    "purpose":"本段推进的信息或行动",
    "shots":[{"id":"S01","duration_seconds":7.2916666667,"action":"完整可见行动与反应","camera":"构图、运动和观看重点","dialogue":[{"character_id":"A","text":"原语言准确对白","delivery":"语气与表演"}]}],
    "storyboard_asset_id":"SB_U01",
    "panels":[
      {"index":1,"time_seconds":0,"shot":"S01","action":"起态与目标","camera":"首格视点与构图"},
      {"index":2,"time_seconds":1.4,"shot":"S01","action":"接近并准备","camera":"保持同一观察关系"},
      {"index":3,"time_seconds":2.1,"shot":"S01","action":"关键动作开始","camera":"让接触关系可见"},
      {"index":4,"time_seconds":2.5,"shot":"S01","action":"动作及物件反馈","camera":"保留必要身体与物件"},
      {"index":5,"time_seconds":4.9,"shot":"S01","action":"连续行动后的反应","camera":"按当前信息安排构图"},
      {"index":6,"time_seconds":6.8,"shot":"S01","action":"落态并交接下段","camera":"交代相邻区域或保留位置关系"}
    ],
    "references":[{"label":"Picture 1","asset_id":"A_REF"},{"label":"Picture 2","asset_id":"SB_U01"},{"label":"Picture 3","asset_id":"SET_REF"}],
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

## 六宫格故事板

新完整制片模式每段填写`storyboard_asset_id`，指向`assets`中一张实际六宫格image；`panels`依图板阅读顺序填写六项，不单独创造六个Shot。各项包含`index`（1—6）、`time_seconds`（本生成单元秒数）、`shot`（对应`shots[].id`）、`action`和`camera`。第1格时刻为0，时刻严格递增，末格在`edit_seconds`剪出范围内；源尾柄不安排不可见的新关键格。时间只是规划，不是已生成证据。

同一张板须真实进入该段`references`。实际Picture标签从此顺序取得：示例是`Picture 2`，不能机械写成`Picture 3`。身份、道具和环境图片数量按任务决定；`derived_from`仅记录真实生图输入，不自动生成、修复或绑定素材。

`report.py render`展示六格大图以及“本地时间→Picture标签/格号→Shot→动作→摄影”表，复制区保持原始中英字符串。就绪检查仅验证六项记录、时间、Shot关联、实际图片与引用，不检查图中几何或自动编写英文。作者仍需在最终正文中逐格明确时间和格号，并观察实际图片是否成立。

旧项目无`storyboard_asset_id`时沿用原格式，采集或小修不强制补板；不要只添加标记来冒充已制作。纯文案或尚缺图片可渲染明确草稿，不能据此批准运行视频。

## 可选场景空间设计

同一大场景内跨区域活动、反复返回或复杂追逐时，按[场景空间与穿行设计](spatial-design.md)使用顶层`scenes`，以及相关`shots[].space`。简单场景和旧项目可省略；Agent填写，不要求用户手填。场景是同一地点的整体，`regions`是其中的局部区域，`routes`是区域之间的实际路线。

下例是补充到同一`film.json`的可选字段。描述字段用自然语言；图片ID先在`assets`注册实际素材，纯文案设计可省略`asset_ids`。

```json
{
  "scenes":[{
    "id":"FOREST",
    "name":"林间空地与溪岸",
    "layout":"入口在西南，古树在中央偏西；窄道绕树南侧通向东面溪岸。古树与小桥是固定地标。",
    "look":"清晨柔和侧光，统一树皮和植被材质；以角色身高标示门洞、树根与桥面的相对尺度。",
    "asset_ids":["FOREST_PLAN"],
    "regions":[{
      "id":"TREE","name":"古树南侧",
      "layout":"树根间留可通行的窄道，角色可在入口短暂停留。",
      "landmarks":"主树干的分叉与地面的弯曲树根固定。",
      "connections":"向东沿窄道进入CREEK，向西返回空地。",
      "asset_ids":["TREE_SOUTH_VIEW"]
    },{
      "id":"CREEK","name":"溪岸",
      "layout":"窄道接近岸石阶，小桥跨过溪流。",
      "landmarks":"小桥与岸边大石固定；向西能看见古树上部。",
      "connections":"西侧石阶接TREE的窄道。",
      "asset_ids":["CREEK_WEST_VIEW"]
    }],
    "routes":[{
      "id":"TREE_TO_CREEK","name":"绕树抵达溪岸",
      "from_region":"TREE","to_region":"CREEK",
      "path":"从树南侧窄道入口出发，绕过凸出的树根，沿短径向东到近岸石阶。",
      "handoff":"绕树后先露出同一座小桥，再抵达石阶；后续镜头保留已抵达的位置。"
    }]
  }]
}
```

在相关镜头对象中补充`space`；沿用原有的`action`、`camera`、时长和对白。一个镜头跨区域时，`region_id`可记起始区域，落点写在`end`并与路线终点对应。

```json
{
  "space":{
    "scene_id":"FOREST","region_id":"TREE","route_id":"TREE_TO_CREEK",
    "start":"古树南侧窄道入口",
    "end":"溪岸近侧石阶前",
    "viewpoint":"机位在小径南侧，面向人物与东侧溪岸，古树逐渐留在后方。",
    "handoff":"停在实际走到的石阶前；下一镜承接朝向、持物与情绪。"
  }
}
```

- `scenes[].asset_ids`展示总体示意或总景参考，`regions[].asset_ids`展示对应局部视点。`layout`说明空间，`look`说明共同视觉；`landmarks`和`connections`保留必要地标与连通关系。按实际需要填写，不追求字段齐全或固定图数。
- `scene_id`对应顶层场景ID；`region_id`、`route_id`对应该场景内的区域和路线ID。路线的`from_region`、`to_region`同样指向本场景区域。没有路线就省略`route_id`。这些关联由Agent在原有联合检查中核对，脚本不推断几何、距离、可通行性或三维一致性。
- 上述`asset_ids`仅用于规划与审阅展示，**不会自动成为模型输入**。实际提交的图片仍逐一列入本单元`references`，并在中英文提示词中按实际用途定义；总图不默认作为首帧，局部设定不默认作为实际末帧。
- 规划图通过实际生图约束总场景，再由总景派生所需局部环境。可用素材的可选`derived_from`数组记录真实父素材ID，并在`role`说明来源与用途；实际生图提示词记录引用了哪些图片。相应局部环境仍须显式写入各单元`references`，在H3稿中定义环境Subject和保留关系。`derived_from`不自动生成图片、同步下游或替代实际输入绑定；来源变更后核对真实受影响素材与镜头。
- 最终提示词从空间设计中选取本单元必要的起止位置、路径、机位、遮挡和交接信息。场景ID和项目字段不直接充当H3参考标签，不整表复制入正文。
- 修改共用空间设定后，就地同步实际受影响镜头的`space`、行动、提示词及输入素材。规划字段不会自动重写生成稿或更换引用；只修改顶层场景文字不能视为执行输入已同步。各段授权仍按实际单元内容、引用素材和真实连续依赖绑定，不扩大重生成范围。
- HTML在填写时展示场景、区域、路线、相关图片与每镜空间关系；没有这些字段时维持原有报告结构。首次仍集中确认整份前期包，局部修复沿用既有授权路径。

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

此命令同步报告并记录指定段的局部授权，不另等整片确认。`approval.json`按段绑定该段内容、实际引用素材及执行配置；未受影响段继续有效。共用素材或`continuity_from`变更只触及真实依赖它的段落。同一项目中仍适用的既有整片或局部授权持续有效；不能用用户的分析请求、其他项目或超出范围的授权、创建Skill指令代替本次GPU授权。

旧版整片审批仅在其原始完整摘要与HTML仍匹配时安全迁移；已过期的旧授权不能猜测恢复。旧任务图、记录和源片保留，已提交任务仍可采集。
