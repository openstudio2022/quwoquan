"""训练样本准入策略。

该模块只承载可独立验证的纯函数，训练入口不得各自维护一套过滤语义。
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any


DEFAULT_MAX_FEATURE_LAG_SECONDS = 24 * 60 * 60


def filter_point_in_time_rows(
    rows: Iterable[dict[str, Any]],
    max_feature_lag_seconds: float,
) -> tuple[list[dict[str, Any]], int]:
    """保留特征快照延迟在闭区间 ``[0, max]`` 内的样本。

    缺失、布尔值、非数值、NaN、无穷值、负值及超阈值均 fail-closed 丢弃。
    返回保留样本及丢弃数量，供训练入口统一记录准入结果。
    """

    if isinstance(max_feature_lag_seconds, bool) or not isinstance(
        max_feature_lag_seconds, (int, float)
    ):
        raise ValueError("max_feature_lag_seconds must be a finite non-negative number")
    max_lag = float(max_feature_lag_seconds)
    if not math.isfinite(max_lag) or max_lag < 0:
        raise ValueError("max_feature_lag_seconds must be a finite non-negative number")

    materialized_rows = list(rows)
    accepted: list[dict[str, Any]] = []
    for row in materialized_rows:
        lag = row.get("featureLagSeconds")
        if isinstance(lag, bool) or not isinstance(lag, (int, float)):
            continue
        normalized_lag = float(lag)
        if math.isfinite(normalized_lag) and 0 <= normalized_lag <= max_lag:
            accepted.append(row)
    return accepted, len(materialized_rows) - len(accepted)
