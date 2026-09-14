# L3 Story：本地内容池工作台 (`content-pool-workbench`)

> 所属能力：[对象主页与多载体供给](../spec.md)
>
> Journey / Scenario：[`JNY-014 / SCN-035`](../../../spec.md#scn-035)
>
> 设计归属：[L2 DEC-045](../design.md#dec-045)

## 1. 用户价值

作为内容运营者，我希望在生产结束后通过只运行于本机的轻量工作台查看 canonical 内容池全貌、逐层下钻，并对精确内容版本作离线人工复核与返工回读，从而在不修改发布仓、不连接数据库、也不触发任何发布动作的前提下，快速判断内容是否可继续使用。

## 2. 范围与非目标

### In Scope

- 只读浏览 canonical publish root 中已经发布的 R0，以及在独立工作根中保存的离线候选 R1/R2 和人工复核台账。
- 从实际对象发现通用动态 `contentFormId`；读侧不得把 homepage/article/image/video 或当前观测到的形态固化成闭集。已知形态使用专用 renderer，未知形态使用保真 fallback，且仍可筛选、计数、查看原始结构与复核。
- 统一分面筛选形态、来源、标签、版本与人工结论；每个数字均是当前筛选条件对应对象集合的计数，点击数字所得列表必须是同一集合。
- 展示标签完整树；父节点集合为全部后代叶节点集合的去重并集，零覆盖节点保持可见且可进入空列表。支持来源 → 形态 → 标签下钻，任一步保持前序条件。
- 内容详情提供三种受支持视口的确定性预览，并逐个展示 adopted source、来源授权元数据、冻结证据、生产评审元数据、对象/版本身份与已知或 fallback renderer 状态；本地冻结原文与外部当前源站严格分区。
- 对已启动且索引预热、页面已加载的 warm interaction，以真实浏览器连续采集 30 个样本并按 nearest-rank 计算 p95，要求不高于 3000ms；安装、构建、启动预热、显式 refresh 与 warm interaction 分开报告。
- 对精确版本记录 `qualified|unqualified` 人工结论；`unqualified` 必须同时记录非空 `changes` 与显式 `targetState`。基于 R0 产生的 R1、再基于 R1 产生的 R2 仅是离线候选；新候选一律进入待复审，旧版本结论不得继承或套用。
- 相同业务字节的同一复核或候选写入可安全重放且不新增版本/记录；身份相同但业务字节不同的重放必须冲突。台账支持中断恢复及重新打开后的精确回读。

### Out of Scope

- 修改 canonical publish root、数据库或任何在线服务；在线回写、发布、激活、导入、部署及环境操作。
- 事件平台、任务调度、后台 worker、历史趋势、跨用户协作、远程访问和生产运行入口。
- 在本 Story 复制字段、path、operation、surface、route、错误码或 wire schema；这些事实由 canonical contracts 拥有。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 动态形态全貌与统一分面集合

- 工作台从当前只读快照中发现 `contentFormId`，所有发现值均进入形态分面、计数、列表与详情；读侧没有要求部署新版本才能识别新形态的硬编码闭集。
- 已知 `contentFormId` 解析到对应 renderer；未知值不得丢弃、归并为某个已知形态或阻断全页，而以中性 fallback 保真展示可用标题、结构化字段、正文/媒体引用与原始对象入口，并明确标记未知 renderer。
- 形态、来源、标签、版本和人工结论使用同一规范化对象集合计算。任意组合条件下，分面数字、总数和点击进入的列表在同一快照上集合相等；不存在独立计数缓存或另一套筛选语义。
- 标签导航展示完整 taxonomy，而非仅展示有内容的节点。父节点命中集合等于全部后代叶节点命中对象的去重并集；同时命中多个后代的对象只计一次，零覆盖父/叶节点仍显示 `0`，点击后得到可解释空列表。
- 来源 → 形态 → 标签下钻逐步收窄同一集合并保留已选条件；返回上层不会把后序条件变成新的默认 authority。

<a id="req-002"></a>
### REQ-002 快速详情、三视口与生产元数据

- 列表为快速浏览提供稳定对象身份、精确版本、形态、主要标签、来源摘要与人工结论；详情保持当前筛选上下文，可前后切换命中集合而不重新解释集合成员。
- 详情对同一精确业务字节提供 desktop、tablet、mobile 三种受支持视口预览；切换视口只改变呈现约束，不改变对象、版本、正文、媒体顺序、来源或复核状态。
- 详情按 `source.json` 的来源身份并结合 manifest 的 cited refs/attribution 判定 adopted 关系，逐个展示 adopted source 的标题、平台、canonical URL、用途、授权线索、取得时间与证据状态；没有 adopted binding 的来源不得混入 adopted 列表，缺失、未知与不可读分别如实呈现，不补造授权或通过结论。
- 每个来源的本地冻结证据与外部当前源站明确分区：冻结证据从包内 `sources/<unit>/` 惰性读取，逐项展示 kind、media type、摘要、字节数与默认展示原因；支持多来源、Markdown 可读展示、raw 保真展示及缺损/不可读证据状态。外部链接只允许安全 HTTPS 新窗口跳转并使用 `noopener,noreferrer`，不得以内嵌 iframe 或把源站当前内容冒充冻结原文。
- 详情同时展示生产阶段的 reviewer、decision、blocking/advisory 与绑定摘要；来源事实与生产评审分别如实呈现且不互相推导。
- renderer 失败只影响该预览区域并给出可诊断 fallback；不得把单媒体或单 renderer 失败报告成池为空，也不得修改源对象以修复展示。

<a id="req-003"></a>
### REQ-003 精确版本离线复核、返工与回读

- 人工结论绑定对象身份、精确版本和业务字节摘要。`qualified` 可直接保存；`unqualified` 只有在 `changes` 非空且 `targetState` 明确时才可保存，否则返回可见 validation failure 且零写入。
- canonical 已发布版本记为 R0 仅用于本工作台迭代视图，不改名、不改写其真实版本。返工从选定版本复制到独立工作根形成下一离线候选 R1/R2；候选不得写入发布仓，也不得被表述为已发布。
- 任一候选业务字节形成后状态必为待复审；其父版本的 `qualified|unqualified`、changes 与 targetState 只作 lineage 证据，不能成为候选结论。R1 被复核后才能作为 R2 的明确父版本；不建立无限迭代或自动生成循环。
- 同一对象、父版本、目标轮次和相同业务字节重放返回同一候选；同一精确版本与相同复核业务字节重放返回同一台账记录。相同幂等身份但业务字节漂移返回 typed conflict 且不覆盖旧记录。
- 台账写入经工作根单写锁、临时文件完整校验与原子 rename 后可见；进程在 rename 前中断不产生可见半记录，rename 后重启可 readback 同一记录。并发读可返回已标明快照身份的 `stale_read`，但不得伪称读到最新状态。

<a id="req-004"></a>
### REQ-004 本地隔离与轻量运行边界

- canonical publish root 永远以只读权限打开；工作台全部可写状态仅位于显式 `QWQ_CONTENT_WORKBENCH_ROOT`，该根不得等于、包含或位于 publish root 内，也不得使用源码工作树、数据库或服务端存储作为 fallback。
- 工作台复用 Data Portal 与 Ops 现有 React/TypeScript/Vite 栈及中性 shared UI 源码；Data 业务规则和 Ops 运行态组件不得互相反向依赖或复制为第二份实现。
- 本地启动只绑定 loopback，并以同一 origin 提供 UI 与本地只读/台账接口；不要求登录远端、启动数据库、消息系统、任务系统或生产服务。
- 缺 root、根重叠、发布根可写企图、锁冲突、原子写失败与 ledger 损坏均 fail closed 并保留首个 typed blocker；恢复只清理未提交临时文件或重放相同业务字节，不修改发布对象。
- 构建与启动入口不进入 prod 镜像、prod route、部署清单或环境准出；工作台不存在 publish/promote/release/activate 操作。

<a id="req-005"></a>
### REQ-005 不可变快照刷新与 warm interaction 性能

- 进程启动时构造不可变内存快照；overview、facets、列表、详情和来源证据读取均绑定一个 `readToken`，请求处理中不得观察到半构建索引或混合两个快照。来源正文不进入常驻索引，只在点名来源证据时按冻结 descriptor 惰性读取并重验摘要/字节数。
- `POST /api/refresh` 是唯一刷新入口；并发 refresh 显式单飞，同一时刻只有一个构建者。新快照须在隔离内完整构建和校验后一次原子交换；失败保留旧快照及其 `readToken`，不清空页面、不部分更新、不隐式回退扫描。
- 性能口径只测 warm interaction：进程已启动且初始索引预热完成、页面已加载，真实浏览器对冻结交互集逐次记录端到端完成时间，共 30 个有效样本；排序后取第 `ceil(0.95 × 30)=29` 个样本作为 nearest-rank p95，必须 `≤3000ms`。不得删除慢样本、仅报成功样本或以平均值代替。
- 安装、构建、进程启动、索引预热、显式 refresh 和 warm interaction 必须形成分栏结果；前五项耗时不得混入 warm p95，任一项失败也不得被 warm p95 PASS 掩盖。

## 4. 契约引用

- 工作台统一筛选：`quwoquan_data/schema/governance/content_workbench/workbench_filter.schema.json`
- 工作台只读模型：`quwoquan_data/schema/governance/content_workbench/read_models.schema.json`
- 离线人工复核：`quwoquan_data/schema/governance/content_workbench/offline_review.schema.json`
- 离线候选：`quwoquan_data/schema/governance/content_workbench/offline_candidate.schema.json`
- 本地 API：`quwoquan_data/schema/governance/content_workbench/local_api.schema.json`
- 工作台 operations：`quwoquan_data/schema/governance/content_workbench/operations.json`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 通用形态全貌

- GIVEN 一个只读池快照包含多个已知 `contentFormId`、一个未注册 renderer 的 `contentFormId`，以及已知 renderer 的正常与局部失败对象。
- WHEN 运营者打开工作台并按形态浏览列表与详情。
- THEN 所有动态发现形态均出现在分面且数字与列表集合一致；已知形态使用对应 renderer，未知形态以明确标记的保真 fallback 可浏览，局部 renderer 失败不清空其它对象且不写源对象。

<a id="gwt-002"></a>
### GWT-002 多维下钻一致

- GIVEN 同一对象可命中多个标签叶节点，taxonomy 含有零覆盖节点，池内来源、形态、标签和版本相互交叉。
- WHEN 运营者组合分面并按来源 → 形态 → 标签下钻，再点击父节点和零覆盖节点数字。
- THEN 每一步数字、总数与列表是同一快照同一集合；父节点为后代集合去重并集，重复对象只计一次，完整标签树与零覆盖节点保留且零节点进入可解释空列表。

<a id="gwt-003"></a>
### GWT-003 快速浏览元数据与来源核对

- GIVEN 命中列表包含多个 adopted source，包内同时具有 Markdown、raw 与缺损/不可读证据，来源授权存在已知和未知状态，生产 review 存在通过、驳回和元数据缺失。
- WHEN 运营者从列表连续打开详情、逐个展开来源证据、访问外部当前源站并切换 desktop、tablet、mobile 三视口。
- THEN 对象/版本身份、正文和媒体顺序不变，每个 adopted source 均由 source identity 与 manifest cited refs/attribution 绑定；本地冻结原文按 Markdown/raw/缺损状态惰性展示，外部 HTTPS 链接安全新开且不 iframe，二者不混称，同时来源授权与生产评审元数据分别如实呈现且不互相推导，缺失不补造，列表前后切换始终限于当前命中集合。

<a id="gwt-004"></a>
### GWT-004 离线复核返工回读

- GIVEN 已发布 R0 尚无人工结论，且 `QWQ_CONTENT_WORKBENCH_ROOT` 可写、publish root 只读。
- WHEN 运营者先尝试保存缺少 changes 或 targetState 的 unqualified，再保存完整 unqualified，基于 R0 形成 R1、复核 R1 后形成 R2，并对相同业务字节重放及对漂移字节冲突重放，期间分别在原子 rename 前后中断并重启。
- THEN 不完整 unqualified 零写入；完整结论精确绑定 R0；R1/R2 均为待复审且不继承父结论；相同业务字节返回同一记录/候选，漂移返回 typed conflict；rename 前无半记录，rename 后可回读同一精确版本、changes、targetState 与 lineage，publish root 字节不变。

<a id="gwt-005"></a>
### GWT-005 隔离轻量性

- GIVEN 本机没有数据库、消息系统、生产服务和外网连接，并分别配置合法独立工作根、与 publish root 重叠的工作根及非 loopback 监听请求。
- WHEN 启动并使用工作台浏览、筛选和保存一条离线复核。
- THEN 合法配置仅以 loopback 同源进程完成浏览和台账写入；重叠根与非 loopback 请求 fail closed；源码工作树和 publish root 无写入，运行入口不包含发布操作，也不进入 prod 构建、路由或部署清单。

<a id="gwt-006"></a>
### GWT-006 原子刷新与 warm interaction 性能

- GIVEN 工作台进程已启动、初始不可变索引已预热且页面已加载，同时准备一次成功 refresh、一次构建失败 refresh 和并发 refresh 请求。
- WHEN 真实浏览器在固定数据集上执行冻结交互集 30 次，并在交互期间触发上述显式 refresh。
- THEN 每次读取只绑定交换前或交换后的完整 `readToken`，并发 refresh 单飞，成功构建只原子交换一次，失败继续服务旧快照；30 个有效样本不删慢值，nearest-rank 第 29 个样本不高于 3000ms；安装、构建、启动、预热、refresh 与 warm interaction 分开报告，任一失败保持可见。

## 6. 依赖

- 上游事实：canonical pool snapshot、对象包、来源授权事实、生产 review、标签 taxonomy 与稳定对象/版本身份。
- 下游结果：仅位于 `QWQ_CONTENT_WORKBENCH_ROOT` 的离线人工复核记录和 R1/R2 候选；没有在线或发布下游。
- 父级设计：[`DEC-045`](../design.md#dec-045)。
- 工程测试：[`local_contract`](../../../../../quwoquan_data/tests/local_contract/governance/content_workbench/test_workbench__contracts__local_contract_test.py)、[`api_integration`](../../../../../quwoquan_data/tests/api_integration/governance/content_workbench/test_workbench__http__api_integration_test.py)、[`Data Portal core`](../../../../../quwoquan_data/control_plane/content_workbench/portal/tests/core.test.mjs)；真实浏览器 30 样本报告绑定 `GWT-006`。

## 7. 开放事项

无。
