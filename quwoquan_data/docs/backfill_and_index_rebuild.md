# 回填与索引重建说明

这份说明用于历史回填、批量重跑和发布前复验，避免 `_entity.json`、`manifest.json`、`publish/v1/index/` 三层职责再次混写。

## 真相源

- `_entity.json` 是实体事实源。
- `manifest.json` 只保留发布和索引所需的扩展元数据。
- `publish/v1/index/` 是 lookup 索引层，不承载事实字段。
- `publish/v1/index/_manifest.json` 记录索引分片和条数，不参与业务查询。

## 回填顺序

推荐顺序如下：

```bash
python3 scripts/build_publish_lookup_indexes.py
python3 scripts/gate_e2e.py
python3 scripts/verify_campus_taxonomy.py
python3 scripts/ml/verify_feature_consistency.py
```

如果是学校数据专项回填，先执行 `bootstrap_school_entities.py` 和 `bootstrap_school_posts.py`，再重建索引和门禁。

## posts 路径约定

canonical 目录结构为：

```text
posts/{contentType}/{angle}/{title}/{seq}/
```

其中 `{angle}` 取 `Format/内容角度/*` 的最后一段。历史兼容的 `posts/{contentType}/内容角度/{angle}/...` 仍可被解析，但新产出应使用 canonical 结构。

## 语义边界提示

产品层的 taxonomy id 和发布层的语义路径不是同一粒度，建议只做映射说明，不要强行合并成一套树：

| 产品语义 | 发布语义轴 |
| --- | --- |
| `education` | `Topic/教育成长` |
| `food` | `Topic/美食餐饮` |
| `travel` | `Topic/旅行` |
| `photography` | `Topic/摄影` |
| `campus` | `Topic/教育成长` + `Audience/圈子/校园圈` + `Format/内容角度/经验分享` |

## 什么时候必须重建索引

- 回填历史实体或 posts 之后。
- 批量修正 tagRefs、geoTagRef、entityRefs 之后。
- 调整学校、住宿、旅行、摄影等高基数目录之后。
- 修改 `bootstrap_*` 产物生成脚本之后。

## 验证标准

- `gate_e2e.py` 通过，包含 G28 lookup 索引完整性和 G29 校园专项。
- `verify_campus_taxonomy.py` 通过。
- `verify_feature_consistency.py` 通过。

