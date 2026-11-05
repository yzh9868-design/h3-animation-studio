# 六宫格故事板驱动 H3

用于把已经收敛的连续场面落实为实际故事板图片，再用明确的时间与格号对应关系指导 H3 演绎。普通完整创作默认每个生成单元一张六格板；用户指定其他板式、仅文案或已有合用素材时按实际范围处理。故事板叠加在角色设计和统一场景设计之上。

## 先确定六个可见瞬间

先写本单元的完整行动、反应和结果，再选六个有用的关键瞬间。每格记录格号、单元内时间、所属摄影镜头、角色动作和机位意图；首格从本单元起点接起，末格落在剪出范围内并给下一段留下清楚状态。

- 六格按左到右、先上后下阅读，默认三列两行。每格的画幅比例采用目标视频比例；例如格内为16:9时，整张无额外页边的三列两行画布约为8:3。核对实际输出尺寸和版式，不把整张板的比例当作视频比例。
- 时间依动作需要分配。预备、快速变化、接触、恢复和理解可以占不同长度，格间保持连续运动；不要把六格机械等分，也不要让一个短促动作被六个近似静止姿势拖慢。
- 六格是关键瞬间，格数不等于摄影镜头数或模型调用数。一个连续镜头可以覆盖六格；存在真实切镜时，为各格指定对应的 `[Shot N]`，另写准确切点。
- 角色的身体朝向、视线、手部、重心、支撑、接触、移动方向和对方反应要能从图上读懂。以“手垂在身侧、胸口朝前方、脚步接住重心”等正面状态描述表演。
- 摄影先回答观众要看清什么，再选景别、观察方向和运动。运镜写清触发、跟随对象和落到的构图；固定观察、跟移、揭示和切近按剧情选择，不把示例的固定机位推广到整片。
- 前后单元一起规划交接：上一段末格与下一段首格继承角色已经走到的位置、朝向、持物、支撑和情绪。换机位或省略路程时，用共同地标与清楚落点建立关系。

对白需要自然说完并留出可读反应。将准确原句、开口位置和完整落音写入相应动作阶段；源尾余柄用于延续落态。不能把“提示词要求某时刻说完”记作实际音频已经完整。

## 用统一素材生成真实图片

使用可用的图像生成 Skill／工具制作实际六宫格图片，遵守其输入与保存规则。把真实使用的图片、用途和来源关系记录到项目中：

- 身份图提供外形、服装和身体比例；可活动道具也保持固定结构、长度、厚度和部件。静态姿势不是完整步态，身份图中的其他动作不替代本段表演。
- 场景主参考固定环境、通路尺度、地标、光色和材质。六格中的角色在同一空间里行动，物件的固有几何不随剧情需要变化；角色转向与透视变化也不意味着物件变长或变宽。
- 用同一主参考派生实际机位需要的画面。相同机位沿用同一环境依据；更换观看方向时核对连通关系与遮挡。图片参考并不构成可任意旋转的三维模型。
- 生成提示词逐格交代本格的单一时刻、镜头和角色状态。图中可印清楚的小时间码辅助阅读；留白、格线和时间码属于规划版面，不属于成片内容。

提交 H3 前查看实际图片：检查格数与顺序、身份和道具比例、同一环境、前进方向、接触支撑，以及段落交接。图与动作稿有冲突时先修真实受影响图片或行动设计，再同步引用；不能仅在 H3 文字中要求模型忽略会改变动作成立条件的错误。

局部修图只处理受影响内容，并核对是否误改其他格、角色比例或环境。错误图片保留为草稿记录，不能同时作为正式动作参考。将实际图片与本次真实用途一同列入单元 `references`；仅在场景说明中列出素材不等于已送入 H3。

## 写成逐格、逐时刻的 H3 稿

读取 `h3-prompt-writing` 的 `SKILL.md` 和 `references/ref-en.txt`，沿用六字段、标签、声源与切镜规则。素材编号以实际输入顺序为准；“两张角色图＋故事板＋环境图”是可选组合，不是固定四图要求。

1. 在 `subject_definitions` 中给故事板一个实际 `<Picture N>` 标签，写清适用的 `[Shot N]`、阅读顺序、六格时刻、构图与动作节拍用途。角色、道具和环境分别用 `<Subject N>` 定义来源，身份图只承担其真实用途。
2. `summary` 概括连续演绎目标及参考关系。每个成片时刻呈现单一全幅场面，格间通过动作和已定义的摄影衔接。
3. `retention_analysis` 按真实用途选择保留关系。只有确实沿用的内容才写 `fully_preserved`；姿势沿用而表情需要变化时，说明具体保留与变化，不把整张错误板一概标为完整保留。
4. 在 `detailed_description` 正文逐一写出“开场对应第1格；在某时刻匹配某图第2格……”。每个锚点紧接可见动作，并说明如何运动到下一锚点；不能只在定义、表格或摘要中列时间，正文却回到剧情概述。
5. 仅真实切镜才增加 `[Shot N]`。第一镜不附切点时间，后续镜头使用 H3 规定的递增切点。固定镜头内的格号变化仍属于同一镜头；移动镜头也要接清各锚点的构图变化。
6. 声线、准确原句、开口与完整落音在对应阶段写清，环境／动作声与配乐按 H3 字段分配。中文执行稿与最终英文表达同一内容，交付与实际提交使用同一版本。

用自然动作和摄影语言表达关键关系。尺寸核对、结构计数、帧数计算和执行日志留在项目资料中，不堆进生成正文；不新增模型并不存在的负向提示词字段。必要的画幅与版面约束直接说明其用途。

## Ref2VA 结构示例

以下假设已有三张真实图片：角色身份图、六格故事板、工作间环境主参考。例子选择9秒、单一固定镜头，只示范写法；实际时长、源帧数、动作、格时与摄影应依项目和所选配置调整。

```text
subject_definitions:
<Subject 1> is the small blue delivery robot in <Picture 1>, with round brass eyes, a red neckerchief and mitten-shaped hands. The identity image supplies its appearance; <Picture 2> supplies this unit's performance.
<Subject 2> is the compact wheeled cart and square parcel in <Picture 2>, retaining their rigid proportions, handle, wheels and stable size.
<Subject 3> is the bright workshop in <Picture 3>, with a level wooden floor, a workbench at screen right and soft afternoon window light.
<Picture 2> is the six-panel storyboard for the continuous [Shot 1], read left to right, top row then bottom row. Its panels mark 00:00.000, 00:01.200, 00:02.000, 00:02.600, 00:04.800 and 00:07.800. It supplies viewpoint, framing, subject placement, action order and timing. Gutters and printed times are planning notation.

summary:
[reference generation] Create a nine-second continuous shot following <Picture 2>. In <Subject 3>, <Subject 1> pushes <Subject 2> toward the workbench, notices the parcel sliding, steadies it and completes the delivery. Animate the panel moments with continuous movement between them.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - retain the blue body, brass eyes, red neckerchief and mitten hands; animate the referenced performance.
<Subject 2> (appears in [Shot 1]): fully_preserved - retain the cart and parcel proportions, construction and contact relationships.
<Subject 3> (appears in [Shot 1]): fully_preserved - retain the floor, right-hand workbench, lighting and connected working space.
<Picture 2> ([Shot 1] storyboard): fully_preserved - follow all six planned moments, their order and framing as a single full-frame animated scene. Its panel layout, gutters and times remain on the reference sheet.

detailed_description:
Warm expressive 3D character animation with crisp, natural physical-comedy timing and the workshop's soft afternoon light. Use a fixed eye-level medium-wide composition that includes the robot's complete body, cart wheels, parcel and the destination workbench. The six reference moments belong to this one continuous shot.
[Shot 1] The shot opens with PANEL 1 of <Picture 2>. <Subject 1> stands at screen left behind the handle of <Subject 2>, looking toward the workbench at screen right in <Subject 3>. Both hands rest on the handle, both feet support its upright body, and the square parcel sits near the cart's center. The robot starts a purposeful forward step and pushes toward the destination.
At 00:01.200, MATCH PANEL 2 of <Picture 2>: the cart rolls right along the same floor as the robot follows with alternating grounded steps. A small wheel jolt makes the parcel tilt forward. The robot's gaze drops toward it while its hands keep the cart moving steadily.
At 00:02.000, MATCH PANEL 3 of <Picture 2>: the parcel has slid close to the cart's front edge. The robot leans from its ankles and extends its nearer hand toward the parcel's forward face, keeping its other hand on the handle. The wheels slow as it shortens the next step.
At 00:02.600, MATCH PANEL 4 of <Picture 2>: the extended palm meets the parcel and arrests its slide. The robot plants its rear foot, bends the receiving knee slightly and steadies the cart through the handle. The parcel remains supported by the cart while the palm directs it back toward the center. A small wooden tap accompanies the contact.
At 00:04.800, MATCH PANEL 5 of <Picture 2>: the parcel is stable in the center again. The robot straightens over its feet, returns both hands to the handle and resumes an ordinary walking push. From about 00:05.200 to 00:06.200, <Subject 1> (S1), using a light youthful midrange voice, standard American accent and brisk conversational delivery, says, <d>[English] Steady now.</d> The complete sentence ends as it approaches the workbench.
At 00:07.800, MATCH PANEL 6 of <Picture 2>: the cart stops beside the right-hand workbench with the parcel stable. The robot finishes its last step, releases its shoulders and looks up with a small relieved smile. Continue this supported final position and subtle eye movement through the end.

overall_soundscape:
Soft workshop room tone continues beneath small rolling-wheel sounds, grounded robot footfalls, a brief parcel scrape and the tap of the steadying hand, synchronized to visible contact.

non_diegetic_music:
N/A
```

## 核对生成结果与局部修复

明确时间锚点改善指向性，不是模型已准确执行的证明。关键动作仍须按需要核对实际帧；对白要确认实际尾音位于剪出点内。将“计划匹配”“实际发生”和“尚有偏差”分开报告，按用户指出的范围修复，不因时间未精确服从而无期限重投 GPU。

若变化影响角色动作成立的空间、尺寸或支撑，先追到对应板图和场景参考；若只是台词时窗、格号或描述缺漏，就地修订该段双语稿。复用未变素材与其他单元，继续遵守主 Skill 的局部执行授权和同任务 ID 恢复规则。
