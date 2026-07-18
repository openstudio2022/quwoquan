"""Deterministic content-creation throughput / horizontal-scaling capacity planner.

底稿中心内容生产的并发吞吐是「单篇耗时 × 可行并行通道数」的乘积。本模块把这一推算
固化为**纯函数 + 强类型**，给运维和放量(2b)一个可复用、可测、不依赖真实大放量的容量门：

- 单通道日产 = 有效作业秒数内的成稿数（按首轮通过率与利用率折损）；
- 可达日产 = 通道数 × 单通道日产；
- 目标所需通道数 = ceil(目标 / 单通道日产)；
- 约束分层：哪些是代码可解（单机本地 bridge 上限已由 P6 错峰/暖机/上限收敛打满，
  per-workspace 启动锁解多-clone 串行），哪些是外部约束（多机/多云 agent、多 key/账号、
  平台并发配额）。

「通道(channel)」= 一个独立的创作执行单元：
- local：一台机器/一个 workspace clone 内，受单机本地 bridge 冷启竞态限制，单机有效并发
  上限 ≈ ``local_bridge_cap_per_machine``（P6 cold-start cap，实测对齐 2-3）；
- cloud：一个独立云端 agent（各自 VM/clone），不共享本地 bridge，瓶颈在平台并发配额与
  多 key/账号，而非单机 bridge。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

SECONDS_PER_DAY = 86_400

# 经第一棒/worker 71c93e21 实测固化的基线（composer 单次 Agent.prompt）。
WARM_SECONDS_PER_ARTICLE = 32.0   # 暖 bridge 复用后单篇
COLD_SECONDS_PER_ARTICLE = 62.0   # 冷启 bridge（60-64s 取中值）单篇
# 单机本地 cursor bridge 冷启安全并发上限（P6 QWQ_FANOUT_COLD_START_MAX_WORKERS 默认 3）。
DEFAULT_LOCAL_BRIDGE_CAP_PER_MACHINE = 3

RUNTIME_LOCAL = "local"
RUNTIME_CLOUD = "cloud"
_VALID_RUNTIMES = (RUNTIME_LOCAL, RUNTIME_CLOUD)


@dataclass(frozen=True)
class ThroughputConfig:
    """容量推算输入（全部可显式给定，缺省取实测基线）。"""

    daily_target: int = 100_000
    channels: int = 1
    runtime: str = RUNTIME_CLOUD
    local_bridge_cap_per_machine: int = DEFAULT_LOCAL_BRIDGE_CAP_PER_MACHINE
    warm_seconds_per_article: float = WARM_SECONDS_PER_ARTICLE
    cold_seconds_per_article: float = COLD_SECONDS_PER_ARTICLE
    active_hours_per_day: float = 24.0
    first_pass_rate: float = 0.85
    utilization: float = 0.80

    def normalized(self) -> "ThroughputConfig":
        runtime = self.runtime if self.runtime in _VALID_RUNTIMES else RUNTIME_CLOUD
        return ThroughputConfig(
            daily_target=max(0, int(self.daily_target)),
            channels=max(1, int(self.channels)),
            runtime=runtime,
            local_bridge_cap_per_machine=max(1, int(self.local_bridge_cap_per_machine)),
            warm_seconds_per_article=max(1.0, float(self.warm_seconds_per_article)),
            cold_seconds_per_article=max(1.0, float(self.cold_seconds_per_article)),
            active_hours_per_day=min(24.0, max(0.1, float(self.active_hours_per_day))),
            first_pass_rate=min(1.0, max(0.01, float(self.first_pass_rate))),
            utilization=min(1.0, max(0.01, float(self.utilization))),
        )


@dataclass(frozen=True)
class Scenario:
    """单一耗时假设下的容量推算（warm / cold / blended）。"""

    label: str
    seconds_per_article: float
    effective_seconds_per_article: float
    articles_per_channel_per_day: float
    achievable_daily: float
    required_channels: int
    meets_target: bool


@dataclass(frozen=True)
class ConstraintNote:
    kind: str  # code_addressable | external
    summary: str


@dataclass(frozen=True)
class ThroughputPlan:
    config: ThroughputConfig
    scenarios: list[Scenario]
    primary_scenario: str
    required_channels_for_target: int
    required_local_machines: int
    achievable_daily_at_configured_channels: float
    meets_target: bool
    constraints: list[ConstraintNote] = field(default_factory=list)

    def to_report(self) -> dict[str, Any]:
        cfg = self.config
        return {
            "schema": "quwoquan_data.throughput_plan",
            "input": {
                "dailyTarget": cfg.daily_target,
                "channels": cfg.channels,
                "runtime": cfg.runtime,
                "localBridgeCapPerMachine": cfg.local_bridge_cap_per_machine,
                "warmSecondsPerArticle": round(cfg.warm_seconds_per_article, 3),
                "coldSecondsPerArticle": round(cfg.cold_seconds_per_article, 3),
                "activeHoursPerDay": round(cfg.active_hours_per_day, 3),
                "firstPassRate": round(cfg.first_pass_rate, 4),
                "utilization": round(cfg.utilization, 4),
            },
            "primaryScenario": self.primary_scenario,
            "scenarios": [
                {
                    "label": s.label,
                    "secondsPerArticle": round(s.seconds_per_article, 3),
                    "effectiveSecondsPerArticle": round(s.effective_seconds_per_article, 3),
                    "articlesPerChannelPerDay": round(s.articles_per_channel_per_day, 3),
                    "achievableDaily": round(s.achievable_daily, 1),
                    "requiredChannels": s.required_channels,
                    "meetsTarget": s.meets_target,
                }
                for s in self.scenarios
            ],
            "requiredChannelsForTarget": self.required_channels_for_target,
            "requiredLocalMachines": self.required_local_machines,
            "achievableDailyAtConfiguredChannels": round(
                self.achievable_daily_at_configured_channels, 1
            ),
            "meetsTarget": self.meets_target,
            "constraints": [
                {"kind": c.kind, "summary": c.summary} for c in self.constraints
            ],
        }


def _build_scenario(label: str, seconds: float, cfg: ThroughputConfig) -> Scenario:
    # 折损：首轮未通过的作业要重试，等价于把单篇有效耗时按 first_pass_rate 放大；
    # utilization 吸收编排/审核/空窗等非创作墙钟。
    effective = seconds / (cfg.first_pass_rate * cfg.utilization)
    active_seconds = cfg.active_hours_per_day * 3600.0
    per_channel = active_seconds / effective if effective > 0 else 0.0
    achievable = per_channel * cfg.channels
    required = (
        math.ceil(cfg.daily_target / per_channel) if per_channel > 0 else 0
    )
    return Scenario(
        label=label,
        seconds_per_article=seconds,
        effective_seconds_per_article=effective,
        articles_per_channel_per_day=per_channel,
        achievable_daily=achievable,
        required_channels=required,
        meets_target=achievable >= cfg.daily_target,
    )


def compute_throughput_plan(config: ThroughputConfig) -> ThroughputPlan:
    """从配置推算容量计划（纯函数，确定性，无 IO）。"""
    cfg = config.normalized()
    blended_seconds = (cfg.warm_seconds_per_article + cfg.cold_seconds_per_article) / 2.0
    scenarios = [
        _build_scenario("warm", cfg.warm_seconds_per_article, cfg),
        _build_scenario("cold", cfg.cold_seconds_per_article, cfg),
        _build_scenario("blended", blended_seconds, cfg),
    ]
    primary = next(s for s in scenarios if s.label == "blended")
    required_channels = primary.required_channels
    required_machines = (
        math.ceil(required_channels / cfg.local_bridge_cap_per_machine)
        if cfg.runtime == RUNTIME_LOCAL and cfg.local_bridge_cap_per_machine > 0
        else required_channels
    )
    constraints = _classify_constraints(cfg, primary, required_channels)
    return ThroughputPlan(
        config=cfg,
        scenarios=scenarios,
        primary_scenario=primary.label,
        required_channels_for_target=required_channels,
        required_local_machines=required_machines,
        achievable_daily_at_configured_channels=primary.achievable_daily,
        meets_target=primary.meets_target,
        constraints=constraints,
    )


def _classify_constraints(
    cfg: ThroughputConfig,
    primary: Scenario,
    required_channels: int,
) -> list[ConstraintNote]:
    notes: list[ConstraintNote] = []
    notes.append(
        ConstraintNote(
            kind="code_addressable",
            summary=(
                "单机本地 bridge 冷启竞态由 P6 错峰冷启释放器 + 冷启并发上限 + per-worker 暖机收敛；"
                "per-workspace 启动锁解除多 clone 间的全局串行，使多 clone/多机 bridge 启动可并行。"
            ),
        )
    )
    if cfg.runtime == RUNTIME_LOCAL:
        cap = max(1, int(cfg.local_bridge_cap_per_machine))
        machines = math.ceil(required_channels / cap) if required_channels > 0 else 0
        notes.append(
            ConstraintNote(
                kind="external",
                summary=(
                    f"单机本地有效并发上限 ≈ {cap}（共享 workspace bridge 物理上限）；"
                    f"达目标需 ≈ {machines} 台机器/clone 横向铺开（外部基础设施）。"
                ),
            )
        )
    else:
        notes.append(
            ConstraintNote(
                kind="external",
                summary=(
                    f"云端每通道=独立 agent，瓶颈在平台并发配额与多 key/账号；"
                    f"达目标需 ≈ {required_channels} 个并行云 agent 通道（平台配额 + 多账号，外部约束）。"
                ),
            )
        )
    if not primary.meets_target:
        notes.append(
            ConstraintNote(
                kind="external",
                summary=(
                    f"当前配置 channels={cfg.channels} 仅可达 ≈ {round(primary.achievable_daily):,}/日，"
                    f"低于目标 {cfg.daily_target:,}/日；缺口须靠扩通道（外部），代码侧已无单机可解空间。"
                ),
            )
        )
    return notes
