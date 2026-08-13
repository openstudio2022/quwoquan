"""generic_protocol_substitute_conformance 实现包。

实现按职责切分为 models / evidence_helpers / protocol_client /
runtime_scenes 四个子模块；公开与被测私有符号统一由稳定薄入口
`quwoquan_ops/ci/provider_conformance/generic_protocol_substitute_conformance.py`
re-export，消费者不应直接 import 本包内部模块。
"""
