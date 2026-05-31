# 校园 / 旅游冷启动批次

## 工作流（runtime → release → publish/v1）

### 川西 v2 全量（122 篇 P0）— 推荐路径

**职责拆分**（plan Phase 0–3）：

| 阶段 | 脚本 | 产出 |
|------|------|------|
| Bootstrap | `python3 cold_start/seed_chuanxi_v2_batch.py` | 实体、manifest、compose brief（**不写正文**） |
| Download | `python3 cold_start/seed_chuanxi_v2_download.py --batch <batch>` | 每实体 ≥2 curated sources，`gate_download` PASS |
| Compose | `python3 cold_start/compose_chuanxi_v2_from_sources.py --all-batches` | brief + sources → compose/review results |
| 端到端 | `python3 cold_start/run_chuanxi_v2_pipeline.py --all-batches --release` | bootstrap → download → compose → materialize → verify → release |
| GWT 6 条 | `python3 cold_start/run_chuanxi_v2_pipeline.py --gwt-only` | 6 条样例验收 |
| 语义门禁 | `python3 verify_content_semantics.py --batch <batch>` | mustIncludeFacts、段落去重、sources 追溯 |

**Smoke baseline（模版化，非终稿）**：`python3 cold_start/seed_chuanxi_v2_batch.py --smoke`  
旧 release 中由 seed 直接 `_paragraph_for_heading` 填模板的内容仅用于 pipeline/索引联调；**对用户可读终稿必须走 `run_chuanxi_v2_pipeline.py`**。

Promote 与索引：

```bash
python3 cold_start/generate_chuanxi_v2_manifest.py   # 可选，bootstrap 已含
python3 cold_start/run_chuanxi_v2_pipeline.py --all-batches --release
python3 cold_start/verify_chuanxi_v2_gwt.py --release
python3 promote_to_publish_v1.py --release-id chuanxi_cold_start_r2 --version 1
python3 build_publish_lookup_indexes.py
python3 gate_e2e.py
```

### 其他批次

- **川西 v1 全量（16×2）**：`python3 cold_start/seed_chuanxi_batch.py`
- **校园标杆（10×3）**：`python3 cold_start/seed_campus_batch.py`
- **旧 pilot 入口**：`python3 cold_start/seed_pilots.py`

**禁止** `bootstrap_school_posts.py` / `sample_data/*` 直写 `publish/v1` 作为冷启动终稿。

## 产出规模

| 批次 | 任务 ID | 规模 |
|------|---------|------|
| 川西冷启动 v2 | `川西冷启动_v2` | 122 篇 P0（6 batch） |
| 川西冷启动 v1 | `川西冷启动_v1` | 16 实体 × 2 篇 = **32 篇** |
| 校园标杆 | `校园冷启动_首批50校` / batch `pilot` | 10 校 × 3 篇 = **30 篇** |
| 旅游 pilot（旧） | `四川旅行_冷启动_v1` | 3 景区 × 2 = 6 篇 |
