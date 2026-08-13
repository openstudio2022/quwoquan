"""provider_conformance 实现包。

实现按职责切分为 constants / evidence_store / governance_bindings /
attestation / candidate / sources / case_results / evidence_validation /
readiness 九个子模块；公开与被测私有符号统一由稳定薄入口
`quwoquan_ops/cli/lib/provider_conformance.py` re-export，消费者不应直接
import 本包内部模块。
"""
