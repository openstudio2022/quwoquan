# L3 Story：图片投递变体 (`image-delivery-variants`)

> 所属能力：[`media-processing-helper-read`](../spec.md)
>
> Journey / Scenario：[`JNY-004 / SCN-002`](../../../spec.md#scn-002)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，我希望单一 MediaAsset 图片交付 descriptor、唯一 CDN variant policy、原图授权和可回滚 reprocess 闭环，从而完成可恢复的内容创作、发现或互动。作为内容运营者，我希望发布侧对「这个对象能不能发」给出可直接读取的终态，从而在浏览者看到缺图或坏图之前就把问题挡在 release 之外。

## 2. 范围与非目标

### In Scope

- MediaAsset 的 ImageDeliveryDescriptor、derivativePolicyVersion、CDN profile 与历史资产 reprocess。
- ImageVariantPolicy metadata/codegen、Data materializer、Dart resolver 和 Image 读侧。
- Data 发布侧的图片存储基线：作为 CDN 四档变换输入的存储体准入语义，以及以单对象存储预算为准的对象级体量约束。
- Post 可见性驱动的原图授权、403/429 限流和对应审计事实。
- alpha/beta/gamma/prod 非 dry-run 图片端到端证据。

### Out of Scope

- 编辑算法、滤镜目录、用户配方、滤镜使用事实、视频 ABR。
- 单图最小像素下限：`REQ-007` 只约束上界语义，下限由下载阶段的图片质量准入拥有，本节点不复制也不改写。
- 单对象存储预算本身的数值与门禁：`REQ-008` 只消费它，其规格 owner 见 `OPEN-006`。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 图片只有在完整交付 descriptor 可验证后才能 ready

- 损坏、超限、descriptor 缺字段或 CDN baseline 不可读全部进入 rejected 或保持 processing 重试，不能发布。
- thumbnail/display/cover/full 不创建独立 MediaAsset、独立 Store 或独立生命周期。
- 真实 PNG/JPEG 经 FFmpegMediaProcessor、Mongo、对象存储和 public reader 的 descriptor 一致。

<a id="req-002"></a>
### REQ-002 所有消费者只使用 metadata 生成的图片 profile

- 读取页只经 generated ImageUrlResolver/AppImage 消费 display profile，沉浸页只消费 full profile。
- policy 变更先生成新 processingVersion 并完成可读验证，失败时保持旧 descriptor。

<a id="req-003"></a>
### REQ-003 原图访问按 Post 可见性授权并可靠限流

- 授权服务经 Post named visibility reader，不以 ViewerID 伪装 owner 查询。
- grant/rejection/ratelimit 仅追加 MediaOriginalAccessFact 与安全指标，不泄露原图 URL 或图片字节。
- 限流额度与 grant 到期是实例级可变不变式，由 `content.original_access_quota` 聚合独占承载；额度只能由该聚合的 Facade 在单次原子提交中变更，兄弟对象与 HTTP adapter 不得直写额度存储。
- grant 的绝对到期时间在预留成功那一刻确定，重放同一幂等键只返回原到期时间，禁止续期或刷新；窗口过期只允许由存储 TTL 自然清理，不得通过重置计数、缩短窗口或重算窗口起点变相扩大额度。
- MediaOriginalAccessFact 退回为纯审计事实，只记录已作出的授权决定，不持有额度、TTL 或任何实例级可变状态。

<a id="req-004"></a>
### REQ-004 策略升级与历史资产重处理可停止、恢复和回滚

- cursor、idempotency、旧新 descriptor、清理候选和 rollback target 都可审计。
- 不直接覆写 ready descriptor、不删除仍被 Post 引用的旧 slice、不以 aggregate version 重解释 processingVersion。

<a id="req-005"></a>
### REQ-005 图片四环境设备矩阵以真实 Remote 主线闭环

- alpha 只作为同构工程证据；beta Android 与 iOS、gamma 与 prod `canary/5/20/50/100` 任一阶段证据缺失均保持 GATE_BLOCK。
- 报告符合 image-end-to-end-commercial-matrix 的统一 schema，禁止用 mock、fixture、路径存在性或 dry-run 代替。

<a id="req-006"></a>
### REQ-006 处理与交付故障必须 fail-closed

- `processing` 超过 SLO、checkpoint 失败、CDN baseline 不可读或 descriptor 校验失败时，只允许保留旧 descriptor 或保持可重试终态；不得生成新的 ready 结果。
- 授权判定必须读取 Post 的 named visibility reader，禁止从 `MediaAsset` aggregate 直接导入可见性事实。

<a id="req-007"></a>
### REQ-007 存储基线是 CDN 变换的输入，不受任何 profile 输出宽度封顶

- 本 REQ 只约束 **Data 发布侧**：素材经下载与质量准入后进入 canonical 对象、再冻结进 immutable release 这条路径。App 上传路径的解码、方向归一、像素守卫与 normalized baseline 仍由 `REQ-001` 与 `GWT-001` 拥有，两条路径不互相推导，本 REQ 不放宽上传侧的任何守卫。
- 存入 immutable release 的图片体是 ImageVariantPolicy 四档即时变换的**输入**，不是任何一档的**输出**。四档声明的宽度是该档的交付输出宽度，不构成存储体的宽度上限。以「最宽 profile 宽度」反推存储体上限属于因果颠倒：要让最宽档交付到它声明的宽度，存储体至少得有那么宽，封顶只会让该档永远拿不到声明宽度。
- 各档声明宽度是**上界而非保证**：实际交付宽度取「声明宽度」与「存储体宽度」的较小者。存储体宽度低于某档声明宽度时，该档按存储体实际宽度交付，不判为 descriptor、profile 或三侧解析不一致。本条细化 `REQ-002` 的「三侧得到相同 profile」——相同的是 profile 参数，不是像素结果。
- 源体宽度不足最宽档声明宽度时原样入库，不放大。放大只增加字节、不增加信息。
- 存储基线不设宽度或长边封顶。判据不得以长边（宽高较大者）为准：即时变换按宽度约束，长边与交付宽度不同轴，按长边归一化会把本已达标的宽度进一步压低。
- 存储基线采用 passthrough：通过权利与质量准入的源体字节原样成为存储体。发布侧不做格式转换、重编码、EXIF/ICC 剥离或任何字节改写，存储体摘要即源体摘要，权利快照绑定的摘要与发布体天然同源。是否引入归一化衍生体及其参数见 `OPEN-007`。
- 存储体不可解码或不可探测是**失败**，不是缺席、不是按放行处理：该资产必须得到 typed 失败终态；解码能力缺失同样判失败，不得因为「探不出来」而放宽准入。
- 资产级失败必须传导为对象级终态，不得停在资产层：该资产已被正文引用时对象整体 blocked，未被引用时形成 typed exclusion 且对象继续。任一情况都不得在对象内留下悬挂引用，也不得让对象带着一个既不在场、也没有失败记录的资产进入 release。
- 即时变换是交付端 CDN 能力，不属于存储基线。不具备变换能力的交付端（`gamma-local` 的对象存储为 passthrough）对四档返回同一存储体字节，这是已知的环境能力差异，不判为 profile 或 descriptor 违约。

<a id="req-008"></a>
### REQ-008 发布侧体量约束来自单对象存储预算，判定落在对象闭包上

- 发布侧对媒体体量的唯一硬约束是**单对象存储预算**：图文对象 10MiB，按该对象的逻辑字节闭包度量（对象自身文档加上它引用的每个不同媒体体，同一内容在同一对象内只计一次）。既有门禁 `verify object-size-budget` 是该预算的唯一执行面并拥有逐载体的完整数值表，本 REQ 只消费它，不新建第二套体量口径，也不在本节点改写非图文载体的预算。
- 判定必须落在**对象闭包成形之后、immutable release 冻结之前**，并以对象为单位构成**准入**。逐资产孤立判定看不见闭包总量，回答不了「这个对象能不能发」；而在 canonical 对象已经写定之后才事后扫描，只能报告既成事实、不能阻止其进入 release，两者都不满足本条。
- 逐资产层只保留 `REQ-007` 的可解码性与不放大两件事，不得承载体量封顶。
- 对象闭包超出预算是 typed 失败，处置为**整对象 blocked**：不逐资产静默裁剪、不丢弃正文已引用的图、不在发布侧生成降级衍生体（后者需要尚未冻结的重编码参数，见 `OPEN-007`）。单个资产自身即超过整个对象预算时同样是对象级 blocked——换素材是更早阶段的内容决定，发布侧无权代做。
- 两种超预算成因必须在终态上可区分：**闭包累计超出**指向「减少该对象引用的资产数」，**单资产自身即超出**指向「换掉这一张」。合并成同一个 blocked 会让运营者拿不到可执行的下一步。
- 该终态必须以运营者可直接读取的 typed 形式呈现，读它即可决定换素材、拆对象还是修来源。进程退出码、stdout 文本与运行日志都不是合法呈现面——这与 [`multi-carrier-release`](../../object-homepage-coverage-scaling/multi-carrier-release/spec.md) `REQ-007` 对呈现面的既有约束同源。
- 对象级 blocked 只终结该对象，不阻断同批其他合格对象。批次终态与 shortfall 语义沿用同一节点 `REQ-001`：合格对象数介于零与 quota 之间为 `partial`，零合格才 `blocked`。本节点不另起一套批次失败语义；零合格时该批次要携带的 typed 原因归 `multi-carrier-release` `REQ-006` 的闭集所有，该闭集已扩容出「全批因对象闭包超出存储预算而在 publish 准入被拦下」一项，其唯一写者仍是该节点的 lane 回执。本节点只产出对象级排除码并由该批次级原因引用，不自行发明批次级原因码。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/contracts/media/media_asset/object.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/media_asset/fields.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/media_asset/operations.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/media_asset/image_variant_policy.yaml`
- canonical：`quwoquan_data/scripts/core/media_asset_url.py`
- canonical：`quwoquan_app/lib/service/content_service/media/media_asset/adapters/cdn_image_url_builder.dart`
- canonical：`quwoquan_service/services/content-service/contracts/media/original_access_quota/operations.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/original_access_quota/fields.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/original_access_quota/errors.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/media_original_access_fact/object.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/media_original_access_fact/fields.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/original_access_quota/original_access_policy.yaml`
- canonical：`quwoquan_data/scripts/verify/verify_object_size_budget.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 图片只有在完整交付 descriptor 可验证后才能 ready

- GIVEN 已完成的图片 MediaUploadSession 产生 processing MediaAsset 和耐久 outbox 事实。
- WHEN processor 真实解码、方向归一、执行像素/尺寸守卫、写入 normalized baseline 并绑定 ImageDeliveryDescriptor。
- THEN ready 资产拥有 processingVersion、derivativePolicyVersion、公共 slice、尺寸、MIME、dominantColor、lqip 与 contentProfile。

<a id="gwt-002"></a>
### GWT-002 所有消费者只使用 metadata 生成的图片 profile

- GIVEN active ImageVariantPolicy 声明 thumbnail/display/cover/full 的 policy version。
- WHEN App、Data 与 Service 解析同一 MediaAsset image descriptor。
- THEN 三侧得到相同 profile 尺寸、格式、质量和 URL 参数；业务代码不存在默认 400/750、Python profile 常量或 Post 目录副本。

<a id="gwt-003"></a>
### GWT-003 原图访问按 Post 可见性授权并可靠限流

- GIVEN ready 图片被 public、followers 或 private Post 引用，且访问者身份各不相同。
- WHEN 访问者请求 view 或 save 原图授权。
- THEN 同时满足内容可见性和 accessPolicy 的请求获得短时 grant
- AND 非可见者稳定得到 403
- AND 超过窗口稳定得到 429。

<a id="gwt-004"></a>
### GWT-004 策略升级与历史资产重处理可停止、恢复和回滚

- GIVEN 已存在不同 processingVersion 的 ready 图片以及待升级的 ImageVariantPolicy。
- WHEN reprocess worker 分批处理历史资产，或在验证失败时停止 activation。
- THEN 每个资产仅在新 descriptor 完整、可读且与 policy 匹配时原子切换；失败、暂停和回滚继续提供旧 slice。

<a id="gwt-005"></a>
### GWT-005 图片四环境设备矩阵以真实 Remote 主线闭环

- GIVEN 同 release/config hash 的 beta Android/iOS、gamma remote 和 prod gray 环境可用。
- WHEN 用户选图、编辑、上传、等待 ready、发布、在第二账号查看并请求原图。
- THEN 每个必选环境都有非 dry-run serviceEvidence 与 uiEvidence，包含 mediaId/postId、descriptor、profile load、授权结局和回滚结论。

<a id="gwt-006"></a>
### GWT-006 存储基线按交付输入判定，不按 profile 输出宽度封顶

- GIVEN 三个已通过权利与质量准入的源体：一个宽度高于最宽档声明宽度的图、一个宽度低于最宽档声明宽度但长边高于它的图，以及一段不可解码的字节；不可解码的那个分别处于「已被正文引用」与「未被引用」两种状态。
- WHEN Data 发布侧对这三个源体做存储基线判定并物化为对象资产。
- THEN 前两个源体都被接受，不因宽度或长边超过任一档声明宽度而被拒；宽度不足的那个原样入库，既不放大到声明宽度，也不按长边缩小到让宽度进一步降低。
- THEN 两个被接受的存储体与各自源体逐字节相同、摘要相等，没有格式转换、重编码或 EXIF/ICC 改写。
- THEN 不可解码的那段字节得到 typed 失败且该资产不进入对象；它不被表述为缺席、零尺寸或静默通过，解码能力缺失同样判失败。
- THEN 该资产的失败传导为对象级终态：已被正文引用时对象整体 blocked，未被引用时形成 typed exclusion 且对象继续；两种情况都不在对象内留下悬挂引用。
- THEN 从这两个存储体解析最宽档得到的有效交付宽度分别是声明宽度与存储体实际宽度；实际宽度小于声明宽度不判为 profile 或 descriptor 不一致。
- THEN 交付端不具备即时变换能力时四档返回同一存储体字节，同样不判为不一致。

<a id="gwt-007"></a>
### GWT-007 超预算对象整体 blocked 且不拖垮同批其他对象

- GIVEN 同一批次内三个已成文、已过审的图文对象：一个的逻辑字节闭包在预算内，一个因引用的资产累计而超出预算，一个含单张自身即超过整个对象预算的图。
- WHEN 发布侧在对象闭包成形之后、immutable release 冻结之前执行准入。
- THEN 预算内的对象正常物化进 release。
- THEN 两个超预算对象各自得到 typed 超预算失败并整体 blocked，不进入 release；发布侧不裁剪资产、不丢弃正文已引用的图、不生成降级衍生体。
- THEN 两者的终态可区分成因：累计超出指向减少引用资产数，单资产超出指向换掉那一张。
- THEN 两个 blocked 终态都能被运营者直接读取并据此决定下一步；进程退出码、stdout 文本与运行日志都不作为呈现面。
- THEN 这两个对象 blocked 不阻断预算内对象，批次按 `multi-carrier-release` 的 `REQ-001` 进入 `partial`，只有零合格对象才 `blocked`。
- THEN 同一媒体体在一个对象内被引用多次时只计一次预算，物理重复不为该对象购买额外额度。

## 6. 依赖

- 前置要求：[`media-processing-helper-read`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-005"></a>
### OPEN-005 图片四环境设备矩阵以真实 Remote 主线闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：alpha 只作为同构工程证据；beta Android 与 iOS、gamma 与 prod `canary/5/20/50/100` 任一阶段证据缺失均保持 GATE_BLOCK。
- 完成判定：`GWT-005` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-006"></a>
### OPEN-006 发布侧存储基线与对象预算 enforcement 尚未落地

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺符合 `REQ-007` 与 `REQ-008` 的发布侧图片准入实现和验收证据。
- 当前发布侧把「最宽 profile 宽度」当作存储体上限，把 CDN 输出反推成存储输入的上限，会让最宽档永远拿不到声明宽度。
- 当前发布侧以长边而非宽度判定，与按宽度约束的即时变换不同轴。实测中，一张宽度低于最宽档声明宽度、只是长边更长的合格源体因此被判为超限，并使该批次零对象可发布。
- 该判定逻辑未被任何规格认领，实现必须按本节点归位，不得为迁就它而保留双轨。
- `REQ-008` 要求的准入形态同样尚不成立。既有门禁虽已按对象闭包度量，但它在 canonical 对象写定之后事后扫描，只能报告既成事实。
- 发布路径上真正拦截的判定仍是逐资产的，看不见闭包总量。
- 完成判定：`GWT-006` 与 `GWT-007` 的全部结果子句成立且有真实测试 `spec_ref`。
- 依赖：`GWT-006.t1`~`GWT-006.t4` 与 `GWT-007.t2`~`GWT-007.t4`、`GWT-007.t6` 由 `local_contract` 以真实编解码的最小图片体和对象级闭包覆盖判定分支、字节等同、typed 失败与成因区分。fixture 只证明判定逻辑。
- `GWT-006.t5` 需拆成两半。resolver 侧「有效交付宽度取声明宽度与存储体宽度的较小者」由 `local_contract` 覆盖；真实变换端按该宽度交付则必须由具备即时变换能力的交付端提供 `api_integration` 证据。
- 四环境内若无此类交付端，则显式记为本节点不证明并另挂 OPEN，不得以 `local_contract` 的形式表现为已覆盖。
- `GWT-006.t6` 与 `GWT-007.t5` 由 `api_integration` 在一次真实 execution 的 publish 阶段与真实对象存储上证明。前者证明 passthrough 交付端四档返回同一字节，后者证明超预算对象 blocked 时同批合格对象仍进入 release。
- `GWT-007.t1` 的「物化进 release」由同一处证据覆盖，不得由单个 fixture 独自挂 `gwt-007.t1` 而对外表现为已证明 release 产出。
- 两个锚点都不改变 App 用户可见终态，因此不追加 `user_acceptance`。环境消费证据继续由 `OPEN-005` 承接。
- 既有 `local_contract` 套件正把「最宽 profile 封顶」与「按长边判定」两条规则断言为正确；这些断言必须随 `REQ-007` 反转或退役，不得与新 `GWT-006.t1` 并存。
- 「不可解码即失败」一例现只断到「返回了非空问题串」，弱于 `GWT-006.t3` 要求的 typed 失败，不得直接追加 `spec_ref` 冒充已覆盖。
- 单对象存储预算的数值与其门禁目前只存在于实现、尚未落到任一 spec 节点。本节点只消费不认领，须为该预算指定规格 owner。
- `multi-carrier-release` `REQ-006` 的零合格 typed 原因闭集已在该节点扩容为六值，并同批引入 publish 准入观测阶段与缩减对象体量运营动作。`ALL_OBJECTS_QUALITY_REJECTED` 仍只归 review 阶段。
- 实现只消费该闭集，媒体侧仍只产出对象级排除码，不得自行发明批次级原因码，也不得把对象级排除码复制成第二份批次级枚举。

<a id="open-007"></a>
### OPEN-007 归一化衍生体的格式、重编码质量、EXIF/ICC 与源体摘要落点待 calibration

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺归一化衍生体格式、重编码质量、EXIF/ICC 去留与源体摘要落点的 calibration 实现和验收证据。
- `REQ-007` 的存储基线采用 passthrough，四项决定均以「不发生」成立。
- 统一转 WebP/AVIF 能省下每次交付的变换成本，但会改变字节与摘要。
- 重编码质量没有实测出的视觉—体量拐点，现在填任何数值都缺乏依据。
- 保留 EXIF 意味着源图内的位置与设备信息随发布体进入公开交付面，剥离则同时丢掉 ICC 色彩正确性。
- 一旦存储体不再等于源体，源体摘要需要明确落点，否则权利快照绑定的摘要会与发布体对不上。
- 在实测之前引入其中任一项都只能使用默认常量，正是 `REQ-007` 禁止的。
- Data 发布侧走 passthrough 时，图片方向完全依赖源体的 EXIF 方向标记被交付端正确解读。这与 App 上传路径由 `GWT-001` 显式做方向归一不是同一条保证。
- 剥离 EXIF 或引入不保留方向标记的衍生体都会让浏览者看到方向错误的图，因此方向必须与其余三项一并裁决，不得单独先动 EXIF。
- 完成判定：引入衍生体后 `GWT-006.t2` 的字节等同子句被改写为衍生体的等价断言并成立，且四项裁决来自 calibration receipt 而不是默认常量。
- 依赖：Data owner 先在可代表主清单的素材样本上实测交付字节量、变换成本、视觉质量拐点与方向标记在各交付端的实际解读，以 create-once receipt 冻结四项裁决。`REQ-008` 的单对象存储预算是该 calibration 的目标函数之一，两者必须一并评估，不得先单独冻结格式或质量再回头发现预算不成立。改写 `GWT-006.t2` 时必须同时重写并重新绑定其测试：子句序号不变意味着门禁看不出语义已反转，沿用原字节等同断言的 `spec_ref` 会让衍生体行为在无证据的情况下表现为已覆盖。
