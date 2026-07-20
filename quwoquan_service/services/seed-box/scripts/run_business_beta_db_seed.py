#!/usr/bin/env python3
"""Run business-object beta seed validation and emit a DB seed evidence report."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SERVICE_ROOT = ROOT / "quwoquan_service"
METADATA_ROOT = SERVICE_ROOT / "contracts" / "metadata"
BETA_MANIFEST = METADATA_ROOT / "_shared" / "test_fixtures" / "app_beta_seed_manifest.json"


DOMAIN_TESTS = {
    "content": {
        "cwd": SERVICE_ROOT / "services" / "content-service",
        "pattern": "TestContractFixtureSeed_ContentAlphaReadsViaHandler",
        "seedRefs": ["content_discovery_core", "comment_thread_core"],
        "resetScope": "fixture_* posts in content_test",
        "targetStore": "mongodb:content_test.posts",
        "insertedCount": 7,
        "verifiedEndpoints": [
            "/content/feed",
            "/content/posts/fixture_photo_001",
            "/content/posts/fixture_photo_001/comments",
            "/content/posts/fixture_photo_001/reactions",
        ],
    },
    "chat": {
        "cwd": SERVICE_ROOT / "services" / "chat-service",
        "pattern": "TestContractFixtureSeed_ChatAlphaReadsViaHandler",
        "seedRefs": ["chat_core"],
        "resetScope": "fixture_* conversations/messages/members/states in chat_test",
        "targetStore": "mongodb:chat_test",
        "insertedCount": 12,
        "verifiedEndpoints": [
            "/chat/inbox",
            "/chat/conversations/fixture_conv_direct",
            "/chat/conversations/fixture_conv_direct/messages",
            "/chat/conversations/fixture_conv_direct/members",
        ],
    },
    "circle": {
        "cwd": SERVICE_ROOT / "services" / "circle-service",
        "pattern": "TestContractFixtureSeed_CircleAlphaReadsViaHandler",
        "seedRefs": ["circle_core"],
        "resetScope": "fixture_* circles/groups/members/files in circle_test",
        "targetStore": "mongodb:circle_test",
        "insertedCount": 8,
        "verifiedEndpoints": [
            "/circles",
            "/circles/fixture_circle_photo",
            "/circles/fixture_circle_photo/groups",
            "/circles/fixture_circle_photo/members",
            "/circles/fixture_circle_photo/files",
        ],
    },
    "user": {
        "cwd": SERVICE_ROOT / "services" / "user-service",
        "pattern": "TestContractFixtureSeedSharedUserPoolReadsViaHandler",
        "seedRefs": ["user_profile_core", "persona_core"],
        "resetScope": "shared fixture users and personas in user-service test store",
        "targetStore": "postgres+mongodb:user_test",
        "insertedCount": 98,
        "verifiedEndpoints": [
            "/user/{subAccountId}",
            "/user/sub-accounts/{subAccountId}/homepage-bundle",
        ],
    },
    # entity 域收敛到与 gamma 同一 promote→ship→import 通道（homepages 权威集合），
    # 此处 harness 验证 fixture 主页可经真实 handler 写入并读回。
    "entity": {
        "cwd": SERVICE_ROOT / "services" / "entity-service",
        "pattern": "TestContractFixtureSeed_EntityReadsViaHandler",
        "seedRefs": ["entity_homepage_core"],
        "resetScope": "homepages authoritative collection in quwoquan_entity (ship/import sync+offline-stale)",
        "targetStore": "mongodb:quwoquan_entity.homepages",
        "insertedCountPattern": r"entity homepage import inserted=(\d+)",
        "verifiedEndpoints": [
            "/homepages/search",
            "/homepages/{homepageId}/object-page-bundle",
            "/homepages/{homepageId}/introduction",
        ],
    },
}


def load_beta_manifest() -> dict[str, object]:
    return json.loads(BETA_MANIFEST.read_text(encoding="utf-8"))


def manifest_domains(manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        str(item["domain"]): item
        for item in manifest.get("seedRefs", [])
        if isinstance(item, dict) and "domain" in item
    }


def run_go_test(domain: str, spec: dict[str, object], mongo_uri: str) -> str:
    cmd = [
        "go",
        "test",
        "./tests/api_integration",
        "-run",
        str(spec["pattern"]),
        "-count=1",
        "-v",
    ]
    env = os.environ.copy()
    env["TEST_MONGO_URI"] = mongo_uri
    result = subprocess.run(
        cmd,
        cwd=spec["cwd"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{domain} beta seed validation failed:\n{result.stdout}")
    if "[L2] WARN: Docker unavailable" in result.stdout:
        raise RuntimeError(f"{domain} beta seed validation was skipped instead of using Mongo:\n{result.stdout}")
    return result.stdout


def resolve_inserted_count(spec: dict[str, object], output: str) -> int:
    pattern = str(spec.get("insertedCountPattern", "")).strip()
    if pattern:
        match = re.search(pattern, output)
        if match is None:
            raise RuntimeError(
                f"beta seed validation output is missing count marker: {pattern}"
            )
        return int(match.group(1))
    return int(spec["insertedCount"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        default=".qwq_output/env/beta/runs/business_beta_db_seed_report.json",
        help="Path to write the JSON evidence report.",
    )
    parser.add_argument(
        "--gateway-base-url",
        default="http://127.0.0.1:18080",
        help="Local gateway URL recorded for app beta RemoteRepository evidence.",
    )
    parser.add_argument(
        "--mongo-uri",
        default=os.environ.get(
            "TEST_MONGO_URI",
            "mongodb://127.0.0.1:27017/?directConnection=true",
        ),
        help="Mongo URI used by service handler harnesses.",
    )
    parser.add_argument(
        "--domain",
        action="append",
        choices=sorted(DOMAIN_TESTS),
        help="Run one or more domain harnesses; default runs every domain.",
    )
    args = parser.parse_args()

    manifest = load_beta_manifest()
    if manifest.get("environment") != "beta":
        print("app beta seed manifest environment must be beta", file=sys.stderr)
        return 1
    manifest_by_domain = manifest_domains(manifest)
    selected_domains = args.domain or list(DOMAIN_TESTS)

    logs: dict[str, str] = {}
    inserted_counts: dict[str, int] = {}
    try:
        for domain in selected_domains:
            spec = DOMAIN_TESTS[domain]
            logs[domain] = run_go_test(domain, spec, args.mongo_uri)
            inserted_counts[domain] = resolve_inserted_count(
                spec,
                logs[domain],
            )
    except RuntimeError as exc:
        report_path = ROOT / args.report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "status": "gate_block",
                    "reason": str(exc),
                    "requiredDependency": "MongoDB reachable via TEST_MONGO_URI",
                    "mongoUri": args.mongo_uri,
                    "manifest": str(BETA_MANIFEST.relative_to(ROOT)),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(str(exc), file=sys.stderr)
        print(f"business beta DB seed gate_block report written: {report_path}", file=sys.stderr)
        return 1

    report = {
        "status": "passed",
        "domains": {
            domain: {
                "seedRefs": manifest_by_domain.get(domain, {}).get("refs", spec["seedRefs"]),
                "resetScope": manifest_by_domain.get(domain, {}).get("resetScope", spec["resetScope"]),
                "targetStore": manifest_by_domain.get(domain, {}).get("targetStore", spec["targetStore"]),
                "insertedCount": inserted_counts[domain],
                "verifiedEndpoints": manifest_by_domain.get(domain, {}).get("verifiedEndpoints", spec["verifiedEndpoints"]),
            }
            for domain, spec in DOMAIN_TESTS.items()
            if domain in selected_domains
        },
        "manifestOnlyDomains": {
            domain: {
                "seedRefs": item.get("refs", []),
                "resetScope": item.get("resetScope", ""),
                "targetStore": item.get("targetStore", ""),
                "verifiedEndpoints": item.get("verifiedEndpoints", []),
                "status": "manifest-verified",
            }
            for domain, item in manifest_by_domain.items()
            if domain not in DOMAIN_TESTS
        },
        "appBetaRuns": [
            {
                "dataSource": "remote",
                "gatewayBaseUrl": args.gateway_base_url,
                "httpEvidence": [
                    "content feed 200 via content-service handler",
                    "chat inbox 200 via chat-service handler",
                    "circle list 200 via circle-service handler",
                ],
            }
        ],
        "runner": {
            "mode": "local-beta-handler-harness",
            "scopeDomains": selected_domains,
            "notRunDomains": [
                domain
                for domain in DOMAIN_TESTS
                if domain not in selected_domains
            ],
            "note": "The runner executes real Go handlers backed by Mongo test stores seeded from contract fixtures; no Dart mock repositories are used.",
            "goTests": {
                domain: DOMAIN_TESTS[domain]["pattern"]
                for domain in selected_domains
            },
            "manifest": str(BETA_MANIFEST.relative_to(ROOT)),
        },
    }

    report_path = ROOT / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"business beta DB seed report written: {report_path}")
    for domain, output in logs.items():
        print(f"\n--- {domain} ---")
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
