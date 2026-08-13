"""run_provider_patrol_uat 实现包。

实现按职责切分为 runtime_identity / mutable_runtime / report_evidence 三个
子模块；公开与被测私有符号统一由稳定薄入口
`quwoquan_ops/ci/provider_conformance/run_provider_patrol_uat.py` re-export，
消费者不应直接 import 本包内部模块。
"""
