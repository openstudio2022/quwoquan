# L3 子特性：app-theme-infrastructure

## 功能说明

App 主题与视觉基础设施（深色/浅色、设计 token 统一），待规划细化。

## 职责边界

- 负责：主题切换与设计系统 token 在 Flutter 端的统一接入。
- 不负责：具体 UI 组件实现（由各域页面引用主题 token）。

## 适用范围与约束

- **适用**：Cupertino/Material 主题与 AppColors/AppSpacing/AppTypography 等设计 token。
- **约束**：与 design.md、tasks.md 对齐；实施时补齐四类文档。

## 与父/子节点关系

- 父节点：`runtime-client-foundation` L2
- 子节点：无（当前为叶子）

## 验收标准概要

- A1：主题与设计 token 基础设施可用
- A8：门禁与静态检查通过
