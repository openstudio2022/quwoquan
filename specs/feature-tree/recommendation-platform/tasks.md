# 开发任务：recommendation-platform（L1）

## 当前交付任务

- [x] 确保 rec-model-training 与 rec-model-service 目录与 tree_index 一致，无遗留 rec-model-engineering-service 引用
- [x] rec-model-training：训练管线（样本、数据集、特征、训练、注册）与训练部署（镜像、PAI/火山任务）见其下 L4/L5 tasks；脚本落点 `scripts/ml/`，feature_registry.yaml、sample_joiner、train.py、evaluate.py、model_registry、Dockerfile 已就绪
- [x] rec-model-service：推理 API、Go 集成、推理部署见其下 L4/L5 tasks；契约与 [readiness.md](rec-model-service/readiness.md) 就绪检查一致；Phase 1–3 已实施（CascadeScorer、FastAPI /v1/score、Dockerfile、docker-compose）
- [x] 两服务共用 feature_registry、ModelRegistry 契约；训练产出可被推理侧从 Registry/OSS 加载
- [x] 门禁：make gate 已通过；metadata 与 endpoint_catalog 与设计一致

## 搁置任务（带规划）

> 因依赖/资源/优先级暂不实施；须写明搁置原因、计划何时/在何条件下重启、由谁或何节点承接，便于回顾审视。

- [ ] **rec-model-training 对外「提交训练任务」API**：搁置原因：当前以作业/脚本触发即可满足；计划在「训练任务可编排、需产品化」时重启；承接节点：rec-model-training 下新增 L4/L5 或独立特性，需同步 metadata/endpoint_catalog。
- [ ] **按 scenario 拆多推理服务（方案 C）**：搁置原因：当前 scenario 数量与运维成本不支撑；计划在「多团队/多场景独立发布与 SLA」需求明确时再评估；承接：本 L1 或新 L3 的 design/tasks 细化。

## 未来演进任务

> 与 [design.md](design.md) 中「未来演进」对应；不阻塞当前交付，新开特性时在对应节点 spec/design/tasks 中细化，便于跟踪与回顾。

- [ ] **双塔与深度模型**：在保持当前 LightGBM/规则可回退的前提下，规划双塔（Two-Tower）等业界通用深度排序模型在 rec-model-training / rec-model-service 的接入方式（特征对齐、训练管线、模型注册与推理契约兼容）。
- [ ] **TikTok/Facebook 式信息流模型**：参考业界信息流推荐实践，预留或补充「重度深度学习模型」（序列、多目标、实时特征）的演进路径；涉及训练样本格式、场景路由与 A/B 实验边界时，在对应 L4/L5 的 spec/design/tasks 中说明。
- [ ] **契约与部署兼容**：演进到重型模型时，保持 POST /v1/score 与 CandidateInput/CandidateScore 契约稳定；新增模型类型通过 scenario 或模型版本区分，训练与推理部署形态仍遵循 design 的分离约定。
