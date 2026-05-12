---
name: /data-sichuan-e2e
id: data-sichuan-e2e
category: Workflow
description: 应用数据生成工作流 · 四川样例 full reset 后端到端验证
---

## 目标

从四川样例 seed 出发，执行：

- full runtime reset
- 目录候选层 / 实体 / 标签
- 下载与图文加工
- 发布与 verify

## 真实实现

```bash
bash scripts/run_sichuan_geo_content_trinity_e2e.sh
```

## 输出

- 当前 runtime 下的四川样例 publish 产物
- authenticity / package / catalog consistency 结果
---
name: /data-sichuan-e2e
id: data-sichuan-e2e
category: Workflow
description: 应用数据生成工作流 · 四川样例 full reset 后端到端验证
---

## 目标

从四川 seed / config 出发，执行：

- full runtime reset
- catalog → entity/tag
- 下载与图文加工
- 发布与 verify

## 真实实现

对应脚本：

```bash
bash scripts/run_sichuan_geo_content_trinity_e2e.sh
```

## 输出

- 当前 runtime 下的四川 catalog、entity/tag、sample spec、publish 产物
- authenticity / package 验证报告

## 边界

- 当前是四川样例 E2E，不等价于全量全国数据生产
- 依赖外部网络与公开来源可访问性
