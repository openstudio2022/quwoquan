# 阶段输入与命令

只读当前阶段。工作流顺序由 [SKILL](../SKILL.md) 拥有，载体模板与评分只在各自 `CARRIER.md`；本文件拥有机械输入、写者与结果边界。下列命令从仓库根运行，`$ROUND` 指向 `.qwq_output/data/local/workspace/content-production/<shardId>/rounds/<roundId>` 的绝对路径，`$EXEC` 为已选 executionId。

## 输入与 init

- `shard.json` 仅声明范围、目标与预算，字段见 [shard schema](../schemas/shard.schema.json)，不签发授权。每轮 `round.json` 复用 [round_spec](../../../../quwoquan_data/schema/execution/round_spec.schema.json)。AI 可直接写它并 init：身份冻结不要求下载前置。
- 每个 `target` 必须显式声明 `entityId/entityRef`，与 carrier、实体类型/名称一同原样冻结；稳定身份由调用方指定，不按名称、行政区、execution 或路径自动 hash。homepage 的 `region` 解析到 `Topic/地理/行政区/<region>`；post 仍声明 `publishAngle/publishTitle`，`publishSeq` 缺省 1，但依赖绑定显式 `entityRef`，不按同名猜实体。只列本轮实际 carrier；补齐 execution 通过 `retryOf` 显式绑定前序。
- `build-inputs` 是另一种构造输入的方法：消费候选、选择和已取得媒体的下载索引，输出一份 `round.json` 与每载体 `<carrier>/ingest.json`，不调用 init/acquire。它不是 init 的前置门；已手写 round 时，输出须逐字节相同，否则不得覆盖，改用一致输入或新轮次。

```bash
python3 quwoquan_data/scripts/cli.py task init --round "$ROUND/round.json"
```

CLI 原子创建 `.qwq_output/data/tasks/<executionId>/execution_manifest.json` 与 `0.plan/{request.json,target_set.json}`。工作包 `targetRef` 是 Data `execution_target_ref(target, carrier=...)` 唯一派生的 execution locator：homepage 保留基于显式 `entityRef` 的 hash 叶子以隔离同名实体，原物理层级不变；post 仍按 angle/title/seq 定位。Skill ingest 直接调用该 Data 函数，不复制 hash 规则。这个过程目录既不是业务 `entityRef`，也不是新内容仓的地域/分区发布 locator；canonical 预检另用显式 `entityRef` 的逻辑引用，不能反推或重算稳定 ID/ref。宿主检查每个 execution 的 `created|replayed`，不以某一个成功代替整轮结果。

## acquire

### 宿主单阶段工具

入口 [producer.py](../scripts/producer.py) 只加载点名载体/来源。取得/构造路径相对该轮根，必须位于本载体子目录，不允许绝对路径、`..` 或软链接；raw、候选和下载缓存均在读取字节前校验载体。仅只读 `lint --draft` 另接受 exact execution 草稿绝对路径。真实 UA 可用 `--user-agent` 或 `QWQ_SOURCE_USER_AGENT`；原件预览与本地登记不需要 UA。`--gap` 是本次调用同站间隔，不是跨会话限流器。

```bash
python3 .agents/skills/content-production/scripts/producer.py --workspace "$ROUND" --user-agent "$UA" source image tuchong --request image/request.json --output image/candidates.json
python3 .agents/skills/content-production/scripts/producer.py --workspace "$ROUND" source image tuchong --request image/request.json --response image/fixture.json --output image/candidates.json
python3 .agents/skills/content-production/scripts/producer.py --workspace "$ROUND" --user-agent "$UA" preview image --candidates image/candidates.json --discovery --max-bytes 16777216
python3 .agents/skills/content-production/scripts/producer.py --workspace "$ROUND" --user-agent "$UA" download --candidates image/candidates.json --selection image/selection.json --max-bytes 536870912 --total-bytes 1073741824
python3 .agents/skills/content-production/scripts/producer.py --workspace "$ROUND" preview image --candidates image/candidates.json
python3 .agents/skills/content-production/scripts/producer.py --workspace "$ROUND" build-inputs --candidates image/candidates.json --selection image/selection.json
```

- `source`：一次请求或 `--response` 离线回放；原响应先 create-or-same 存入 `<carrier>/sources/responses/<sha256>.raw` 再 parse/schema，失败输出也点名 responsePath/responseSha256；HTTP 错误/挑战提前终止只取得前缀时明确 responseComplete=false，不冒称完整响应。page 另写 `source.md`。分页使用不同候选快照，`--candidates` 显式传入；同身份同 revision 且除 evidence 外相同的重叠只保留首份引用，原响应全部保留，内容/revision 冲突拒绝。Commons 返回 continuation 供宿主下一次显式请求，不自动翻页。
- `preview`：默认先校验本载体 downloads index 的 schema、路径、URL、bytes、sha256，再读原件；缺原件即报错。只有 `--discovery --max-bytes <总预算>` 才允许取 API 缩略图，仍优先原件。预览按资产身份/摘要缓存，index 和拼图标注原件/发现图及实际尺寸；每页最多 8 个 tile，完成即释放。像素只复用 Data `image_decode` 政策，无第二 PIL 或 16MiB 原件上限。只处理图片，不抽视频帧。
- AI 单写 `selection.json`：字段只用本载体 `schemas/selection.schema.json` 所引用的 [common](../schemas/common.schema.json)。根为 `carrier/executionId/targets`，可选 `retryOf`；每项为 `target/sources`，来源含 `candidateId/relevance`，可选 `role`、权利事实、访问/热度，媒体选 `assets[].id` 及观察字段。不得自造 `confirmed/workId/actors` 等字段。
- 候选允许缺许可、作者、热度或视频直链；上传账号是 `uploader/uploaderUrl`，不是 `creator`。selection 可补充事实；纠正已有 creator/license/licenseUrl 时，对该字段提供 `factEvidence.<字段>={responsePath,responseSha256,quote,sourceUrl}`。机械核实本载体证据摘要及 quote 原文在场，宿主负责语义真实性。`assets[]` 同样支持逐资产 creator/license/licenseUrl/factEvidence；优先级是逐资产 selection → 逐资产原事实 → 来源 selection → 来源原事实，混合许可不能被统一来源声明覆盖。逐资产已核实的商业授权状态/证明、音轨与使用范围也可显式补录，取值直接引用 Data ingest schema；缺席不推导、不扩散到同作品其他资产。原响应和候选均不改写，见 [sourcing](sourcing.md#权利与访问记录)。
- `download` 只下载显式选中资产；必填 `--max-bytes` 单资产预算与 `--total-bytes` 本次总预算。先按已知 size/Content-Length 预检，64KiB 有界分块写入与增量摘要，失败流已读字节也消耗预算。普通 404/坏图保留后续独立资产，429/503/技术挑战停止当前调用内该站，其他站继续；宿主负责不在本轮重启已停站。聚合 `status=partial_failure` 退出 1，成功项留索引，不写 verdict/approved。缓存漂移或跨载体引用是完整性错误，在网络读取前拒绝。成功索引记录实际 path、URL、sha256、bytes、图片尺寸并核对 sha1。
- `build-inputs` 同样接受两类路径列表，一轮每载体仅一份 selection，先校验全部 round/ingest 再 create-or-same 写出。缺选中媒体的下载事实、身份冲突或 Data schema 必填事实时返回错误，不补造。
- `register-local video --candidates video/candidates.json --candidate-id <id> --asset-id <id> --file video/host/result.mp4 --metadata video/host/result.info.json --max-bytes <预算>`：宿主 yt-dlp 本地结果机械登记，核对 info.json 的 id/webpage_url，计算实际 bytes/sha256 与元数据摘要；两个文件必须在本载体内。不手填索引。无单文件直链的分轨合并结果仍可登记，但当前 Data ingest 强制实际 directUrl，`build-inputs` 返回 `SOURCE.DIRECT_URL_REQUIRED`，不能把作品页伪装成直链。未实现来源由宿主工具取证，不假称自动化。

### 最小 selection 示例（离线测试绑定）

将图虫 request 保存为 `image/request.json` 并取得含 `tuchong:138766711` 的候选；以下保存为 `image/selection.json` 后可运行上面的 download/build-inputs。示例仅演示精确输入，真实使用须替换为已核实对象与权利，不代表该示例自动获准生产。

```json
{
  "carrier": "image",
  "executionId": "20260908--travel-image-work--sichuan-r01--pilot-001",
  "targets": [{
    "target": {"carrier": "image", "entityType": "地点/自然景观", "name": "秋山", "entityId": "entity-qiushan-sichuan", "entityRef": "/entity/travel/sichuan/qiushan", "publishAngle": "风光", "publishTitle": "赏秋"},
    "sources": [{
      "candidateId": "tuchong:138766711",
      "relevance": "作品页与山景一致",
      "creator": "和风不语",
      "license": "版权保留",
      "licenseUrl": "https://tuchong.com/agreement/",
      "assets": [{"id": "tuchong:1:1271483541", "watermarkStatus": "unknown", "watermarkKind": "unknown"}]
    }]
  }]
}
```

### Data 零网络取得与 seal

`ingest.json` 只含实际本地文件与申报事实，复用 [ingest_manifest](../../../../quwoquan_data/schema/source/ingest_manifest.schema.json)。page 提交有标题、可回查正文/结构化事实的 `source.md`；所有媒体申报 `sourceUrl/directUrl/filePath/license/licenseUrl/creator/relevance`、水印三字段，video 另有真实 `hasAudio`。不申报 Data 能算的 sha256、mime、尺寸或 rightsStatus。

```bash
python3 quwoquan_data/scripts/cli.py task acquire --execution-id "$EXEC" --input "$ROUND/image/ingest.json"
python3 quwoquan_data/scripts/cli.py task seal --execution-id "$EXEC" --stage 1.download --input "$ROUND/image/seal.acquire.json"
```

CLI 计算摘要、探测、按现有预算派生/转码/抽 poster、登记来源与媒体 holder，写 `1.download/source_refs.json`；不访问来源站点、不判断相关性。逐 target 取得失败退出 1，输入非法退出 2；保留首个 typed issue，宿主判断有效对象后显式提交 `actor + verdict`。视频转码可用宿主工具级后台，不使用 shell `&/nohup` 或后台启动重派。

## author

### author 前只读存在性、引用与图片预检

宿主在写正文前显式运行一次批量 `preflight`；不把当前 selection、同轮计划或 `invalid` 当成 canonical 已完成。工具只调用 Data 唯一 `query_pool`（与 `release pool-query` 同一个 API），不出网、不写池/草稿、不计算第二套 pHash、不调用 final projection/seal/publish，也不自动选择或 approved。

```bash
python3 .agents/skills/content-production/scripts/producer.py --workspace "$ROUND" preflight --selection image/selection.json article/selection.json
python3 .agents/skills/content-production/scripts/producer.py --workspace "$ROUND" preflight --selection image/selection.json --acquired-selection image/acquired.selection.json --target-ref 'entities/travel/sichuan/qiushan'
```

- `--selection` 按 Data 唯一 target schema 校验显式 `entityId/entityRef`，机械提取全部 canonical 逻辑 objectRef 及其精确 `entityRef` 对应的 homepage 依赖（去 `/entity/` 再加 `entities/`，不查询 execution hash locator）；不按 `entityType/name` 或区域猜依赖，同名不同区域不串。`--target-ref` 可重复点名其它实际依赖。`--candidate-file` 可给多份载体私有文件，但所有候选合并为**一次** Data 调用，图片索引仅打开一次，跨候选也查冲突；空输入拒绝，不逐候选反复扫描全池。
- 输出 `poolQuery` 是 Data 原结果：`objects[].occupied/eligible/state/code/deepestCode` 分开报告身份占用、资格与最深原因，`preflight[].dependencyIssues/imageConflicts` 给 exact objectRef。`invalid` 仍占用身份；同轮 homepage 尚未发布或已失败时，其依赖仍 absent/invalid，不用同轮候选代替 canonical 资格。
- stdout 另有覆盖范围 `coverage.candidateManifestRefs/identityOnlyTargetRefs/selectedWithoutManifestRefs`。仅 selection 检查身份和显式实体资格，**不代表已完成图片去重**；退出 0 只表示查询成功，池内冲突照实返回，不签发 verdict/approved。输入/图片事实不足、池完整性错误则非零，宿主处理真实原因。
- `candidate-file` 与 Data `release pool-query --candidate-file` 使用同一 `{candidates:[{objectRef,manifest}]}` 形状，不是来源候选数组，也不是 `image_work.json` 等正文。当前 API 实际消费 manifest 的身份、依赖与资产视图，**不要求提前生成完整 final manifest**。视图需显式声明 `contentType/entityRefs/assets`，有资产时保留 Data 取得的稳定 `assetId/sha256` 和真实 sourceUrl/originalAssetUrl；图片保留由 Data 唯一算法产生的 `perceptualHash`。不要填零 pHash、改 ID 绕重或复制发布投影来“凑”字段。
- 普通新草稿在 acquire seal 后使用 `--acquired-selection <carrier>/acquired.selection.json`；输入按 [common acquiredSelection](../schemas/common.schema.json) 为 `{executionId,targets:[{objectRef,assetRefs}]}`，其中输入 `objectRef` 必须是 Data 已冻结的 execution locator，Data 读回后输出 canonical 逻辑 objectRef，二者不可互换；assetRefs 显式列本对象 `source_refs.json` 下资产的完整 `sources/.../assets/...` 引用，保留选图顺序；无图主页显式传空数组，视频恰为 video+poster 且封面必须匹配该视频取得记录的派生身份与摘要，不能借用同对象另一来源的封面。读取 execution 前核对载体，再校验 receipt、对象来源与资产实际摘要，复用 Data 唯一 SHA/pHash 和身份消歧函数，内存构造视图与其它候选合并为一次查询，不要求草稿或 final manifest，不写文件。不同来源同名图片仍保留稳定身份，别名、跨对象引用、漂移和软链接拒绝。`candidate-file` 缺图片事实仍报 `SOURCE.PREFLIGHT_IMAGE_FACTS_REQUIRED`，不把下载前原件摘要当派生后摘要；修改选择后显式重查。
- 发布前再以**实际将发布的**资产/实体引用重验同一接口；早期查询不是 admission 或锁，不代替 publish 事务再次检查引用闭包与作品唯一性。输出需要留存时保存本轮新的快照路径，不把旧预检当当前事实。

下例是预检身份视图的形状说明；资产事实必须来自实际 Data 取得结果，不可照抄示例值作生产证据：

```json
{"candidates":[{"objectRef":"posts/image/风光/赏秋/1","manifest":{"contentType":"image","entityRefs":["/entity/travel/sichuan/qiushan"],"assets":[{"assetId":"<Data稳定资产ID>","sha256":"<实际SHA256>","kind":"image","perceptualHash":"<Data实际64位pHash>","sourceUrl":"https://tuchong.com/26553952/138766711/","originalAssetUrl":"https://photo.tuchong.com/1/f/1271483541.jpg"}]}}]}
```

### 创作与 author seal

- 同 execution 的唯一 author 读已取得来源、`source_refs.json` 与资产索引，逐对象写 `4.draft/page.md|draft.article.md|image_work.json|video_script.json` 之一。标题、标签、creatorProfileId 与来源/资产选择由产物自身声明；不写第二份实体输入或 actor 旁车。
- 模板、作品分组与六维评分以当前载体 `CARRIER.md` 为唯一正文。`lint` 只返回版式/内容建议；检查已在 execution 的草稿时，将 `--workspace` 显式设为该 execution 根、`--draft` 设为对象草稿相对路径，不复制第二份可写正文，也不使用 `..` 越界。CLI seal 才是 canonical 草稿校验者。
- 主会话提交真实 author 的 `seal.author.json`（`actor + verdict`），不把执行 CLI 的主会话冒充作者。

```bash
python3 .agents/skills/content-production/scripts/producer.py --workspace ".qwq_output/data/tasks/$EXEC" lint image --draft "$TARGET/4.draft/image_work.json"
python3 quwoquan_data/scripts/cli.py task seal --execution-id "$EXEC" --stage 4.draft --input "$ROUND/image/seal.author.json"
```

seal 校验 schema、标签/创作者引用及载体来源/资产绑定，补机械字段；单对象违规以 `DATA.SEAL.DRAFT_INVALID` 退轮，至少一个合规对象才可 `pass`，零合规以 `blocked` 提交。

## review

独立 reviewer 单写 `<carrier>/seal.review.json`：真实 `actor`、显式 `verdict` 与按 targetRef 索引的 `reviews`。对象覆盖集合恰为 `002-4.draft` receipt 的 resultRefs；不评已退轮对象。每项只写 `decision/blockingIssues/advisories`，可选 `qualityScores/qualityNotes/safety` 与资产疑虑；不写逐对象 `content_review.json`，不另建 `review.json/actors.json`。

只在关键论断缺证据、安全/隐私、素材不相关或不可播放三类拒绝。文风、长度、权利疑虑、热度与质量评分只记录，不改变 admission 或补零。reviewer 必须核实当前草稿及来源/实际媒体，不以 poster 代完整视频证据。

```bash
python3 quwoquan_data/scripts/cli.py task seal --execution-id "$EXEC" --stage 5.review --input "$ROUND/image/seal.review.json"
```

CLI 核对独立 actor、覆盖与前序绑定，将这唯一输入 create-once 扇出 `5.review/content_review.json`，补 schema、draft digest、assetRights 与 dimensions，透传六维评分。approved/rejected 可并存，零 approved 为 blocked；reviewer 不 seal、不改草稿。

## publish

主会话只对显式 approved 对象逐个调用，先 homepage 再引用它的 post；已发布对象直接复用，不重复 init 或造 receipt。

```bash
python3 quwoquan_data/scripts/cli.py release publish-object --execution-id "$EXEC" --target-ref "$TARGET"
```

CLI 唯一原子事务写 `$QWQ_PUBLISH_ROOT` 指定的平级独立 Git 内容仓（本机约定 `/Users/zhaoyuxi/Projects/quwoquan/publish`），核对 `repository.json` 仓身份；缺根/错仓阻断，不回退 `quwoquan_data/publish`。实体按已核实行政链/类型/分区定位，posts 保留载体/角度/分区结构；物理 locator 不改变稳定 ID/ref，布局只由 Data policy 拥有。对象包 `manifest.json` 单写身份、结构化实体事实、正文/有序媒体与依赖；采用来源及必要真实证据进包内 `sources/`，最终媒体进 `media/`，review 原件与追加式 `records/` 保留，完整对象不依赖采集 library 消费。Skill 不改 canonical 包、不实现 publish wrapper，不把 homepage 封面复用扩大为跨 Post 去重硬门；实际去重由 canonical inventory 判定。实现/迁移差距仍由 [OPEN-025](../../../../specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#open-025) 与 [OPEN-027](../../../../specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#open-027) 跟踪，本说明不授权初始化、搬迁、删除旧树或宣称切换完成。

## release 与 handoff

只在已获授权时进入。先保存 `release pool-query --json <path>` 原始结果，AI 显式选择 eligible objectRefs，写 [release_cohort](../../../../quwoquan_data/schema/release/release_cohort.schema.json)；禁止隐式 all-publishable。M1/M10/M100/M1000 底线依次为 `1/1/1/1`、`10/10/10/2`、`100/100/100/10`、`1000/1000/1000/100`（homepage/article/image/video），按累计唯一 finalized 对象计数。

`producerBaselineRevision` 绑定真实工程 baseline，与 `producerContractDigest` 及内容仓身份/exact 内容快照分开记录；只有内容 commit 匹配所选对象实际字节才记录它，不要求工程提交包含仓外 canonical 包，也不强制双提交。提交仍需单独授权。`releaseClass` 唯一值 `production`；CLI 排序、canonical 化 objectRefs 并派生计数，不替 AI 选择 cohort 或 milestone。

```bash
python3 quwoquan_data/scripts/cli.py release finalize --release-id "$RELEASE" --cohort-file "$ROUND/cohort.json" --milestone M1 --producer-baseline-revision "$BASELINE"
python3 quwoquan_data/scripts/cli.py release handoff-verify --release-id "$RELEASE"
```

finalize 完成 pool-build、release-integrity 与 create-once handoff，只将现有 cohort/handoff 两份 terminal 事实 create-or-same 保存到独立内容仓 `$QWQ_PUBLISH_ROOT/releases/<releaseId>/`，不再写 `reference/releases`；历史 release、bundle 与 receipts 原件全部保留。handoff-verify 只读校验，缺失/损坏不得隐式回填。handoff 绑定 canonical publish proof、工程 baseline/契约摘要及内容仓身份/所选 ID、版本、包摘要与定位的 exact 内容快照，不内嵌 actor/receipt 链或 consumer facts。成功即 producer END；工作区审计证据不因此成为永久耐久链。收官只更新本轮 `report.md`，见 [session](session.md#收官)。
