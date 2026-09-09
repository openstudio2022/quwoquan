# Video 来源

只读当前来源小节；[CARRIER](CARRIER.md) 拥有选材/脚本/评分。元数据枚举是宿主显式有界请求，不是下载、选择或发布自动化。

## commons · 已实现

- 来源名 `commons`；request 用 `{"query":"<地点>","limit":20}`、`{"category":"<不带 Category: 的类目>","limit":20}` 或 `{"uploader":"<用户>","limit":20}`；limit 必填，1..50。可显式带 API 返回的 continue；单调用只取一页，不自动续页。query 加 filetype:video，解析仅保留 video mime。
- MediaWiki imageinfo 提供 URL、小写 sha1、尺寸/mime/时长（实际有则）、extmetadata；每 File 一候选，Artist 与 uploader 分开。缺 license/Artist 不补 verified。离线 response 为原始 API JSON。
- 可从 Drone videos/Aerial videos/Time-lapse videos/Walking China/地区 Videos 类目发现，但名称、实体落点与权利需实际核实。
- HTTPS 单文件直链可走 Skill download；size 可在传输前预算筛除。poster 由 Data acquire 派生，Skill preview 只处理图片。

## youtube · 已实现有界单条/频道 metadata

- 单条 request：`{"url":"https://www.youtube.com/watch?v=<id>","mode":"single","limit":1}`。
- 频道 request：`{"url":"https://www.youtube.com/@<handle>/videos","mode":"channel","limit":10}`，limit 为 1..100。仅接受 youtube.com/www.youtube.com/youtu.be 的公开 HTTPS URL。
- single 使用 no-playlist，channel 使用 yes-playlist/flat-playlist；两者都显式带 playlist-end/max-downloads，no-playlist 不单独代表有界。无重试，120 秒进程超时。频道 flat 候选还需宿主单条取证，不把频道当 target。
- 保留原 uploader/uploaderUrl，只有源实际 creator 才写 creator；许可、描述、热度按原响应。每条都有稳定 video 资产 ID，duration/filesize 或 filesize_approx 即使缺直链也保留。requested_formats 或 flat URL 不伪造媒体直链。
- entries 缺席只支持单条对象；playlist 缺 entries、entries=null 或未知类型可解释拒绝。数组 null 是不可用位置，计入 limit、不生成候选、不自动补足条数。`--response` 离线回放不代表在线可达或可播放。

## bilibili · 已实现有界单条/UP metadata

- 单条 request：`{"url":"https://www.bilibili.com/video/<BV>","mode":"single","limit":1}`；支持 bilibili.com/www.bilibili.com/b23.tv。
- UP 主 request：`{"url":"https://space.bilibili.com/<uid>/video","mode":"channel","limit":10}`；同样使用显式条数边界，不做分页调度。
- 412/352、登录/验证码/挑战只报告停止，不重试绕过。UP 主账号不独自证明原作者；不填默认协议或许可，版权保留/作者与条款须可回查。

## 本地合并下载 · 宿主取得、机械登记

宿主在确认来源/预算后用 yt-dlp 选格式、写 info.json、合并本地文件；保存到本载体 `video/host/`，然后执行：

```bash
python3 .agents/skills/content-production/scripts/producer.py --workspace "$ROUND" register-local video --candidates video/candidates.json --candidate-id 'youtube:<id>' --asset-id 'youtube:<id>:video' --file video/host/result.mp4 --metadata video/host/result.info.json --max-bytes 536870912
```

登记核对 id/webpage_url、计算媒体 bytes/sha256 和 metadataSha256，不下载、不手填取得成功。读取缓存前仍校验当前载体与两份摘要。不把 watch URL 假称 directUrl；分轨合并结果没有单文件直链时可登记，但当前 Data ingest 强制实际 directUrl，build-inputs 返回 `SOURCE.DIRECT_URL_REQUIRED`，需 Data 契约闭合后才能进入 ingest。

Data API key、ytsearch/bilisearch、Dailymotion/Vimeo/档案/Pexels/Pixabay 等没有对应模块，仅按明确需要用宿主工具取证，不新增占位客户端或自动来源切换，不绕过 DRM、登录或挑战。
