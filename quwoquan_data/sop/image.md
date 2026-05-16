# 图片内容 SOP（image）

## 检索策略

### 内容源


| 平台  | 适用场景   | 检索词模板            |
| --- | ------ | ---------------- |
| 小红书 | 打卡照、风景 | `{实体名} 拍照/打卡/风景` |
| 马蜂窝 | 行程图    | `{实体名} 实拍/旅行照片`  |
| 微博  | 即时分享   | `#{实体名}# 摄影`     |


### 检索词生成

Agent 根据 entityType + season + 场景 自动推导。

## 下载规则

1. 每实体目标 20+ 张高质量原图
2. 存储：`sources/{实体名}/images/img_NN.jpg`
3. 元数据 sidecar：`img_NN.meta.json`（含 url, platform, photographer, license）

## 质量标准


| 维度  | 阈值         |
| --- | ---------- |
| 分辨率 | >= 1080p 宽 |
| 构图  | 主体清晰、无严重畸变 |
| 水印  | 无水印或可去除    |


## 生成模板


| 模板ID        | 角度   | 必含元素     |
| ----------- | ---- | -------- |
| 景区_风景_image | 风景照  | 全景/特写各 1 |
| 景区_人文_image | 人文纪实 | 人物与场景结合  |


## 准出 gate

- manifest.assets 每张含 assetId, fileName, width, height
- 图片真实存在于 assets/ 子目录
- entityRefs, tagRefs 全中文