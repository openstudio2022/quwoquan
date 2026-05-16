# 视频内容 SOP（video）

## 检索策略

### 内容源


| 平台      | 适用场景      | 检索词模板                |
| ------- | --------- | -------------------- |
| 哔哩哔哩    | Vlog、攻略视频 | `{实体名} vlog/旅行`      |
| 抖音      | 短视频、打卡    | `{实体名} 旅行/打卡`        |
| YouTube | 深度纪录      | `{实体名} travel guide` |


## 下载规则

1. 每实体目标 5+ 条精选视频
2. 存储视频元数据：`sources/{实体名}/videos/video_NN.meta.json`
3. 视频本体存储策略由部署决定（CDN / 对象存储）

## 质量标准


| 维度  | 阈值          |
| --- | ----------- |
| 画质  | >= 720p     |
| 时长  | 30s - 15min |
| 内容  | 非纯广告，有实际场景  |


## 准出 gate

- manifest 含 videoUrl / videoAssetId
- entityRefs, tagRefs 全中文
- 含封面图 coverAssetId