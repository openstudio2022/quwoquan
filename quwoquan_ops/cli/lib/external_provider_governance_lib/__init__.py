"""external_provider_governance 实现包。

实现按职责切分为 constants / models / derived_sources / validation /
compilation / go_descriptors 六个子模块；公开与被测私有符号统一由稳定
薄入口 ``quwoquan_ops/cli/lib/external_provider_governance.py`` re-export，
消费者不应直接 import 本包内部模块。
"""

from .single_environment import compile_single_environment_bindings

__all__ = ["compile_single_environment_bindings"]
