# 川西 crawl 修复方案复核（命令入口 + 可复用脚本）

本文是对「问题根因与修复」的**二次复核**，按你的要求强调：**从命令（CLI）入手**，且 **爬取/扩池脚本可复用、支持增量**，避免每次全量重生成。

---

## 1. 复核结论（问题是否仍存在）

| 问题 | 当前代码事实 | 复核结论 |
|------|----------------|----------|
| 来源偏 wiki、缺马蜂窝等 | [`chuanxi_crawl_bootstrap.py`](quwoquan_data/tools/chuanxi_crawl_bootstrap.py) 只生成百科主条 + 无过滤的 `prop=links`；**未**调用任何旅游站发现 | **根因未变**；仅改 spec `allow_domains` 不够，必须加「发现」与过滤 |
| 杜甫草堂下无关文章 | 维基外链与景点无绑定语义 | **根因未变**；必须关/收紧 `prop=links` 或加相关性门槛 |
| 景点数量 | 手工 [`chuanxi_attractions_catalog.yaml`](quwoquan_data/runtime/seed/chuanxi_attractions_catalog.yaml) | **根因未变**；需 POI 真相源 + topic 分片/动态展开 |

---

## 2. 务必从命令入手：CLI 为第一入口

现状：[`quwoquan_data/tools/cli.py`](quwoquan_data/tools/cli.py) 仅有 `crawl spec-discovery | status | fetch-source | compose-topic | audit-topic | run-topic`，**没有**「扩池 / POI 导入 / 增量合并 / 跳过 hydrate 发现」等命令，导致川西逻辑落在独立脚本上，与 `/crawl` 总控文档不一致。

**复核要求**：新能力应落在 **`python3 quwoquan_data/tools/cli.py crawl <subcommand>`**（或同级 `qwq-data` 子命令），并在 [`.cursor/commands/crawl.md`](.cursor/commands/crawl.md) / [`quwoquan_data/README.md`](quwoquan_data/README.md) 中写明调用方式。

### 2.1 建议新增的 crawl 子命令（命名可微调）

| 子命令 | 职责 | 与「可复用」关系 |
|--------|------|------------------|
| `crawl pool-bootstrap` | 按 spec + catalog/profile 生成或**合并**各 topic 的 `source_pool.ndjson`（百科主条、可选过滤维基、旅游站 URL 列表） | 支持 `--merge`、`--topics`、`--dry-run` |
| `crawl pool-import` | 从外部 NDJSON/CSV（如 OSM 导出）批量追加候选行 | 幂等键：`sourceUrl` 或 `sourceId` |
| `crawl spec-discovery`（增强） | 可选 `--skip-hydrate`：只刷新 `discovery.json` / `topic_tasks.ndjson`，**不**对全池逐条拉 HTML（需改 [`batch.py`](quwoquan_data/tools/batch.py)） | 大 POI 规模下必须，否则命令不可用 |

实现要点：`cli.py` 注册子命令 → `batch.handle_*` 或独立 `pool_ops.py` 再被 batch 调用；**业务逻辑不放死在「川西」文件名里**，川西只是默认 profile。

### 2.2 与现有命令的衔接

```text
crawl pool-bootstrap --spec ... [--merge] [--topics t1,t2] ...
crawl spec-discovery --spec ... [--skip-hydrate]
crawl fetch-source ...   # 单条补源，保持不变
```

---

## 3. 川西脚本做成可复用：不要每次重新生成

当前 [`chuanxi_crawl_bootstrap.py`](quwoquan_data/tools/chuanxi_crawl_bootstrap.py) 每次运行会 **整文件重写** `source_pool.ndjson`（`write_ndjson` 全量覆盖），且逻辑写死「川西 + 当前 catalog」，因此**不具备**增量与跨地域复用。

### 3.1 复用形态（推荐）

1. **通用模块 + Profile**  
   - 将「维基解析 / 百科内链 / 相关性过滤 / 未来旅游发现」抽到例如 `quwoquan_data/tools/crawl_topic_pool.py`（或 `pool_bootstrap.py`）。  
   - **Profile**：`runtime/seed/profiles/chuanxi.yaml` 描述 `catalog_path`、`default_wiki_strategy`、`allow_travel_domains` 等；川西、其它线路只换 profile，不换代码结构。

2. **默认增量（merge），全量需显式**  
   - 默认：`--merge` 为 true——按 `sourceUrl`（或 `sourceId`）去重，**只追加**新行，不删已有手工/已审核行。  
   - 全量重建：`--replace-pool` 显式覆盖（防误操作）。

3. **按 topic / 按 catalog 切片**  
   - `--topics cdcx_attr_du_fu_001` 只处理指定 topic。  
   - `--catalog-offset 0 --catalog-limit 200` 配合大 POI 文件分批跑，避免一次跑千站超时。

4. **状态与幂等（可选）**  
   - `runtime/runs/<spec_id>/.pool_bootstrap_state.json` 记录上次 catalog 文件 hash、已处理 `topic_id`，支持 `--since-hash` 跳过未变更 topic。

### 3.2 与「命令」对齐

上述逻辑由 **`crawl pool-bootstrap`** 调用同一套实现；`chuanxi_crawl_bootstrap.py` 可退化为 **薄封装**（deprecated shim 调 CLI 模块），避免维护两套入口。

---

## 4. 实施顺序（在通过本复核后的执行顺序）

1. **CLI**：在 `cli.py` 增加 `crawl pool-bootstrap`（及可选 `pool-import`）；README / crawl 命令文档同步。  
2. **batch**：`spec-discovery --skip-hydrate`（或等价环境变量），保证大 spec 下命令可完成。  
3. **重构**：抽离通用 pool 逻辑 + chuanxi profile；默认 merge、可选 replace。  
4. **业务**：旅游站发现、POI 真相源、相关性过滤（仍按前版计划的技术项推进）。

---

## 5. 待你确认的一点（可选）

若希望 **单条命令** 覆盖「POI 导出 + pool-bootstrap + spec-discovery」，可再增加 `crawl region-sync --spec ... --profile chuanxi` 作为编排层（内部顺序调用子命令）；否则保持子命令原子化更易测试。
