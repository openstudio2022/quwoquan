# 用户可感知体验覆盖标准

## 目标

任何用户可感知体验点都必须从应用根 UAT 追踪到领域服务、业务能力、Story、测试证据和性能指标。覆盖测试从用户体验出发，不从代码文件或测试类型倒推。

## 覆盖链路

```text
UserExperience
  -> AppRoot UAT
  -> L1_domain_service boundary
  -> L2_business_capability SIT
  -> L3_story GWT + contract
  -> local_contract / api_integration / user_acceptance + performance evidence
```

## 必填字段

### 应用根 UAT

- `experience_points`：用户可感知体验点。
- `platforms`：iOS、Android、Web 或服务端。
- `journey_refs` / `scenario_refs`：跨领域路径。
- `done_when`：用户可观察结果。
- `test_evidence.primary`：通常为 `user_acceptance`。

### 业务能力 SIT

- `capability_boundary`：能力边界与不负责内容。
- `state_machine`：状态与转换。
- `conflict_matrix`：与相邻体验或系统手势的冲突仲裁。
- `performance_points`：响应延迟、帧率、误触率、降级窗口。
- `test_evidence.primary`：通常为 `api_integration`，并辅以 `local_contract`。

### Story GWT / contract

- `given / when / then`：最小价值点行为。
- `contract_refs`：metadata、route、surface、平台策略或配置契约。
- `platform_variants`：iOS / Android 差异。
- `edge_cases`：边界、权限、冲突、取消、重试。
- `performance_points`：Story 级性能阈值。
- `test_evidence.primary`：通常为 `local_contract`。

## 性能指标口径

体验点必须按需声明：

- 响应延迟：用户动作到首个可感知反馈。
- 动画流畅度：关键过渡帧率或 jank。
- 误触率：相邻手势或控件冲突。
- 保护窗口：二次确认、撤销、取消等时间窗。
- 恢复时间：降级、重试或返回后的状态恢复。

## 验收准出

- 应用根 UAT 能解释用户价值。
- 能力 SIT 能解释能力边界和组合行为。
- Story GWT 能解释最小行为。
- Contract 能解释接口、平台策略或配置边界。
- 三层测试证据和性能指标有明确计划或记录。
