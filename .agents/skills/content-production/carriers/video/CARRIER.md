# Video · 单条视频作品

本文件唯一拥有视频选材、脚本模板与评分；取来源时只读 [sources 的对应小节](sources.md)。

## 输入与产物

- 对象身份 `posts/video/<angle>/<title>/<seq>`；target 指向已发布或同批先发布的真实 homepage。先由实体反查视频，路线多实体时明确主实体；不能定位或不可入 cohort 的实体不作落点。
- [candidate](schemas/candidate.schema.json)/[selection](schemas/selection.schema.json) 允许发现期缺媒体直链；当前 adapter 要求一个 target 一个来源视频、明确选择唯一视频资产，不把频道/合集或多条视频拼成作品。
- 唯一 author 产物 `4.draft/video_script.json`：`title/caption/scriptLines`，可选真实 `creatorProfileId/tagRefs/sourceVideoAssetRef`；未写 sourceVideoAssetRef 时使用本对象唯一 source video。媒体、poster 及权利机械字段由 Data acquire/seal 投影，不由 author 伪造。

## 选材与证据

- 优先可辨识实体的实景、河山、航拍、延时、行走视角；约 15 秒–5 分钟、≥720p 是选材建议，不新增时长/分辨率准入硬门。播放、点赞等只排序。
- 说明不能定位实体、talking-head/幻灯为主或二传平台烫印明显者优先换候选；版权保留、水印或低分本身不成为新增硬门。
- 下载只取明确选择素材，现有 sourceAssetMaxBytes 与载体媒体预算照用。YouTube/Bilibili 分离音视频由宿主 yt-dlp 下载合并，Skill 不实现合并器；Data acquire 根据现有预算/容器要求转码并抽 poster，记录真实 derivedModifications。
- author/reviewer 必须查实际可播放视频内容及音轨；poster 只证明一帧，不能代完整视频评判主体、节奏、画质、水印或音轨。无法观察的维度留缺口/不评分，不谎称完整看过；无法证明可播放按现有 review 规则处理。
- `hasAudio` 据实际音轨申报；水印 unknown 不是 null，未观察全片不能仅因 poster 无水印就断言全片无水印。

## 脚本模板

- title：实体 + 可见主题/视角，不把来源标题的夸张词当事实。
- caption：实际画面与已取得实体事实的简要说明，季节、路线、历史仅有据才写。
- scriptLines：按真实视频内容组织的简短描述，不编造镜头、旁白、亲历或音轨；不要求机械行数/时长。

`adapter.lint` 仅提示缺 scriptLines，不代替完整视频检查。seal 从实际引用资产补 video 与 poster 权利记录，reviewer 不另写第二份 poster 权利文件。

## 六维评分

独立 reviewer 可在唯一 seal.review 输入中给 1–5 整数，2/4 介于锚点之间；只记录、不补零、不影响 admission。不能用 poster 给未观察的音轨/剪辑打分。

| 维度键 | 1 分 | 3 分 | 5 分 |
| --- | --- | --- | --- |
| `subject_relevance` | 看不出实体 | 实体可辨 | 实体为主角且有标志性镜头 |
| `visual_quality` | 抖动、模糊、明显低清观感 | 稳定清晰 | 曝光准、色彩自然、细节丰富 |
| `editing_rhythm` | 拖沓或片段不完整 | 开头即景、节奏平稳 | 节奏匹配、有起承转合 |
| `audio_fit` | 噪声/无关配乐/突兀口播 | 不干扰；确认无音轨记 3 | 音画相得益彰 |
| `unique_perspective` | 常见地面机位 | 有航拍或延时 | 罕见视角且具辨识度 |
| `rights_clarity` | unknown | unverified 但许可原文可读 | verified 且署名清楚 |
