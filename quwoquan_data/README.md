# quwoquan_data

`quwoquan_data` 已切到 **代码与运行时分离** 的形态：

- 仓库内只保留 `schema/`、`tools/`、`tests/`、`README.md`、`SPEC.md`
- 真实运行数据统一写入 ignored 根目录 `quwoquan_data/runtime/`
- 测试样例统一收敛到 `quwoquan_data/tests/fixtures/`

默认路径解析：

- `QWQ_DATA_ROOT` 默认指向 `quwoquan_data/`
- `QWQ_RUNTIME_ROOT` 默认指向 `quwoquan_data/runtime/`

## 目录治理

```text
quwoquan_data/
├── README.md
├── SPEC.md
├── schema/
├── tools/
├── tests/
│   └── fixtures/
└── runtime/          # ignored，仅承载真实运行数据
```

`runtime/` 下的正式结构：

```text
runtime/
├── specs/
├── trees/
├── runs/
├── publish/
├── out/
└── downloads/
```

其中：

- `runtime/specs/{spec_id}.yaml` 是运行时 spec 真相源
- `runtime/trees/**` 是运行时实体/标签/模板树
- `runtime/runs/{spec_id}/topics/{topic_id}/...` 是 topic 工作区
- `runtime/downloads/` 存放原生抓取的 HTML 与图片二进制
- `tests/fixtures/runtime_seed/` 只保留测试种子，不再把样例 runs/publish/raw 跟踪到仓库根

唯一有效的 publish 真相源是：

- `quwoquan_data/runtime/publish/`

仓库根旧目录 `quwoquan_data/publish/`、`quwoquan_data/runs/`、`quwoquan_data/raw/`、`quwoquan_data/out/`、`quwoquan_data/crawl_specs/`、`quwoquan_data/trees/` 仅作为迁移中的待删除对象，不再参与当前主线读写。

## hybrid 主线

`/crawl` 与 `cli.py crawl *` 现在采用 hybrid 结构：

1. 命令编排层：
   - `crawl spec-discovery`
   - `crawl status`
   - `crawl run-topic`
2. tools 原生能力：
   - `crawl fetch-source`
   - HTML 拉取
   - 正文抽取
   - 图片 URL 抽取与下载
   - 元数据提取
   - 真实性 / 合规门禁

也就是说，command 层负责编排 spec/topic 生命周期，`tools/native_fetch.py` 负责最小真实 I/O。

## 常用命令

```bash
python3 quwoquan_data/tools/cli.py tree validate --tree all
python3 quwoquan_data/tools/cli.py crawl spec-discovery --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml
python3 quwoquan_data/tools/cli.py crawl fetch-source --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_article_001 --task-type article --source-id real_west_lake_article_source_001 --url "https://zh.wikivoyage.org/wiki/%E6%9D%AD%E5%B7%9E" --title "第一次逛杭州，先把西湖这条线走顺" --query "杭州 西湖 旅行指南 步行" --snippet "中文 Wikivoyage 杭州词条把西湖、湖滨和城市步行节奏写成了旅行指南，更适合重组为用户可读长文。" --rights-status clear --watermark-status clean
python3 quwoquan_data/tools/cli.py crawl fetch-source --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_image_001 --task-type image --source-id real_west_lake_image_source_001 --url "https://commons.wikimedia.org/wiki/File:West_Lake_-_Hangzhou,_China.jpg" --title "雷峰塔视角下的西湖开阔湖面" --query "West Lake Hangzhou Commons image" --snippet "真实来源基于 Wikimedia Commons 文件页，来源页明确写出作者、拍摄时间和 CC BY-SA 3.0 授权。" --rights-status clear --watermark-status clean
python3 quwoquan_data/tools/cli.py crawl run-topic --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_article_001 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl run-topic --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_image_001 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl status --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml
```

说明：

- `run-topic` 现在会基于 retained 且通过真实性校验的来源，自动补全默认 `enrichment.ndjson` 字段（`selectedCandidateIds`、`sourceUrls`、`coverAssetId`、`figureAssetIds/mediaAssetIds`、`publishReady` 等），不再要求手工改 NDJSON 才能跑通真实样例。
- 当前本地真实可验证 publish 样例位于：
  - `quwoquan_data/runtime/publish/real_west_lake_article_001/`
  - `quwoquan_data/runtime/publish/real_west_lake_image_001/`

## 本地验证

```bash
bash scripts/verify_quwoquan_data.sh
python3 scripts/verify_quwoquan_data_source_authenticity.py
python3 scripts/verify_quwoquan_data_post_packages.py
python3 -m unittest discover -s quwoquan_data/tests
```

详细约束见 `quwoquan_data/SPEC.md`。