# Video · 单条视频作品

本文件唯一拥有视频选材、脚本模板与评分；取来源时只读 [sources 的对应小节](sources.md)。

## 输入与产物

- 对象身份 `posts/video/<angle>/<title>/<seq>` 与地点关联分开。有可核实地点时，target 指向已发布或同批先发布的真实 homepage，路线多实体明确主实体；不可入 cohort 的实体不作落点。摄影视频（如野生动物精彩瞬间）无确证拍摄地时，不填写 entityId/entityRef/entityType/region，不造假地点或物种主页，使用既有摄影主题标签。半填地点身份拒绝；下载、实际观察、独立审核和去重要求不变。
- [candidate](schemas/candidate.schema.json)/[selection](schemas/selection.schema.json) 允许发现期缺媒体直链；当前 adapter 要求一个 target 一个来源视频、明确选择唯一视频资产，不把频道/合集或多条视频拼成作品。
- 唯一 author 产物 `4.draft/video_script.json`：`title/caption/scriptLines`，可选真实 `creatorProfileId/tagRefs/sourceVideoAssetRef`；未写 sourceVideoAssetRef 时使用本对象唯一 source video。媒体、poster 及权利机械字段由 Data acquire/seal 投影，不由 author 伪造。

## 选材与证据

- 优先可辨识实体的实景、河山、航拍、延时、行走视角；约 15 秒–5 分钟、≥720p 是选材建议，不新增时长/分辨率准入硬门。播放、点赞等只排序。
- 说明不能定位实体、talking-head/幻灯为主或二传平台烫印明显者优先换候选；版权保留、水印或低分本身不成为新增硬门。
- 下载只取明确选择素材，现有 sourceAssetMaxBytes 与载体媒体预算照用。YouTube/Bilibili 分离音视频由宿主 yt-dlp 下载合并，Skill 不实现合并器；Data acquire 根据现有预算/容器要求转码并抽 poster，记录真实 derivedModifications。
- 作者 seal 前完整看听 exact 交付段，对照 title/caption/scriptLines，并核实转码后实际声音，不能沿用原片听感。区分无音轨、有轨静音与不可听：无音轨由实际媒体证实，有轨静音须实际听核，不可听不等于静音或无音轨，缺必要视听即 blocked；音量检测、解码成功不能证明「环境声、无口播」或「已听过」。
- `hasAudio` 据实际音轨申报，不因有轨静音写 false；水印 unknown 不是 null，未观察全片不能仅因 poster 无水印就断言全片无水印。

## 脚本模板

- title：实体 + 可见主题/视角，不把来源标题的夸张词当事实。
- caption：实际画面与已取得实体事实的简要说明，季节、路线、历史仅有据才写。
- scriptLines：按真实视频内容组织的简短描述，不编造镜头、旁白、亲历或音轨；不要求机械行数/时长。

`adapter.lint` 仅提示缺 scriptLines，不代替完整视频检查。seal 从实际引用资产补 video 与 poster 权利记录，reviewer 不另写第二份 poster 权利文件。

## 当前草稿核读与质量纠偏

按[共享 QA 决策](../../references/dispatch.md#qa-整批交总监)核当前草稿 `video_script.json`、来源及 `002-4.draft` 实际 resultRefs。本域逐项核对 exact 交付段画面、声音与脚本；镜像、poster、ffprobe 或抽帧不能替代完整视听后 approved。未看完整画面、未听音轨（实际有音轨时）即 blocked；已观察的画面/声音与文案矛盾须引用原句、资产与时间段交作者纠正。

生产术语、取证限制与审核提示不进入 title/caption/scriptLines；描述只针对实际画面和有据背景。既有 approved 不代表质量高或当前已读稿，缺观察与低分分开处理；低分只引导下一批选材纠偏，不新增分数准入门，不自动改封存 review、覆写成品或换 ID 重发。

QA 对当前 title/caption/scriptLines 未逐段核读不能宣称“无残留”；发现残留须引用 exact 原句，关键词未命中不证明语义无残留，也不能凭旧 approved 或完整视听就替当前文案作保证。

## 兴趣标签

作者 seal 前按实际完整视听选 `tagRefs` 并逐项确认解析到既有 taxonomy；外站话题词只作候选，不猜造非法路径。图片与视频共用题材叶子，不按载体新建近义路径。

- 主体优先：自然风光、动物、植物、城市建筑、人文风物、旅途生活与全站生活、学习、娱乐题材使用既有 Topic/Entity 叶子。
- 场景或行为有据才选：日照金山、取食、求偶、筑巢、育雏；拟人标题不能单独证明求偶或智商。迁徙等未声明 `consumedBy` 的叶子不作为正式消费样例。
- 正式消费只选已声明 `consumedBy` 的叶子。观看价值优先用 `Topic/摄影/摄影教程` 等已声明主题；未声明采集与消费的 Format 内容角度只作创作提示，不写入正式映射合同。纯风景不自动带教程或器材。
- 地点、季节、物种只在可核验时选择；未知则省略，不造假地点或物种主页。
- 可见观感可辅助，不得压过主体。时长、画幅、音轨、器材、光圈、快门、ISO、构图和制作流程不作为大众兴趣标签。
- 不从画面人物、颜色、作者姓名或一次查询推断 Audience 画像。建议少而准，不加数量硬门；App 手工五标签上限不是 Data 导入上限。

## 六维评分

独立 reviewer 可在唯一 seal.review 输入中给 1–5 整数，2/4 介于锚点之间；只记录、不补零、不影响 admission。不能用 poster 给未观察的音轨/剪辑打分。

| 维度键 | 1 分 | 3 分 | 5 分 |
| --- | --- | --- | --- |
| `subject_relevance` | 看不出实体 | 实体可辨 | 实体为主角且有标志性镜头 |
| `visual_quality` | 抖动、模糊、明显低清观感 | 稳定清晰 | 曝光准、色彩自然、细节丰富 |
| `editing_rhythm` | 拖沓或片段不完整 | 开头即景、节奏平稳 | 节奏匹配、有起承转合 |
| `audio_fit` | 噪声/无关配乐/突兀口播 | 不干扰；确认无音轨记 3 | 音画相得益彰 |
| `unique_perspective` | 重复空泛，没有可辨的观察收益 | 视角带来明确的观察收益，能看清主体关系或变化；地面、航拍、延时同标 | 有据的独到视角揭示主体特征，持续带来鲜明且具辨识度的观看收益 |
| `rights_clarity` | unknown | unverified 但许可原文可读 | verified 且署名清楚 |
### 消费者等级与证据

评分必须引用实际观察的时间段、画面、音轨及 rubric 版本；未观察的适用维度保持“未评定”，不得填 `N/A` 或补零。确认无音轨时可预先声明 `audio_fit` 的适用规则；`rights_clarity` 是独立权利轴，不参与内容等级平均。内容等级：D=任一适用内容维度为1；C=无1但有2；B=全部适用内容维度至少3；A=B且核心 `subject_relevance|editing_rhythm|unique_perspective` 至少4；S=核心均5、其余适用内容维度至少4且经跨队复核。单队场景不以同队独立 QA 冒充跨队复核；缺少跨队复核证明时不标 S，只记录已证实的分数及满足条件的较低等级与证据缺口。跨队复核仅为 S 等级证据，不新增发布审批、不改变 admission、不改 sealed review；旧对象只读评估，不回写历史审核。硬阻断优先。航拍、延时与配乐不天然高分，按完整观看收益、节奏与视听一致性评价。
