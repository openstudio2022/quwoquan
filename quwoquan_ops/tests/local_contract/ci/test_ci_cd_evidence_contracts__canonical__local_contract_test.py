"""local_contract: atomic-cutover CI/CD evidence governance stays single-track."""

from __future__ import annotations

from pathlib import Path

import yaml

from quwoquan_ops.gate import verify_ci_cd_evidence_contracts as gate

REPO_ROOT = Path(__file__).resolve().parents[4]


def parsed_workflow(source: str) -> dict[object, object]:
    value = yaml.safe_load(source)
    assert isinstance(value, dict)
    return value


def test_repository_evidence_chain_has_no_contract_drift() -> None:
    assert gate.evidence_contract_findings(REPO_ROOT) == []


def test_release_control_requires_every_two_phase_tag_api_call() -> None:
    relative_path = "quwoquan_ops/ci/release_control.py"
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    required = gate.REQUIRED_SOURCE_TOKENS[relative_path]
    canonical = (
        "create_release_candidate_tag_intent",
        "create_release_tag_intent",
        "record_tag_mutation_outcome",
        "finalize_release_candidate_tag_admission",
        "finalize_release_tag_admission",
    )

    # 表头为 promotion admission、release train 两个生产者（initial authority / rc selection）与 qualification 两步。
    assert required[5:-1] == canonical
    for api in canonical:
        without_stage = source.replace(api, f"removed_{api}")
        findings = gate.release_control_tag_api_findings(relative_path, without_stage)
        assert [finding.detail for finding in findings] == [
            f"canonical release tag API call is missing: {api}"
        ]


def test_retired_tag_callables_cannot_satisfy_the_two_phase_gate() -> None:
    relative_path = "quwoquan_ops/ci/release_control.py"
    required = gate.REQUIRED_SOURCE_TOKENS[relative_path]
    retired = ("admit_release_candidate_tag", "admit_release_tag")
    legacy_only = "\n".join(f"{api}()" for api in retired)

    assert not set(retired) & set(required)
    details = {
        finding.detail
        for finding in gate.release_control_tag_api_findings(
            relative_path, legacy_only
        )
    }
    assert details == {
        f"canonical release tag API call is missing: {api}"
        for api in required[4:-1]
    }


def test_gate_repo_invokes_the_atomic_cutover_evidence_gate() -> None:
    gate_source = (REPO_ROOT / "quwoquan_ops/gate/gate_repo.sh").read_text(
        encoding="utf-8"
    )

    assert gate.ENVIRONMENT_ACCEPTANCE_V2 == (
        "quwoquan_ops.environment_acceptance_fact.v2"
    )
    assert set(gate.REQUIRED_RELEASE_WORKFLOWS) == {
        ".github/workflows/release-qualification.yml",
        ".github/workflows/release-tag-selection.yml",
        ".github/workflows/deploy-prod-auto.yml",
    }
    assert "python3 quwoquan_ops/gate/verify_ci_cd_evidence_contracts.py" in gate_source


def test_retired_implementations_are_not_canonical_requirements() -> None:
    assert not set(gate.CHAIN_FILES) & gate.RETIRED_CANONICAL_IMPLEMENTATIONS
    assert not set(gate.REQUIRED_SOURCE_TOKENS) & gate.RETIRED_CANONICAL_IMPLEMENTATIONS
    assert "quwoquan_ops.environment_acceptance_fact.v1" not in (
        gate.CANONICAL_EVIDENCE_IDENTITIES
    )
    assert "release-environment-receipt" not in gate.CANONICAL_EVIDENCE_IDENTITIES
    assert "green-matrix" not in gate.CANONICAL_EVIDENCE_IDENTITIES


def test_four_retired_workflows_are_mechanically_rejected(tmp_path: Path) -> None:
    for retired in gate.RETIRED_WORKFLOWS:
        path = tmp_path / retired
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("name: retired\non: workflow_dispatch\n", encoding="utf-8")

    findings = gate.evidence_contract_findings(tmp_path)
    rejected = {
        finding.path
        for finding in findings
        if finding.detail == "retired workflow must not exist after atomic cutover"
    }

    assert rejected == gate.RETIRED_WORKFLOWS


def test_active_workflow_rejects_mutable_and_bare_source_authority() -> None:
    source = """name: invalid release
on: workflow_dispatch
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - run: echo "$RELEASED_RELEASE_EVIDENCE_REF"
      - run: cat selectors/latestQualified.json
      - run: test "$SOURCE_GIT_SHA" = promotable
      - run: consume release-environment-receipt
      - run: consume green-matrix
"""

    findings = gate.active_workflow_findings(
        ".github/workflows/invalid.yml", source, parsed_workflow(source)
    )
    details = [finding.detail for finding in findings]

    assert sum("mutable release authority" in detail for detail in details) == 2
    assert "bare source promotable fallback is forbidden" in details
    assert (
        "active workflow requires retired evidence: release-environment-receipt"
        in details
    )
    assert "active workflow requires retired evidence: green-matrix" in details


def test_factory_material_schemas_are_unversioned_and_rc_qualified() -> None:
    for relative_path, (expected_schema, expected_inputs) in (
        gate.FACTORY_WORKFLOW_CONTRACTS.items()
    ):
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        workflow = parsed_workflow(source)

        assert gate.factory_workflow_findings(
            relative_path,
            source,
            workflow,
            expected_schema=expected_schema,
            expected_inputs=expected_inputs,
        ) == []
        assert set(gate._workflow_on(workflow)) == {"workflow_call"}


def test_factory_material_gate_rejects_versioned_schema_identity() -> None:
    relative_path = ".github/workflows/app_pipeline.yml"
    expected_schema, expected_inputs = gate.FACTORY_WORKFLOW_CONTRACTS[relative_path]
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    versioned = source.replace(
        f'"schema": "{expected_schema}"',
        f'"schema": "{expected_schema}.v1"',
    )
    assert versioned != source

    findings = gate.factory_workflow_findings(
        relative_path,
        versioned,
        parsed_workflow(versioned),
        expected_schema=expected_schema,
        expected_inputs=expected_inputs,
    )

    assert [finding.detail for finding in findings] == [
        f"factory material schema must be exactly {expected_schema!r}"
    ]


def test_factory_inputs_have_exact_required_type_semantics() -> None:
    """spec_ref: deliver-deploy-prod-pipeline/SIT-001 and DEC-008."""

    expected_by_path = {
        ".github/workflows/app_pipeline.yml": {
            "source_git_sha": (True, "string"),
            "qualification_request_ref": (True, "string"),
            "qualification_request_digest": (True, "string"),
            "rc_tag_admission_ref": (True, "string"),
            "artifact_build_number": (True, "string"),
            "artifact_build_number_allocation_ref": (True, "string"),
            "artifact_build_number_allocation_digest": (True, "string"),
        },
        ".github/workflows/service_pipeline.yml": {
            "source_sha": (True, "string"),
            "rc_tag_admission_ref": (True, "string"),
            "qualification_request_ref": (True, "string"),
            "qualification_request_digest": (True, "string"),
            # 与 app_pipeline 同型：caller 传入的 job output 恒为字符串，number 声明会让 actionlint 类型校验失败。
            "artifact_build_number": (True, "string"),
            "artifact_build_number_allocation_ref": (True, "string"),
            "artifact_build_number_allocation_digest": (True, "string"),
        },
    }

    for relative_path, expected in expected_by_path.items():
        workflow = parsed_workflow(
            (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        )
        call = gate._workflow_on(workflow)["workflow_call"]
        assert isinstance(call, dict)
        inputs = call["inputs"]
        assert isinstance(inputs, dict)
        assert {
            name: (configuration.get("required"), configuration.get("type"))
            for name, configuration in inputs.items()
            if isinstance(configuration, dict)
        } == expected
        assert set(inputs) == set(gate.FACTORY_WORKFLOW_CONTRACTS[relative_path][1])


def test_service_factory_gate_rejects_missing_build_number_allocation_inputs() -> None:
    """spec_ref: deliver-deploy-prod-pipeline/SIT-001 and DEC-008."""

    relative_path = ".github/workflows/service_pipeline.yml"
    expected_schema, expected_inputs = gate.FACTORY_WORKFLOW_CONTRACTS[relative_path]
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    for missing in (
        "artifact_build_number",
        "artifact_build_number_allocation_ref",
        "artifact_build_number_allocation_digest",
    ):
        workflow = parsed_workflow(source)
        call = gate._workflow_on(workflow)["workflow_call"]
        assert isinstance(call, dict)
        inputs = call["inputs"]
        assert isinstance(inputs, dict)
        inputs.pop(missing)

        findings = gate.factory_workflow_findings(
            relative_path,
            source,
            workflow,
            expected_schema=expected_schema,
            expected_inputs=expected_inputs,
        )

        assert [finding.detail for finding in findings] == [
            "factory inputs must be exactly the explicit RC qualification inputs"
        ]


def test_service_factory_gate_rejects_every_optional_input() -> None:
    """spec_ref: deliver-deploy-prod-pipeline/SIT-001 and DEC-008."""

    relative_path = ".github/workflows/service_pipeline.yml"
    expected_schema, expected_inputs = gate.FACTORY_WORKFLOW_CONTRACTS[relative_path]
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    for optional_name in expected_inputs:
        workflow = parsed_workflow(source)
        call = gate._workflow_on(workflow)["workflow_call"]
        assert isinstance(call, dict)
        inputs = call["inputs"]
        assert isinstance(inputs, dict)
        configuration = inputs[optional_name]
        assert isinstance(configuration, dict)
        configuration["required"] = False

        findings = gate.factory_workflow_findings(
            relative_path,
            source,
            workflow,
            expected_schema=expected_schema,
            expected_inputs=expected_inputs,
        )

        assert [finding.detail for finding in findings] == [
            "every factory input must be required"
        ]


def test_service_factory_gate_rejects_extra_mutable_or_build_number_inputs() -> None:
    """spec_ref: deliver-deploy-prod-pipeline/SIT-001 and DEC-008."""

    relative_path = ".github/workflows/service_pipeline.yml"
    expected_schema, expected_inputs = gate.FACTORY_WORKFLOW_CONTRACTS[relative_path]
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    for extra_name in ("latest_qualification_request_ref", "build_number"):
        workflow = parsed_workflow(source)
        call = gate._workflow_on(workflow)["workflow_call"]
        assert isinstance(call, dict)
        inputs = call["inputs"]
        assert isinstance(inputs, dict)
        inputs[extra_name] = {"required": True, "type": "string"}

        findings = gate.factory_workflow_findings(
            relative_path,
            source,
            workflow,
            expected_schema=expected_schema,
            expected_inputs=expected_inputs,
        )

        assert [finding.detail for finding in findings] == [
            "factory inputs must be exactly the explicit RC qualification inputs"
        ]


def test_prod_workflow_rejects_main_push() -> None:
    source = """name: prod
on:
  push:
    branches: [main]
jobs:
  deploy:
    environment: production
    runs-on: ubuntu-latest
    steps: []
"""

    findings = gate.active_workflow_findings(
        ".github/workflows/prod.yml", source, parsed_workflow(source)
    )

    assert any(
        finding.detail == "main push must not trigger Prod behavior"
        for finding in findings
    )


def test_delivery_gate_rejects_execution_but_ignores_negative_declarations() -> None:
    allowed = """# build and package are forbidden here
- run: echo 'forbidden here: ABG, Provider live and device execution'
- run: python3 -B -m py_compile quwoquan_ops/ci/promotion_evidence.py
"""
    assert gate.promotion_workflow_findings(gate.PROMOTION_WORKFLOW, allowed) == []

    forbidden = """- uses: actions/setup-go@sha
- run: make build
- run: python3 quwoquan_ops/cli/stackctl.py package --kind app
- run: execute ABG matrix
- run: execute device matrix
- run: provider live
- run: execute alpha-environment
"""
    details = [
        finding.detail
        for finding in gate.promotion_workflow_findings(
            gate.PROMOTION_WORKFLOW, forbidden
        )
    ]
    assert len(details) == 7


def test_environment_acceptance_canonical_source_rejects_v1() -> None:
    source = 'SCHEMA = "quwoquan_ops.environment_acceptance_fact.v1"\n'

    findings = gate.scan_canonical_source("producer.py", source)

    assert [finding.detail for finding in findings] == [
        "retired evidence identity is forbidden: "
        "quwoquan_ops.environment_acceptance_fact.v1"
    ]


def test_active_workflow_rejects_retired_producer_but_not_negative_fixture() -> None:
    source = """name: old chain
on: workflow_dispatch
jobs:
  old:
    runs-on: ubuntu-latest
    steps:
      - run: python3 quwoquan_ops/ci/render_environment_release_receipt.py
"""
    findings = gate.active_workflow_findings(
        ".github/workflows/old.yml", source, parsed_workflow(source)
    )
    assert any("active workflow calls retired implementation" in item.detail for item in findings)

    negative = """name: migration assertion
on: workflow_dispatch
jobs:
  assert:
    runs-on: ubuntu-latest
    steps:
      - run: >-
          echo 'forbidden: render_environment_release_receipt.py must not run'
"""
    assert gate.active_workflow_findings(
        ".github/workflows/assert.yml", negative, parsed_workflow(negative)
    ) == []


def test_production_import_caller_is_rejected_without_scanning_string_fixtures(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "quwoquan_ops/ci"
    source_root.mkdir(parents=True)
    (source_root / "caller.py").write_text(
        "from quwoquan_ops.ci.render_environment_release_receipt import render\n",
        encoding="utf-8",
    )
    (source_root / "fixture.py").write_text(
        "value = 'from quwoquan_ops.ci.render_environment_release_receipt import render'\n",
        encoding="utf-8",
    )

    findings = gate.retired_import_findings(tmp_path)

    assert [(finding.path, finding.line) for finding in findings] == [
        ("quwoquan_ops/ci/caller.py", 1)
    ]



def _write_production_source(root: Path, relative_path: str, source: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_retired_writer_and_finalizer_bytes_are_deletion_gated(
    tmp_path: Path,
) -> None:
    for relative_path in gate.RETIRED_CANONICAL_IMPLEMENTATIONS:
        path = tmp_path / relative_path
        if path.suffix == ".py":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("raise SystemExit('retired')\n", encoding="utf-8")
        else:
            path.mkdir(parents=True, exist_ok=True)
            (path / "retired.py").write_text(
                "raise SystemExit('retired')\n", encoding="utf-8"
            )

    findings = gate.retired_implementation_findings(tmp_path)

    assert {finding.path for finding in findings} == (
        gate.RETIRED_CANONICAL_IMPLEMENTATIONS
    )
    assert {finding.detail for finding in findings} == {
        "retired writer/finalizer implementation must be deleted"
    }


def test_repository_has_deleted_retired_writer_and_finalizer_bytes() -> None:
    """spec_ref: deliver-deploy-prod-pipeline/SIT-001 and DEC-008."""

    assert gate.retired_implementation_findings(REPO_ROOT) == []


def test_retired_import_gate_covers_static_and_dynamic_bypasses(
    tmp_path: Path,
) -> None:
    sources = {
        "direct.py": (
            "import quwoquan_ops.cli.prod.finalize_mainline_release_artifact\n"
        ),
        "direct_alias.py": (
            "import quwoquan_ops.cli.prod.finalize_mainline_release_artifact as old\n"
        ),
        "from_module.py": (
            "from quwoquan_ops.cli.prod.finalize_mainline_release_artifact "
            "import finalize as finish\n"
        ),
        "from_parent.py": (
            "from quwoquan_ops.cli.prod import "
            "finalize_mainline_release_artifact as old\n"
        ),
        "import_module.py": (
            "import importlib as loader\n"
            "old = loader.import_module("
            "'quwoquan_ops.cli.prod.finalize_mainline_release_artifact')\n"
        ),
        "import_module_alias.py": (
            "from importlib import import_module as load\n"
            "old = load("
            "'quwoquan_ops.cli.prod.finalize_mainline_release_artifact')\n"
        ),
        "import_module_getattr.py": (
            "import importlib\n"
            "load = getattr(importlib, 'import_module')\n"
            "old = load("
            "'quwoquan_ops.cli.prod.finalize_mainline_release_artifact')\n"
        ),
        "import_module_relative.py": (
            "from importlib import import_module\n"
            "old = import_module("
            "'.finalize_mainline_release_artifact', "
            "'quwoquan_ops.cli.prod')\n"
        ),
        "dunder_import.py": (
            "old = __import__("
            "'quwoquan_ops.cli.prod.finalize_mainline_release_artifact')\n"
        ),
        "dunder_fromlist.py": (
            "old = __import__('quwoquan_ops.cli.prod', "
            "fromlist=['finalize_mainline_release_artifact'])\n"
        ),
        "dunder_positional_fromlist.py": (
            "old = __import__('quwoquan_ops.cli.prod', globals(), locals(), "
            "['finalize_mainline_release_artifact'])\n"
        ),
        "getattr_child.py": (
            "from quwoquan_ops.cli import prod\n"
            "old = getattr(prod, 'finalize_mainline_release_artifact')\n"
        ),
        "getattr_writer.py": (
            "import quwoquan_ops.cli.stackctl as stackctl\n"
            "writer = getattr(stackctl, '_command_package_release_manifest')\n"
        ),
    }
    for filename, source in sources.items():
        _write_production_source(
            tmp_path, f"quwoquan_ops/cli/{filename}", source
        )
    _write_production_source(
        tmp_path,
        "quwoquan_ops/cli/string_fixture.py",
        """FIXTURE = \"\"\"
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact
getattr(stackctl, '_command_package_release_manifest')
\"\"\"
assert 'finalize_mainline_release_artifact' not in 'current module'
""",
    )

    findings = gate.retired_import_findings(tmp_path)
    rejected_paths = {finding.path for finding in findings}

    assert rejected_paths == {
        f"quwoquan_ops/cli/{filename}" for filename in sources
    }


def test_retired_surface_gate_rejects_public_cli_writer_and_formal_option(
    tmp_path: Path,
) -> None:
    blocked = {
        "choice.py": "parser.add_argument('--kind', choices=['runtime', 'release-manifest'])\n",
        "dispatch.py": (
            "if package_kind == 'release-manifest':\n"
            "    dispatch()\n"
        ),
        "mapping.py": "handlers = {'release-manifest': writer}\n",
        "unlabelled_mapping.py": "routes = {'release-manifest': writer}\n",
        "membership.py": (
            "if package_kind in ('runtime', 'release-manifest'):\n"
            "    dispatch()\n"
        ),
        "match.py": (
            "match package_kind:\n"
            "    case 'release-manifest':\n"
            "        dispatch()\n"
        ),
        "argv.py": (
            "subprocess.run(['package', '--kind', 'release-manifest'])\n"
        ),
        "option.py": "parser.add_argument('--release-manifest', type=Path)\n",
        "reject_flag.py": "parser.add_argument('--release-manifest', action='store_true', help='legacy input')\n",
        "constant_option.py": (
            "OLD_OPTION = '--release-' + 'manifest'\n"
            "parser.add_argument(OLD_OPTION, type=Path)\n"
        ),
        "writer.py": "def _command_package_release_manifest(args):\n    pass\n",
    }
    for filename, source in blocked.items():
        _write_production_source(
            tmp_path, f"quwoquan_ops/cli/{filename}", source
        )
    _write_production_source(
        tmp_path,
        "quwoquan_ops/cli/allowed.py",
        """parser.add_argument('--release-tag-admission-ref')
parser.add_argument('--candidate-material-manifest-ref')
parser.add_argument('--android-release-manifest')
parser.add_argument('--web-release-manifest')
assert '--release-manifest' not in parser_source
FIXTURE = "package --kind release-manifest"
""",
    )

    findings = gate.retired_import_findings(tmp_path)
    rejected_paths = {finding.path for finding in findings}

    assert rejected_paths == {
        f"quwoquan_ops/cli/{filename}" for filename in blocked
    }


def test_historical_reader_exposes_only_named_read_side(
    tmp_path: Path,
) -> None:
    allowed_root = tmp_path / "allowed"
    _write_production_source(
        allowed_root,
        "quwoquan_ops/ci/release_evidence_reader.py",
        """def validate_frozen_diagnostic_snapshot(payload):
    return payload

def validate_historical_release_snapshot(payload):
    return payload

__all__ = (
    'validate_frozen_diagnostic_snapshot',
    'validate_historical_release_snapshot',
)
""",
    )
    _write_production_source(
        allowed_root,
        "quwoquan_ops/ci/diagnostic.py",
        """from quwoquan_ops.ci.release_evidence_reader import (
    validate_historical_release_snapshot,
    validate_frozen_diagnostic_snapshot,
)
""",
    )
    assert gate.retired_import_findings(allowed_root) == []

    blocked_root = tmp_path / "blocked"
    _write_production_source(
        blocked_root,
        "quwoquan_ops/ci/release_evidence_reader.py",
        """def validate_manifest(payload):
    return payload

def validate_manifest_files(root, payload):
    return payload

def finalize(payload):
    return payload

def release_verdict(payload):
    return payload

def publish_manifest(payload):
    return payload

def __getattr__(name):
    return globals()[name]

validate = validate_manifest
""",
    )
    _write_production_source(
        blocked_root,
        "quwoquan_ops/ci/generic_import.py",
        "from quwoquan_ops.ci.release_evidence_reader import validate_manifest\n",
    )
    _write_production_source(
        blocked_root,
        "quwoquan_ops/ci/dynamic_reader.py",
        """import importlib
reader = importlib.import_module('quwoquan_ops.ci.release_evidence_reader')
validator = getattr(reader, 'validate_manifest')
""",
    )

    findings = gate.retired_import_findings(blocked_root)
    rejected_paths = {finding.path for finding in findings}

    assert rejected_paths == {
        "quwoquan_ops/ci/release_evidence_reader.py",
        "quwoquan_ops/ci/generic_import.py",
        "quwoquan_ops/ci/dynamic_reader.py",
    }
