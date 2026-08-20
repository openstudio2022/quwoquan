"""Read-only, user-facing view of the three content-pool decisions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.execution.campaign.lane import normalize_workloads
from content.release.canonical.aggregate_release_pool import pool_post_refs
from content.release.canonical.aggregate_release_pool_closure import (
    entity_candidate_closure,
)
from content.release.canonical.canonical_identity_state import (
    CanonicalIdentityStateQuery,
)
from content.release.canonical.effective_admission import (
    effective_source_attribution_ready,
)
from content.release.canonical.environment_release_selection import (
    DATA_POST_CAPS,
    MILESTONE_TARGETS,
    select_environment_release_posts,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)
from content.release.canonical.pool_delivery_intent_inspection import (
    inspect_pool_delivery_intents,
)
from content.release.canonical.pool_inspection_support import (
    _SUPPLY_TYPES,
    M100_TARGETS,
    _admission_record,
    _author_admitted,
    _author_closure_ready,
    _content_admitted,
    _eligibility_passed,
    _entity_closure_ready,
    _issue,
    _manifest_refs,
    _not_admitted_issue,
    _reason_summary,
    _resolved_admission,
)
from content.release.canonical.pool_semantic_scheduling import (
    semantic_scheduling_projection,
)


def inspect_pool(
    *,
    publish_root: Path,
    include_issues: bool = False,
    strict_delivery: bool = True,
    include_batches: bool = False,
    output_root: Path | None = None,
    milestone: str | None = None,
    execution_ids: Sequence[str] = (),
    source_ready_backlog: Mapping[str, int] | None = None,
    p10_per_slot_throughput: Mapping[str, float] | None = None,
    source_ready_candidates: Mapping[str, list[Mapping[str, Any]]] | None = None,
    source_ready_input: Mapping[str, Any] | None = None,
    throughput_input: Mapping[str, str] | None = None,
    workload_targets: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Report quality, eligibility and delivery without mutating pool facts."""

    source_scale = (
        str(source_ready_input.get("targetScale") or "").strip()
        if isinstance(source_ready_input, Mapping)
        else ""
    )
    milestone_name = str(milestone or "").strip() or (
        "WORKLOAD" if workload_targets is not None else source_scale or "M100"
    )
    targets = MILESTONE_TARGETS.get(milestone_name)
    if targets is None and milestone_name != "WORKLOAD":
        raise ValueError(f"unsupported milestone: {milestone_name!r}")
    requested_workloads = (
        normalize_workloads(workload_targets) if workload_targets is not None else None
    )
    source_workloads = None
    if (
        isinstance(source_ready_input, Mapping)
        and source_ready_input.get("status") == "validated"
    ):
        source_workloads = normalize_workloads(
            source_ready_input.get("workloadTargets", {})
        )
    if (
        requested_workloads is not None
        and source_workloads is not None
        and requested_workloads != source_workloads
    ):
        raise ValueError("pool inspection workloadTargets drift from source pool")
    explicit_workloads = source_workloads or requested_workloads
    if milestone_name == "WORKLOAD" and explicit_workloads is None:
        raise ValueError("WORKLOAD inspection requires explicit workloadTargets")
    effective_targets = explicit_workloads or dict(targets or {})
    active_carriers = tuple(effective_targets)
    workload_mode = (
        str(source_ready_input["workloadMode"])
        if source_workloads is not None
        else ("explicit" if requested_workloads is not None else "milestone_preset")
    )
    issues: list[dict[str, str]] = []
    identity_query = CanonicalIdentityStateQuery(publish_root=publish_root)
    canonical_identity_states: list[dict[str, Any]] = []
    author_admission: dict[str, bool] = {}
    creators_root = publish_root / "creators"
    if creators_root.is_dir():
        for creator_root in sorted(creators_root.iterdir()):
            if not creator_root.is_dir():
                continue
            profile_path = creator_root / "profile.json"
            profile = _read_json(profile_path) if profile_path.is_file() else {}
            record = _admission_record(
                creator_root,
                profile,
                object_type="author",
            )
            admitted = _author_admitted(record)
            author_admission[creator_root.name] = admitted
            if not admitted:
                _not_admitted_issue(
                    issues,
                    record=record,
                    admission_missing=record is None,
                    ref=f"creators/{creator_root.name}",
                )

    observed = Counter()
    admitted = Counter()
    publishable = Counter()
    scopes = Counter()
    admission_missing = Counter()
    pending_delivery: list[dict[str, Any]] = []
    if output_root is not None:
        pending_delivery, intent_issues = inspect_pool_delivery_intents(
            output_root=output_root,
            publish_root=publish_root,
            execution_ids=tuple(execution_ids),
        )
        issues.extend(intent_issues)
    pending_by_carrier = Counter(str(row["carrier"]) for row in pending_delivery)

    for entity_ref, path in _manifest_refs(publish_root / "entities"):
        observed["homepage"] += 1
        manifest = _read_json(path)
        identity_state = identity_query.get(
            object_type="homepage",
            object_ref=f"entities/{entity_ref}",
        )
        canonical_identity_states.append(identity_state)
        if identity_state["state"].startswith("invalid_"):
            _issue(
                issues,
                gate="eligibility",
                code=str(identity_state["deepestError"]),
                ref=f"entities/{entity_ref}",
            )
            continue
        if identity_state["state"] == "terminated":
            _issue(
                issues,
                gate="eligibility",
                code="DATA.POOL.IDENTITY_TERMINATED",
                ref=f"entities/{entity_ref}",
            )
            continue
        entity_admission = _resolved_admission(
            path.parent,
            manifest,
            object_type="homepage",
        )
        record = entity_admission.record
        if not _content_admitted(record):
            record_missing = bool(
                record is None and (path.parent / "attestation.json").is_file()
            )
            admission_missing["homepage"] += int(record_missing)
            _not_admitted_issue(
                issues,
                record=record,
                admission_missing=record_missing,
                ref=f"entities/{entity_ref}",
            )
            continue
        admitted["homepage"] += 1
        scopes[str(record["usageScope"])] += 1
        if not _author_closure_ready(
            object_root=path.parent,
            document=manifest,
            author_admission=author_admission,
        ):
            _issue(
                issues,
                gate="delivery",
                code="DATA.POOL.AUTHOR_NOT_ADMITTED",
                ref=f"entities/{entity_ref}",
            )
            continue
        if strict_delivery:
            try:
                if not effective_source_attribution_ready(entity_admission):
                    raise ObjectTransactionError(
                        "DATA.POOL.SOURCE_ATTRIBUTION_INCOMPLETE"
                    )
                entity_candidate_closure(
                    publish_root,
                    entity_ref=entity_ref,
                    release_mode="research",
                )
            except (OSError, TypeError, ValueError, ObjectTransactionError) as exc:
                code = str(exc).split(":", 1)[0]
                if not code.startswith("DATA."):
                    code = "DATA.POOL.REFERENCE_MISSING"
                _issue(
                    issues,
                    gate="delivery",
                    code=code,
                    ref=f"entities/{entity_ref}",
                )
                continue
        publishable["homepage"] += 1

    for post_ref, path in _manifest_refs(publish_root / "posts"):
        manifest = _read_json(path)
        carrier = str(manifest.get("contentType") or "").strip()
        if carrier not in {"article", "image", "video"}:
            _issue(
                issues,
                gate="quality",
                code="DATA.POOL.OBJECT_NOT_ADMITTED",
                ref=f"posts/{post_ref}",
            )
            continue
        observed[carrier] += 1
        identity_state = identity_query.get(
            object_type="content",
            object_ref=f"posts/{post_ref}",
        )
        canonical_identity_states.append(identity_state)
        if identity_state["state"].startswith("invalid_"):
            _issue(
                issues,
                gate="eligibility",
                code=str(identity_state["deepestError"]),
                ref=f"posts/{post_ref}",
            )
            continue
        if identity_state["state"] == "terminated":
            _issue(
                issues,
                gate="eligibility",
                code="DATA.POOL.IDENTITY_TERMINATED",
                ref=f"posts/{post_ref}",
            )
            continue
        post_admission = _resolved_admission(
            path.parent,
            manifest,
            object_type="content",
        )
        record = post_admission.record
        if not _content_admitted(record):
            record_missing = bool(
                record is None and manifest.get("reviewDecision") == "approved"
            )
            admission_missing[carrier] += int(record_missing)
            _not_admitted_issue(
                issues,
                record=record,
                admission_missing=record_missing,
                ref=f"posts/{post_ref}",
            )
            continue
        admitted[carrier] += 1
        scopes[str(record["usageScope"])] += 1
        if not _author_closure_ready(
            object_root=path.parent,
            document=manifest,
            author_admission=author_admission,
        ):
            _issue(
                issues,
                gate="delivery",
                code="DATA.POOL.AUTHOR_NOT_ADMITTED",
                ref=f"posts/{post_ref}",
            )
            continue
        if strict_delivery and not effective_source_attribution_ready(post_admission):
            _issue(
                issues,
                gate="delivery",
                code="DATA.POOL.SOURCE_ATTRIBUTION_INCOMPLETE",
                ref=f"posts/{post_ref}:sourceAttribution",
            )
            continue
        if not _entity_closure_ready(
            publish_root=publish_root,
            raw_refs=manifest.get("entityRefs"),
        ):
            _issue(
                issues,
                gate="delivery",
                code="DATA.POOL.REFERENCE_MISSING",
                ref=f"posts/{post_ref}:entityRefs",
            )
            continue
        publishable[carrier] += 1

    strict_capacity: dict[str, int] | None = None
    if strict_delivery:
        strict_capacity = {}
        selections = {}
        post_refs = pool_post_refs(publish_root)
        for environment in DATA_POST_CAPS:
            try:
                selections[environment] = select_environment_release_posts(
                    publish_root=publish_root,
                    post_refs=post_refs,
                    environment=environment,
                    release_class="research",
                    strict_admission=True,
                )
                strict_capacity[environment] = selections[environment].counts["total"]
            except (OSError, TypeError, ValueError, ObjectTransactionError):
                strict_capacity[environment] = 0
        research_selection = selections.get("gamma")
        if research_selection is not None:
            counts = research_selection.counts
            for carrier in ("article", "image", "video"):
                publishable[carrier] = counts[carrier]
            superseded = Counter()
            selected_refs = set(research_selection.post_refs)
            excluded_refs = {row.post_ref for row in research_selection.excluded}
            for post_ref, path in _manifest_refs(publish_root / "posts"):
                manifest = _read_json(path)
                carrier = str(manifest.get("contentType") or "").strip()
                if (
                    carrier in {"article", "image", "video"}
                    and post_ref not in selected_refs
                    and post_ref not in excluded_refs
                ):
                    superseded[carrier] += 1
            for excluded in research_selection.excluded:
                ref = f"posts/{excluded.post_ref}"
                if any(row["ref"].split(":", 1)[0] == ref for row in issues):
                    continue
                _issue(
                    issues,
                    gate=excluded.gate,
                    code=excluded.code,
                    ref=ref,
                )
    publishable_total = sum(publishable.values())
    if publishable_total == 0:
        _issue(
            issues,
            gate="delivery",
            code="DATA.POOL.EMPTY",
            ref="publish",
        )
    issues = sorted(issues, key=lambda row: (row["gate"], row["code"], row["ref"]))
    supply = {
        supply_type: {
            "observed": observed[supply_type],
            "admitted": admitted[supply_type],
            "publishable": publishable[supply_type],
            "deliveryPending": max(
                0,
                admitted[supply_type]
                - publishable[supply_type]
                - (superseded[supply_type] if strict_delivery else 0),
            )
            + pending_by_carrier[supply_type],
            "explicitAdmissionPending": admission_missing[supply_type],
            "target": effective_targets[supply_type],
            "gap": max(0, effective_targets[supply_type] - publishable[supply_type]),
        }
        for supply_type in active_carriers
    }
    research_post_count = sum(publishable[carrier] for carrier in _SUPPLY_TYPES[1:])
    # Environment capacity is a delivery estimate for Posts only. Homepage,
    # Author, Entity and media closure do not consume the Data Post cap.
    environment_capacity = strict_capacity or {
        environment: (
            min(
                research_post_count,
                cap,
            )
            if cap is not None
            else research_post_count
        )
        for environment, cap in DATA_POST_CAPS.items()
    }
    checks = {
        gate: ("failed" if any(row["gate"] == gate for row in issues) else "passed")
        for gate in ("quality", "eligibility", "delivery")
    }
    next_wave = [
        {
            "carrier": supply_type,
            "requestedCandidateCount": max(
                0,
                effective_targets[supply_type] - publishable[supply_type],
            ),
        }
        for supply_type in sorted(
            active_carriers,
            key=lambda item: (
                -max(0, effective_targets[item] - publishable[item]),
                _SUPPLY_TYPES.index(item),
            ),
        )
        if publishable[supply_type] < effective_targets[supply_type]
    ]
    target_attained = not next_wave
    result = (
        "ready" if target_attained else ("partial" if publishable_total else "blocked")
    )
    report: dict[str, Any] = {
        "schema": "quwoquan_data.pool_inspection",
        "result": result,
        "milestone": milestone_name,
        "workloadMode": workload_mode,
        "activeCarriers": list(active_carriers),
        "workloadTargets": effective_targets,
        "targetAttained": target_attained,
        "checks": checks,
        "authors": {
            "observed": len(author_admission),
            "admitted": sum(author_admission.values()),
        },
        "supply": supply,
        "usageScope": {
            "research": scopes["research"],
            "commercial": scopes["commercial"],
        },
        "environmentCapacity": environment_capacity,
        "reasons": _reason_summary(issues),
        "issueCount": len(issues),
        "nextWave": next_wave,
        "canonicalIdentityStates": canonical_identity_states,
        "pendingDelivery": pending_delivery,
        "semanticScheduling": semantic_scheduling_projection(
            milestone=milestone_name,
            supply=supply,
            source_ready_backlog=source_ready_backlog,
            p10_per_slot_throughput=p10_per_slot_throughput,
            source_ready_candidates=source_ready_candidates,
            source_ready_input=source_ready_input,
            throughput_input=throughput_input,
            workload_targets=explicit_workloads,
        ),
    }
    if include_issues:
        report["issues"] = issues
    if include_batches:
        if output_root is None:
            from core.paths import OUTPUT_ROOT

            output_root = Path(OUTPUT_ROOT)
        from content.release.canonical.pool_batch_observability import (
            build_batch_statistics,
        )

        report["batches"] = build_batch_statistics(
            publish_root=publish_root,
            output_root=output_root,
            issues=issues,
            pending_delivery=pending_delivery,
            execution_ids=tuple(execution_ids),
        )
    return report


__all__ = ["M100_TARGETS", "_eligibility_passed", "inspect_pool"]
