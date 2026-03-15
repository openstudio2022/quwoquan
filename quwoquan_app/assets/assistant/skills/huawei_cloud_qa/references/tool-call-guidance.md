# 工具调用指引

## 检索策略总则

1. 先判定问题层级（L1-L4），再按层级执行差异化检索。
2. **首轮检索始终限定华为云官方**：`site:huaweicloud.com` 或 `site:support.huaweicloud.com`。
3. 单轮最多调用 `web_search` 3 次（含重试）。
4. 检索不足时扩大范围；仍不足时使用模型知识并标注来源。

## 查询构造规范

### L1 查询模板
```
site:huaweicloud.com {产品名} {核心属性词}
```
示例：
- `site:huaweicloud.com ECS 定价 计费方式`
- `site:huaweicloud.com OBS 存储类型`
- `site:huaweicloud.com 提交工单 入口`

### L2 查询模板
```
# L2a 多源综合
site:huaweicloud.com {产品名} {功能列表/计费方式/支持的xxx}

# L2b 多步推理（拆子查询）
site:huaweicloud.com {产品A} 定价
site:huaweicloud.com {产品B} 定价

# L2c 比较与选型
site:huaweicloud.com {产品A} vs {产品B}
{竞品名} {维度} 官方文档

# L2d 故障诊断
site:support.huaweicloud.com {产品名} {报错关键词/现象描述}
site:bbs.huaweicloud.com {产品名} {报错关键词}
```

### L3 查询模板
```
site:huaweicloud.com {产品名} 定价计算器
site:huaweicloud.com {场景} 成本优化 最佳实践
华为云 {产品方向} 发展趋势 2025 2026
```

### L4 查询模板
```
site:huaweicloud.com {行业} 上云方案 白皮书
site:huaweicloud.com {场景} 架构设计 最佳实践
华为云 {行业} 解决方案 案例
```

## 检索扩展策略

| 场景 | 首轮检索 | 扩展检索 |
|------|----------|----------|
| 产品定价 | `site:huaweicloud.com {产品} 定价` | `site:huaweicloud.com {产品} 计费 价格` |
| 操作步骤 | `site:support.huaweicloud.com {产品} {操作}` | `site:bbs.huaweicloud.com {产品} {操作} 教程` |
| 故障排查 | `site:support.huaweicloud.com {报错}` | `site:bbs.huaweicloud.com {产品} {现象}` |
| 竞品对比 | `site:huaweicloud.com {华为云产品}` + `{竞品} 官方文档` | 技术媒体对比文章 |
| 方案设计 | `site:huaweicloud.com {行业} 解决方案` | `华为云 {行业} 案例 白皮书` |

## 时效性检索

- 定价、活动、促销类问题：`freshnessHoursMax: 720`（30天内）
- 产品功能、操作步骤：`freshnessHoursMax: 8760`（1年内）
- 架构方案、最佳实践：不限时效
- 故障排查：优先最新结果

## 降级规则

1. 首轮检索无结果 → 换关键词/扩大 site 范围再试一次
2. 扩展检索仍无结果 → 使用模型训练知识，但必须标注：
   - "以上信息基于模型训练知识，可能不是最新数据"
   - 附上官方文档/工单/950808 确认渠道
3. 定价/配额/参数等时效性强的数据 → 绝不使用模型知识兜底，直接告知用户通过官网或客服确认

## 竞品检索规范

- 华为云产品信息：必须从 `huaweicloud.com` 检索
- 友商产品信息：从对应厂商官方域名检索（`aliyun.com`、`cloud.tencent.com`、`aws.amazon.com` 等）
- 对比文章：优先权威技术媒体（InfoQ、CSDN、36Kr 等），标注来源
- 禁止使用非权威来源的主观评价作为对比依据
