# 任务工程目录（committed 真相源）

每个任务 = 一个目录，taskId 即斜杠路径：`<一级tab中文>/<组织轴>/<键>[/<实体类别>]/<任务名>`。

```
tasks/<taskId>/
  task.yaml      # 规格（schema: schema/task/task_spec.schema.json）
  progress.json  # 断点：广度 coverage.entities + 深度 anglesByEntity/conditionCells（续跑唯一依据）
  runs/run_*.json# 每次运行账本（会话总结/增量/下一步），可复盘
  notes.md       # 经验沉淀（踩坑/取舍/数据源）
```

- committed（本目录，进版本控制）= 规格/进度/账本/经验。
- runtime（`runtime/tasks/<taskId>/`，gitignored）= 生成产物工作区，同 taskId 对应。
- publish（`publish/`，gitignored）= 发布主线；`ship` 按 `deploy/shared/content_sampling_manifest.yaml` 采样到各环境。

## 继承分层（L0-L3）：覆盖广 + 精确，task 只写特有

条件维（角度/受众/载体/地形 regions/季节 seasons）按路径前缀 `_defaults.yaml` 就近继承，**list 整体替换、dict 递归合并**（见 `task/store.py:defaults_chain/resolve_spec`）。task.yaml **只写特有**，其余继承：

| 层 | 文件 | 提供 | 改动频率 |
|----|------|------|----------|
| **L0 全局** | `tasks/_defaults.yaml` | carriers=[article]、minPostsPerEntity | 极少 |
| **L1 垂类** | `tasks/旅行/_defaults.yaml` | 通用 angles/audiences + 四季 seasons | 少 |
| **L2 地域/环线** | `tasks/旅行/地域/四川省/_defaults.yaml` | 该地域**真实地形全谱菜单**（高原/雪山/山地森林/平原都市/乡村田园）；泰国/川西可 override 季节 | 建地域时一次 |
| **L3 实体级** | `publish/entities/<域>/<类>/<名>/_entity.json` 的 `conditionProfile` | 实体**真实**地形(regions)/最佳季节(seasons)/海拔；`plan/brief` 按 entityRef 取主值**精确注入** conditionContext，缺失回退 L2 全谱 | 建实体时 |

**task.yaml 只写**：`scope`（region/entityTypes/coverageTargets/route/anchorEntities）+ 与 L1 不同的特化 `angles` + `content.emphasis`（实体类别选题侧重）+ 可选 `acceptance`。

- **不写** `carriers`/`audiences`/与 L1 相同的 `angles`/`conditionAxes`（lint 会 PR_WARN 提示冗余）。
- 若确有地形/季节限制才 override `conditionAxes`，且**必须是继承全谱子集**（lint 越界报错）。
- `emphasis` 示例：古镇=人文叙事/古建筑、博物馆=文物/科普、遗址=历史考据、美食=在地风味、住宿=住宿体验、打卡地=机位美图、赛事=赛事报道、线路=路线/补给避险。

> lint（`qwq-data task lint`）校验：拦 `provenance.historySourceTasks`、effective `angles`/`seasons`（travel 含 `regions`）非空、显式 `conditionAxes` 须为全谱子集；冗余 content 出 PR_WARN。试点结论见 `旅行/地域/四川省/景区/景区全覆盖/notes.md`。

## CLI（CLI-first：skill 只编排这些命令）

```
# 默认不写 carriers/audiences/conditionAxes（继承 L0-L2）；--angles 仅在与垂类默认不同时给；--emphasis 声明实体类别选题侧重
qwq-data task new --vertical travel --organize-by 地域 --key 四川省 --category 景区 \
    --name 景区全覆盖 --coverage 地点/景区/九寨沟,地点/景区/黄龙 --emphasis 自然风光,徒步体验
qwq-data task list [--tree] [--vertical travel]   # 10-20 任务广度总览
qwq-data task show <taskId> | lint [<taskId>] | status <taskId> | resume <taskId>
qwq-data task lock/unlock <taskId> [--owner X] [--force]   # 并发锁，陈旧锁(>6h)可夺
qwq-data task record-run <taskId> --summary "..." --posts-added N --mark-done 地点/景区/九寨沟
qwq-data task trace --task-id <taskId> | --ref <publish片段>   # 溯源反查
qwq-data task hydrate <taskId>                                 # 按 sourceTaskId 拉回 publish 产物
```

## 单任务重生成回路（每任务）

```
1. qwq-data task lock <taskId> --owner <session>
2. qwq-data task resume <taskId>                 # 读缺口（待补实体 / 缺角度 / 缺条件维）
3. 上游：explore（按 scope.coverageTargets 找全）→ build 实体主页 → download 取图
4. 产出：plan（实体 conditionProfile 自动精确注入 L3，缺省回退地域全谱；可 --region/--season 强制覆盖）
        → produce --stage compose-brief → 会话模型创作 article.md(generator=agent)
        → produce --stage review --materialize（自动写 sourceTaskId/sourceBatchId 溯源）
5. qwq-data task record-run <taskId> --summary ... --mark-done ... --posts-added ...
6. qwq-data task unlock <taskId>
```

## promote + 环境回填

```
# 串行 promote（publish 锁），各环境按比例采样（默认 10% / 上限 1000；prod 全量）
qwq-data ship --task <taskId> --batch <B> --copy-entities --env alpha,beta,gamma
```

环境比例：`content_sampling_manifest.yaml` 的 `defaults`（sampleRatio 0.10、maxPosts/maxEntities 1000）；
各环境继承，可在 `environments.<env>` 覆盖单键；prod 显式全量。

## 多任务并行（fan-out）

- 每个 subagent 领 1 个 taskId，独占 `runtime/tasks/<taskId>` + `.lock` 并行跑 1-5 步（generate）。
- promote 串行收尾：所有任务生成完后，按任务依次 `ship --task ... promote`（publish 锁串行化），最后统一 `ship --skip-promote --env alpha,beta,gamma` 重采样回填各环境。

## 历史全量重生成（破坏性，建议分批/试点先行）

1. （可选）`rm -rf publish/*`（gitignored 本地主线；app 的 alpha CI seed 在 `_shared/test_fixtures` 另有提交，不受影响）。
2. fan-out 按 `task list` 逐任务重生成 → promote。
3. `ship --skip-promote --env alpha,beta,gamma` 回填。
4. 校园「全国高校」历史是按学校目录批量生成（~3302 校）；如需追历史全量，先按目录重新 `task new`/扩 coverageTargets 再 fan-out（体量大，跨会话）。
