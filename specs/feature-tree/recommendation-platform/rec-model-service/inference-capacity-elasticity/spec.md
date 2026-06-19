# L3 Story：inference-capacity-elasticity

## 功能说明

rec-model-service 的商用并发容量与实时性工程：多进程、打分/特征缓存、跨请求合批、超时预算分层，以及与治理 guardrails 口径统一。当前单 Uvicorn worker + 紧超时导致频繁回退规则打分，无缓存/合批，难以承载商用 QPS。

## 范围

- 多进程：`uvicorn --workers` 或 gunicorn + uvicorn worker，按 CPU 核数水平扩容，替换单 worker。
- 缓存：打分结果短 TTL 缓存（同候选 + 特征指纹）、特征缓存层。
- 合批：可选跨请求 micro-batch coalescing，降低 numpy/LightGBM 调用次数。
- 超时预算分层：feature/recall/model 预算与重试预算分离，避免一次重试挤占全预算导致大面积回退 rule。
- guardrails 口径统一：`policy.yaml` guardrails `suggest_only` 与 `online_guardrail.py` 自动切流口径对齐。

## 非目标

- 不引入深度模型平台轨的服务拆分或 ANN 检索；P1 仅完成当前 rec-model-service 的容量工程最小集。
- 不引入深度模型平台轨（MMoE/PLE/双塔 ANN/IPS）。

## 验收标准

- A1：服务可多进程水平扩容，单进程 GIL 不再是吞吐上限。
- A2：打分/特征缓存命中可降低模型调用与尾延迟，缓存有 TTL 与失效策略。
- A3：超时预算分层后 `model_fallback_rate` 不因单次重试大面积升高。
- A4：guardrails `suggest_only` 与 `online_guardrail` 自动切流口径一致，无治理语义冲突。
- A5：容量指标（QPS、P95/P99、fallback 率、缓存命中率、合批度）可观测并以 SLO 为真相源。
