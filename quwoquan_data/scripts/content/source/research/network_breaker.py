"""Auto-research 网络失败断路器（host 分桶）。

zh.wikipedia 出口故障时，wave 内每个请求都要等满 curl --max-time × retry，
单实体可拖十几分钟、整个 stage 卡死数十分钟（H100 实证 42 分钟零进展）。
断路器把「同一 host 连续网络级失败达到阈值」视为出口故障：
- 后续对该 host 的请求直接短路返回空结果（秒级），不再消耗 max-time；
- 任一成功请求立即复位该 host 桶；
- wave 结束后由 auto_plan_public / run.py 消费 `snapshot()`，把纯网络故障
  wave 标记为可自愈的 network outage（recipe 网络自愈通道接手）。

判定口径：curl 网络级退出码（DNS/连接/超时/SSL/传输中断），
内容级失败（HTTP 4xx/5xx 正常返回、JSON 解析失败）不计入。
"""
from __future__ import annotations

import threading
import urllib.parse

from core.runtime_policy import active_runtime_policy

# curl 网络级退出码：6=DNS 解析失败, 7=连接失败, 28=超时, 35=SSL 握手失败,
# 52=空响应, 55/56=发送/接收失败。
NETWORK_CURL_EXIT_CODES = frozenset({6, 7, 28, 35, 52, 55, 56})

def _threshold() -> int:
    return active_runtime_policy().network_breaker_threshold


class NetworkFailureBreaker:
    """线程安全的 host 分桶断路器。"""

    def __init__(self, threshold: int | None = None) -> None:
        self._lock = threading.Lock()
        self._consecutive: dict[str, int] = {}
        self._short_circuited: dict[str, int] = {}
        self._threshold = max(1, int(threshold)) if threshold else _threshold()

    @staticmethod
    def host_of(url: str) -> str:
        return (urllib.parse.urlparse(str(url or "")).hostname or "").lower()

    def is_open(self, url: str) -> bool:
        host = self.host_of(url)
        if not host:
            return False
        with self._lock:
            if self._consecutive.get(host, 0) >= self._threshold:
                self._short_circuited[host] = self._short_circuited.get(host, 0) + 1
                return True
            return False

    def record_network_failure(self, url: str) -> None:
        host = self.host_of(url)
        if not host:
            return
        with self._lock:
            self._consecutive[host] = self._consecutive.get(host, 0) + 1

    def record_success(self, url: str) -> None:
        host = self.host_of(url)
        if not host:
            return
        with self._lock:
            self._consecutive.pop(host, None)

    def open_hosts(self) -> list[str]:
        with self._lock:
            return sorted(
                host for host, count in self._consecutive.items() if count >= self._threshold
            )

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            open_hosts = sorted(
                host for host, count in self._consecutive.items() if count >= self._threshold
            )
            return {
                "threshold": self._threshold,
                "openHosts": open_hosts,
                "consecutiveFailures": dict(self._consecutive),
                "shortCircuitedRequests": dict(self._short_circuited),
            }

    def reset(self) -> None:
        with self._lock:
            self._consecutive.clear()
            self._short_circuited.clear()


# 进程级共享实例：auto research 的 curl 层与 wave 编排共同消费。
BREAKER = NetworkFailureBreaker()

_wave_deadline_lock = threading.Lock()
_wave_deadline_monotonic: float | None = None
_wave_deadline_exceeded_flag = False


def wave_budget_seconds() -> float:
    """单 wave wall-clock 预算（秒）：0 = 关闭。

    串行路径（maxWorkers=1）没有并行 watchdog；预算耗尽后 curl 层直接短路
    剩余请求，保证 wave 在有界时间内收口并进入可自愈的 outage 通道。
    """
    return float(active_runtime_policy().research_wave_budget_seconds)


def start_wave_budget(budget_seconds: float | None = None) -> None:
    import time

    global _wave_deadline_monotonic, _wave_deadline_exceeded_flag
    budget = wave_budget_seconds() if budget_seconds is None else max(0.0, float(budget_seconds))
    with _wave_deadline_lock:
        _wave_deadline_monotonic = (time.monotonic() + budget) if budget else None
        _wave_deadline_exceeded_flag = False


def clear_wave_budget() -> None:
    global _wave_deadline_monotonic, _wave_deadline_exceeded_flag
    with _wave_deadline_lock:
        _wave_deadline_monotonic = None
        _wave_deadline_exceeded_flag = False


def wave_budget_exceeded() -> bool:
    import time

    global _wave_deadline_exceeded_flag
    with _wave_deadline_lock:
        if _wave_deadline_monotonic is None:
            return _wave_deadline_exceeded_flag
        if time.monotonic() >= _wave_deadline_monotonic:
            _wave_deadline_exceeded_flag = True
        return _wave_deadline_exceeded_flag


def stage_no_progress_timeout_seconds() -> float:
    """stage 无进展 watchdog 预算（秒）：0 = 关闭。

    唯一真相源：runtime profile `stageNoProgressTimeoutSeconds`。
    消费方：auto_plan_public 并行 wave（相邻两次实体完成之间无任何进展超过
    该预算 → 以可续跑的 network/no-progress outage 中断）；task 层 run_context
    暴露同名常量给 run.py 编排消费。
    """
    return float(active_runtime_policy().stage_no_progress_timeout_seconds)
