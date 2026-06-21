# data-tag-bootstrap

生成/重建完整标签体系（7大维度：实体类型、地理、主题、场景、内容角度、时间、用户画像）。

## 执行步骤

```bash
# 1. 生成非地理维度标签（幂等，可重复执行）
python3 quwoquan_data/scripts/bootstrap/taxonomy/bootstrap_tags.py

# 2. 补全行政区标签（可指定省份/城市）
python3 quwoquan_data/scripts/bootstrap/taxonomy/bootstrap_admin_regions.py                      # 全部省份
python3 quwoquan_data/scripts/bootstrap/taxonomy/bootstrap_admin_regions.py --province 四川省     # 指定省
python3 quwoquan_data/scripts/bootstrap/taxonomy/bootstrap_admin_regions.py --province 四川省 --city 成都市  # 指定市

# 3. 生成自然地标标签（山脉/名山/江河/湖泊/海洋/沙漠）
python3 quwoquan_data/scripts/bootstrap/taxonomy/bootstrap_geo_landmarks.py

# 4. 验证标签体系完整性
python3 quwoquan_data/scripts/verify/verify_tag_tree.py

# 5. 输出统计报告
python3 quwoquan_data/scripts/tags/tag_stats.py
```

## dry-run 模式

```bash
python3 quwoquan_data/scripts/bootstrap/taxonomy/bootstrap_tags.py --dry-run
```

仅统计标签数量，不写入磁盘。

## 输出位置

`quwoquan_data/publish/tags/`

## 目标

- 非地理维度 >= 1590 标签
- 总标签数 >= 1900
- 7 大维度 _dimension.json 完整
- 四川省 21 市州行政区完备

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/data-tag-bootstrap` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
