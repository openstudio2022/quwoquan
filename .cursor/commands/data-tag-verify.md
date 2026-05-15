# data-tag-verify

验证标签体系完整性与合规性。

## 执行

```bash
python3 quwoquan_data/scripts/verify_tag_tree.py
```

## 检查项

| 编号 | 检查项 | 说明 |
|------|--------|------|
| R1 | 维度完备性 | 7 大维度 _dimension.json 必须存在 |
| R2 | 字段合规 | label/labelEn/description/createdAt/updatedAt |
| R3 | 兄弟互斥 | 同级目录下标签名不得互为子串（WARNING） |
| R4 | 行政区完备 | 四川省 21 市州 |
| R5 | 无空目录 | 含 _definition.json 才算有效标签 |
| R6 | 标签总量下限 | 总量 >= 1900, 非地理 >= 1590 |

## 自定义阈值

```bash
python3 quwoquan_data/scripts/verify_tag_tree.py --min-total 2000 --min-non-geo 1600
```
