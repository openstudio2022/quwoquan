# Video 来源

只读当前来源小节；[CARRIER](CARRIER.md) 拥有选材/脚本/评分。元数据枚举是宿主显式有界请求，不是下载、选择或发布自动化。

## 来源优先与有界检索

- 专业类与综合类同等首选，不按名单顺序排名：抖音、快手、TikTok、Facebook 公开视频/Reels、腾讯视频、百度视频、YouTube、Bilibili（B站）均在发现候选范围；按题材可补 Vimeo、Dailymotion、西瓜视频和 Pexels/Pixabay 等专业视频素材库。百科/Commons 只作补充，专业视频不必等综合平台找完才搜；此名单不是在线能力或自动采集承诺。
- 实体/区域/别名交叉徒步、自驾、航拍、街景、自然、摄影主题，结合原作者主页、频道/合集与单作品检索；通用预算和站点轮换按[共享 sourcing 的有界检索](../../references/sourcing.md#有界检索与能力记录)，不逐作品遍历全站。短视频与长视频都按实际内容完整性、片长、画面音轨、字幕/水印选材，不因短而自动优先；电视剧/影视片段、宣传预告不能仅凭地名命中冒充旅行实景作品。
- 百度视频按聚合发现入口处理，落定实际播放页与供稿网站后才登记作品来源；百度自有托管也须真实页面证据，不自动把全部结果归为百度原作。抖音与 TikTok 分列，跨平台同原作重传先去重，不能把不同 URL 当不同作品。

## 发现、详情与原件能力边界

以下是本地实现边界，不是逐站在线验证结果；每次实际使用分别记录发现、详情读取、原件取得及未验证/阻断原因，不从一个维度推断另两个维度。

- 抖音：发现仅用宿主合法公开搜索线索；详情未实现专用模块；原件取得未实现，不开放自动采集。
- 快手：发现仅用宿主合法公开搜索线索；详情未实现专用模块；原件取得未实现，不开放自动采集。
- TikTok：发现依宿主可用公开搜索；详情未实现专用模块；原件取得未实现，未验证可访问/下载。
- Facebook 公开视频/Reels：发现依宿主可用公开搜索；详情未实现专用模块；原件取得未实现，“公开”不保证无登录可读或有分发权。
- 腾讯视频：发现依宿主可用公开搜索；详情未实现专用模块；原件取得未实现，不绕付费、登录或 DRM。
- 百度视频：发现依宿主可用公开搜索；详情回实际播放/供稿站核实、未实现专用模块；原件取得未实现，不把搜索落地页当媒体直链。
- YouTube：发现有下述有界频道 metadata；详情有单条 metadata，非完整播放证据；原件由宿主依法取得/合并并机械登记，不宣称 source 自动下载。
- Bilibili：发现有下述有界 UP metadata；详情有单条 metadata，非完整播放证据；原件由宿主依法取得/合并并机械登记，挑战即停。
- Vimeo、Dailymotion、Pexels/Pixabay：发现依实际宿主工具或合法正式 API；详情及原件未实现专用模块，未验证时保留缺口。
- 西瓜视频：发现仅用宿主合法公开搜索线索；详情与原件未实现专用模块，不开放自动采集。

现有 spec 对抖音/快手/西瓜的自动采集限制仍须遵守：允许登记公开发现线索不等于解除访问/下载约束；合法工具与验证未闭合前不开放自动采集。未实现部分只在宿主实际可用能力内取证，不新增占位客户端，不借换代理/账号绕过挑战。

## commons · 已实现

- 来源名 `commons`；request 用 `{"query":"<地点>","limit":20}`、`{"category":"<不带 Category: 的类目>","limit":20}` 或 `{"uploader":"<用户>","limit":20}`；limit 必填，1..50。可显式带 API 返回的 continue；单调用只取一页，不自动续页。query 加 filetype:video，解析仅保留 video mime。
- MediaWiki imageinfo 提供 URL、小写 sha1、尺寸/mime/时长（实际有则）、extmetadata；每 File 一候选，Artist 与 uploader 分开。缺 license/Artist 不补 verified。离线 response 为原始 API JSON。
- 可从 Drone videos/Aerial videos/Time-lapse videos/Walking China/地区 Videos 类目发现，但名称、实体落点与权利需实际核实。
- HTTPS 单文件直链可走 Skill download；size 可在传输前预算筛除。poster 由 Data acquire 派生，Skill preview 只处理图片。

## youtube · 已实现有界单条/频道 metadata

- 单条 request：`{"url":"https://www.youtube.com/watch?v=<id>","mode":"single","limit":1}`。
- 频道 request：`{"url":"https://www.youtube.com/@<handle>/videos","mode":"channel","limit":10}`，limit 为 1..100。仅接受 youtube.com/www.youtube.com/youtu.be 的公开 HTTPS URL。
- single 使用 no-playlist 与 playlist-end=1；不加 max-downloads=1，避免 yt-dlp 在 dump-single-json 前以 101 提前退出。channel 使用 yes-playlist/flat-playlist，并显式带 playlist-end/max-downloads；两种模式均校验响应条数。无重试，120 秒进程超时。频道 flat 候选还需宿主单条取证，不把频道当 target。
- 保留原 uploader/uploaderUrl，只有源实际 creator 才写 creator；许可、描述、热度按原响应。每条都有稳定 video 资产 ID，duration/filesize 或 filesize_approx 即使缺直链也保留。requested_formats 或 flat URL 不伪造媒体直链。
- entries 缺席只支持单条对象；playlist 缺 entries、entries=null 或未知类型可解释拒绝。数组 null 是不可用位置，计入 limit、不生成候选、不自动补足条数。`--response` 离线回放不代表在线可达或可播放。

## bilibili · 已实现有界单条/UP metadata

- 单条 request：`{"url":"https://www.bilibili.com/video/<BV>","mode":"single","limit":1}`；支持 bilibili.com/www.bilibili.com/b23.tv。
- UP 主 request：`{"url":"https://space.bilibili.com/<uid>/video","mode":"channel","limit":10}`；同样使用显式条数边界，不做分页调度。
- 412/352、登录/验证码/挑战只报告停止，不重试绕过。UP 主账号不独自证明原作者；不填默认协议或许可，版权保留/作者与条款须可回查。

### 宿主批量下载的退出状态

先用已读元数据和现有候选确定有界的小组、格式及传输峰值；已登记且摘要校验通过的资产不再次请求，不以文件存在跳过身份/摘要校验。下段仅用于宿主明确选定且获准取得的剩余公开 URL，不自动发现、选材、续组或绕访问限制。它不是审批、评分或自动重试器；外层 `exit=0` 仅表示所列命令都返回0，不证明媒体/授权合格，取得后仍须 register-local 核验。

使用 `/bin/bash` 执行，事先给 `YTDLP` 已核实的可执行文件绝对路径、`HOST` 本批既有输出目录，URL 作为位置参数逐个传入。不要将下载器接到 `tail/head` 后采信管道末端退出码；日志由宿主工具保存，观察另行读取。下例一次只给同一来源的小组；保留每次已执行的原始退出码，首个失败退出该组并将余项明确记为未执行，最终退出1，不删除成功文件。403不推测原因、不绕过；首错即停避免429/挑战后继续撞站，是否缩批或换另一获准来源仍由宿主决定，不解析文本替其裁定。

```bash
set -u -o pipefail
if [ "$#" -eq 0 ] || [ ! -x "${YTDLP:-}" ] || [ ! -d "${HOST:-}" ]; then
  printf 'input error: provide executable YTDLP, existing HOST and explicit URLs\n' >&2
  exit 64
fi
ok=0
failed=0
not_attempted=0
for url in "$@"; do
  if [ "$failed" -ne 0 ]; then
    printf 'candidate\t%s\tnot_attempted\n' "$url"
    not_attempted=$((not_attempted + 1))
    continue
  fi
  if "$YTDLP" --no-playlist --retries 0 --fragment-retries 0 \
      --extractor-retries 0 --socket-timeout 30 \
      --write-info-json --merge-output-format mp4 \
      -f 'bv*[height<=1080]+ba/b[height<=1080]' \
      -o "$HOST/%(id)s.%(ext)s" -- "$url"; then
    rc=0
    ok=$((ok + 1))
  else
    rc=$?
    failed=$((failed + 1))
  fi
  printf 'candidate\t%s\texit=%s\n' "$url" "$rc"
done
printf 'summary\tok=%s\tfailed=%s\tnot_attempted=%s\n' "$ok" "$failed" "$not_attempted"
if [ "$failed" -ne 0 ]; then exit 1; fi
```

示例格式上限不是固定质量选择；需要其他已授权格式时显式决定，不按文件大小牺牲画面/音轨。`--socket-timeout` 只是网络读取超时，不是整体任务期限；后台期限/终态由实际宿主工具负责，不能把未响应猜为失败后重派。来源探测若明确返回逐项失败列表，聚合命令正常结束0可以合法；不能因此把404/429候选登记成功，也不能把混合下载失败改成整批重下。

## 本地合并下载 · 宿主取得、机械登记

宿主在确认来源/预算后用 yt-dlp 选格式、写 info.json、合并本地文件；保存到本载体 `video/host/`，然后执行：

```bash
python3 .agents/skills/content-production/scripts/producer.py --workspace "$ROUND" register-local video --candidates video/candidates.json --candidate-id 'youtube:<id>' --asset-id 'youtube:<id>:video' --file video/host/result.mp4 --metadata video/host/result.info.json --max-bytes 536870912
```

登记核对 id/webpage_url、计算媒体 bytes/sha256 和 metadataSha256，不下载、不手填取得成功。读取缓存前仍校验当前载体与两份摘要。无单文件直链时，build-inputs 从原 info.json 读取实际 format_id 列表，输出 `directUrl=null` 及 host_merged 取得事实；缺格式 ID 或摘要漂移拒绝。Data 零网络 ingest 保留 null 与取得事实，资产署名回指作品页，不把 watch URL 假称下载直链。真实来源试点与发布仍须逐阶段验证。

Data API key、ytsearch/bilisearch、Dailymotion/Vimeo/档案/Pexels/Pixabay 等没有对应模块，仅按明确需要用宿主工具取证，不新增占位客户端或自动来源切换，不绕过 DRM、登录或挑战。
