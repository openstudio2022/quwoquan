# L3 Story：ranking-calibration

## 功能说明

排序校准把规则分、模型分、质量分和交集分映射到可比较的业务概率或相对尺度，避免不同信号在混排、阈值、曝光预算和运营干预中不可比。

## 范围

- 预估分与真实 CTR、完成率、负反馈率的校准。
- 规则分和模型分的场景级 calibration。
- calibration error 进入离线评估与 SLO。
- 校准参数走 metadata/recpolicy，不在业务代码硬编码。

## 非目标

- 本轮不实现校准训练或在线重打分。
- 不引入深度多任务模型。

## 验收标准

- A1：排序分可解释为同一尺度或明确的场景尺度。
- A2：校准参数版本化，可随 scorer_variant 和 channel 切分。
- A3：calibration error 进入 `ranking_calibration_error`。
- A4：校准异常可回退到原始 RuleScorer/RemoteModelScorer。
