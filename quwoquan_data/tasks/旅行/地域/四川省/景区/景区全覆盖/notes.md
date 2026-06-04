# 四川省景区全覆盖

- taskId: `旅行/地域/四川省/景区/景区全覆盖`
- archetype: region_category_coverage
- 覆盖历史任务: 四川旅行_v5, 四川省全域_v5, 四川旅行_冷启动_v1, 川西冷启动_v1, 川西冷启动_v2

## 历史实体种子 (15)

- 地点/景区/丹巴甲居藏寨
- 地点/景区/九寨沟
- 地点/景区/四姑娘山
- 地点/景区/墨石公园
- 地点/景区/峨眉山
- 地点/景区/康定木格措
- 地点/景区/新都桥
- 地点/景区/毕棚沟
- 地点/景区/海螺沟
- 地点/景区/理塘
- 地点/景区/甲根坝
- 地点/景区/稻城亚丁
- 地点/景区/色达
- 地点/景区/若尔盖花湖
- 地点/景区/黄龙

## 经验沉淀

(记录踩坑/取舍/数据源)

## 稻城亚丁端到端试点（task 重定义 + conditionAxes 分层 L3 验证）

时间：2026-06-01。目标：以单实体景区「稻城亚丁」验证瘦身后的 task 规格 + 四层条件分层在真实 CLI 是否「覆盖广 + 精确」。

### 1. 历史基线对比 — 不可得（已记录）

`quwoquan_data/publish/` 与 `quwoquan_data/runtime/**` 均在 `.gitignore`（第 57、66 行），历史产物从未进入版本库；`git log -S 稻城亚丁` 无命中。前两次清理已物理删除 publish/runtime 旧产物，故**无法从 git 找回历史稻城亚丁文章作逐句对比**。对比改为「结构/事实/条件精确度」维度的方法论对比（见下）。

### 2. conditionAxes 四层分层（已落地并验证）

- L0 全局 `_defaults`：carriers=[article]。
- L1 垂类 `旅行/_defaults`：通用 angles/audiences + 四季。
- L2 地域/环线 `_defaults`：四川省真实地形全谱 [高原/雪山/山地森林/平原都市/乡村田园] + 四季；欧洲/泰国/川西环线本轮补建全谱菜单（泰国/川西并 override 季节）。
- L3 实体 `conditionProfile`：稻城亚丁 = regions[高原,雪山] / seasons[秋,夏,冬] / 海拔4700 / notes；写于 `publish/entities/地点/景区/稻城亚丁/_entity.json`。
- task.yaml 不再内联 conditionAxes，由 `plan/brief` 按 entityRef 精确取子集注入；缺失实体画像则回退地域全谱（`entityProfileFallback`）。

### 3. plan → compose brief（真实 CLI，精确注入已验证 ✅）

命令（**未传** `--region/--season`，验证自动精确推断）：

```
qwq-data plan --vertical travel --subject entity --kind 景区 --intent 体验 \
  --entity-refs 地点/景区/稻城亚丁 --title "稻城亚丁·亚丁三神山徒步体验" --output <brief>
```

brief 结果（节选）：

- `conditionContext.region = 高原`（label 高原/高海拔，source=**entityProfile**，自动取实体主地形而非 task 全谱）；packing=[防晒墨镜,保暖冲锋衣,红景天与葡萄糖]，riskNotes=[高原反应,强紫外线灼伤,道路结冰落石]。
- `conditionContext.season = 秋`（source=entityProfile）；crowdNotes=[国庆与红叶季拥挤]。
- `conditionContext.entityProfile`：regions[高原,雪山]、seasons[秋,夏,冬]、altitudeMeters 4700、notes 全文随 brief 输出（覆盖广）。
- `mustIncludeFacts` 在模板基线 [到达时间,停留时长,体验路线] 上叠加精确条件事实：海拔与高反风险 / 强紫外线防护 / 昼夜温差 / 红叶与彩林窗口 / 干燥补水。
- `imagePlan` 叠加：雪山垭口 / 高原湖泊 / 经幡牧场（高原）+ 彩林红叶 / 秋日金辉 / 云海（秋）。
- `tagRefs` 含 Topic/自然风光/高原风光 + Topic/时间/四季/秋季。

配套改动：`景区_体验.tmpl.yaml` 声明 `conditionAxes.region/season applicable`（景区是强地形/季节敏感类别），使 catalog 精确事实/图位/标签得以注入。

结论：达成「a 为基础（地域全谱覆盖广）+ b 精确度（实体真实高原/雪山/秋/海拔，非笼统）」的分层目标。

### 4. produce → review → promote → ship — 受真实素材依赖阻断（已记录边界）

`produce --stage compose-brief` 对稻城亚丁返回 `SKIP: evidence too weak (recommendation=skip)`：因 `download` 真实来源素材缺失，产证据不足。这是事实可回溯门（不允许无出处素材凭空成稿）的**正确**行为，本试点不伪造素材绕过。

→ produce/review/materialize/promote/ship 全链路的前置是 `qwq-data download` 拉取真实来源；该步需联网真实数据源，留作后续 fan-out（先 download 素材，再按本 brief 精确条件创作正文、过三道门、materialize、promote、ship 回填 alpha/beta/gamma）。

### 5. 其余旅行任务

13 个 task.yaml 已瘦身为「只写 scope + 特化 angles + emphasis」，继承解析（angles/regions/seasons/audiences/carriers）全部通过 `task lint`。其余地域/环线任务按相同方法 fan-out（每实体配 conditionProfile → plan 精确注入 → download → produce）。

### 反思账本 · run_20260601_215839
- query: fan-out 5 景区从真实素材到 ship 当前环境集合的端到端闭环
  - 归因: 执行/契约问题：composer 把主实体 entityRef 拼成 /entity/{name} 短格式，publish_filter._parse_entity_ref 需 domain/type/name 三段，导致主实体被误判无主页过滤；图片 needs_review 多为景观误判人脸/缺CV后端，非真不安全
  - 决策: 修复 composer：用 compose input 的 subject.type 补全为全路径 /entity/{domain}/{type}/{name}，提取共享 normalize_entity_refs(单一真相源)并加回归测试；needs_review 不硬拦 produce、延到 publish 人工门；补 fetch 合规UA+429/503退避重试解限流

### 反思账本 · run_20260603_150021
- query: 为 15 实体补真实多源 source_plan + Wikimedia CC 图片直链(39 张) + 体验/讲解/海拔证据 body
  - 归因: 三处工程缺口被修复：①编排器缺 produce_plan(compose brief 无人生成) ②download 用原始 HTML 当 evidence 致情感/数字抽不到 ③gate_produce manifest 路径未下钻版本目录且 materialize 漏写 storySpine
  - 决策: download 优先 source_plan 人工 body 作 evidence 源；gate_produce 兼容 <post>/<version>/manifest.json 并补 storySpine；ship 必须带 --copy-entities 先 promote 主页再关联 posts
