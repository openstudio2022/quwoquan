---
name: /rec-bench
id: rec-bench
category: Recommendation
description: 推荐系统 · 效果评估与业界对标（离线/在线指标 + 工程成熟度对标）
---

# rec-bench

## 命令目的
评估推荐系统的效果水位和工程成熟度，与业界一流产品系统性对标。

## 输入
- `--target {tiktok|xiaohongshu|wechat|toutiao|all}` 对标对象（默认 all）
- `--scope {offline|online|engineering|both}` 评估范围（默认 both）

## 对标维度矩阵

### A–E：功能对标
（行为捕获深度 / 召回策略 / 排序与重排 / 社交利用 / 工程与运营）

### F. 工程规范对标（新增维度）

| 能力 | TikTok | 小红书 | 微信 | 我方 |
|------|--------|--------|------|------|
| DDD 分层 | ★★★ | ★★ | ★★★ | ? |
| 强类型特征传输 | ★★★ | ★★★ | ★★★ | ? |
| 存储无关抽象 | ★★★ | ★★ | ★★★ | ? |
| 端云 schema 一致性 | ★★★ | ★★★ | ★★★ | ? |
| metadata 驱动 | ★★★ | ★★ | ★★ | ? |
| 四层测试覆盖 | ★★★ | ★★ | ★★★ | ? |
| 特征一致性校验 | ★★★ | ★★★ | ★★★ | ? |
| AB 正交分层 | ★★★ | ★★★ | ★★★ | ? |
| 自动模型迭代 | ★★★ | ★★ | ★★ | ? |

## 评估标准
- ★★★：完整实现 + 测试 + 生产可用 + 合规
- ★★：实现存在但缺测试/缺配置/未上线 或 合规部分满足
- ★：骨架/接口存在但未实现
- ○：完全缺失

## 验证手段

```bash
# 离线指标
cd quwoquan_service/scripts/ml && python3 evaluate.py --model latest --metrics auc,gauc,ndcg

# DDD 合规扫描
make gate

# 特征一致性
cd quwoquan_service && python3 scripts/ml/verify_feature_consistency.py

# 端云 schema 对齐
cd quwoquan_app && flutter test test/cloud/behavior/
```

## 输出要求
- 14+9 维矩阵评估
- 离线/在线指标快照
- 工程成熟度评分
- 改进路线图（对齐 `/rec-plan` 格式）
