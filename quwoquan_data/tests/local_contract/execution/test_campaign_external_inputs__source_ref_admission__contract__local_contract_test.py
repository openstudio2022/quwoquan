# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

from pathlib import Path

import pytest
from content.execution.campaign import request_envelope as campaign_request_envelope
from content.execution.campaign import (
    request_envelope_build as campaign_request_envelope_build,
)
from content.execution.campaign import submission as campaign_submission
from content.execution.campaign import (
    submission_identity as campaign_submission_identity,
)
from content.execution.campaign.external_inputs import (
    CampaignExternalInputError,
    bind_external_input_refs,
    envelope_acquisition_root,
    external_inputs_digest,
    frozen_acquisition_root_ref,
    verify_external_input_refs,
)
import json

from content.execution.request import RuntimeExecutionRequest
from core import paths as core_paths
from core.control_types import TargetSelector
from core.io import write_json
from core.source_digest import ExecutionBundleIdentity, SourceDefinitionSnapshot
from core.paths import REPO_ROOT
from support.semantic_preflight_fixture import ready_semantic_preflight
from support.campaign_external_inputs_fixture import (  # noqa: F401
    CATALOG_DIGEST,
    SOURCE_DIGEST,
    SOURCE_REVISION,
    _acquisition,
    _governed_acquisition_handoff,
)


BUNDLE_DIGEST = "sha256:" + "b" * 64


class _FrozenSourceDigest:
    def __init__(self, document: dict[str, object]) -> None:
        self._document = document

    def to_document(self) -> dict[str, object]:
        return self._document


def _bind_observed_identities(
    monkeypatch: pytest.MonkeyPatch,
    *,
    source: dict[str, object],
    bundle: dict[str, object],
) -> None:
    """Pin what the repository currently observes for both frozen identities."""

    monkeypatch.setattr(
        campaign_submission_identity,
        "current_source_definition_snapshot",
        lambda **_kwargs: _FrozenSourceDigest(source),
    )
    monkeypatch.setattr(
        campaign_submission_identity,
        "current_execution_bundle_identity",
        lambda **_kwargs: _FrozenSourceDigest(bundle),
    )



def test_campaign_submission_accepts_stable_dirty_source_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = SourceDefinitionSnapshot(SOURCE_DIGEST).to_document()
    bundle = ExecutionBundleIdentity(BUNDLE_DIGEST).to_document()
    _bind_observed_identities(monkeypatch, source=source, bundle=bundle)

    campaign_submission._require_stable_source_inputs(
        source,
        execution_bundle=bundle,
        repo_root=tmp_path,
    )


def test_campaign_submission_rejects_source_digest_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    frozen = SourceDefinitionSnapshot(SOURCE_DIGEST).to_document()
    bundle = ExecutionBundleIdentity(BUNDLE_DIGEST).to_document()
    observed = {**frozen, "digest": "sha256:" + ("f" * 64)}
    _bind_observed_identities(monkeypatch, source=observed, bundle=bundle)

    with pytest.raises(ValueError, match="changed during freeze"):
        campaign_submission._require_stable_source_inputs(
            frozen,
            execution_bundle=bundle,
            repo_root=tmp_path,
        )


def test_campaign_submission_rejects_execution_bundle_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An executor change must invalidate the freeze on its own."""

    frozen = SourceDefinitionSnapshot(SOURCE_DIGEST).to_document()
    bundle = ExecutionBundleIdentity(BUNDLE_DIGEST).to_document()
    observed_bundle = {**bundle, "digest": "sha256:" + ("c" * 64)}
    _bind_observed_identities(monkeypatch, source=frozen, bundle=observed_bundle)

    with pytest.raises(ValueError, match="changed during freeze"):
        campaign_submission._require_stable_source_inputs(
            frozen,
            execution_bundle=bundle,
            repo_root=tmp_path,
        )



def test_external_inputs_reject_path_escape_and_content_replacement(
    tmp_path: Path,
) -> None:
    acquisition_root, refs = _acquisition(tmp_path)
    with pytest.raises(CampaignExternalInputError, match="PATH_ESCAPE"):
        bind_external_input_refs(
            "image",
            [
                {
                    "kind": "professional_image_acquisition",
                    "manifestRef": "../manifest.json",
                    "receiptRef": refs[0]["receiptRef"],
                }
            ],
            acquisition_root=acquisition_root,
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            entity_catalog_digest=CATALOG_DIGEST,
        )

    blob = acquisition_root / str(refs[0]["blobRefs"][0]["blobRef"])
    blob.write_bytes(blob.read_bytes() + b"tamper")
    with pytest.raises(
        CampaignExternalInputError, match="DIGEST_DRIFT|digest mismatch"
    ):
        verify_external_input_refs(
            "image",
            refs,
            acquisition_root=acquisition_root,
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            entity_catalog_digest=CATALOG_DIGEST,
        )




def test_professional_image_input_is_limited_to_homepage_and_image(
    tmp_path: Path,
) -> None:
    acquisition_root, image_refs = _acquisition(tmp_path)
    declaration = {
        "kind": image_refs[0]["kind"],
        "manifestRef": image_refs[0]["manifestRef"],
        "receiptRef": image_refs[0]["receiptRef"],
    }
    homepage_refs = bind_external_input_refs(
        "homepage",
        [declaration],
        acquisition_root=acquisition_root,
        source_revision=SOURCE_REVISION,
        source_digest=SOURCE_DIGEST,
        entity_catalog_digest=CATALOG_DIGEST,
    )
    assert homepage_refs[0]["carrier"] == "homepage"
    with pytest.raises(CampaignExternalInputError, match="not admitted for article"):
        bind_external_input_refs(
            "article",
            [declaration],
            acquisition_root=acquisition_root,
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            entity_catalog_digest=CATALOG_DIGEST,
        )




def test_request_envelope_freezes_content_addressed_external_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _governed_acquisition_handoff: None,
) -> None:
    acquisition_root, refs = _acquisition(tmp_path)
    repo = tmp_path / "repo"
    (repo / "quwoquan_data/reference/travel/entities/china").mkdir(parents=True)
    # 采集根必须落在受治理输出根内，冻结出的 acquisitionRootRef 才是可移植的；
    # 夹具已按 <output>/data/local/... 布局建目录，这里把该输出根显式绑上去。
    monkeypatch.setattr(core_paths, "OUTPUT_ROOT", tmp_path / "output")

    for module in (campaign_request_envelope, campaign_request_envelope_build):
        monkeypatch.setattr(
            module,
            "current_source_definition_snapshot",
            lambda **_kwargs: SourceDefinitionSnapshot(SOURCE_DIGEST),
        )
        monkeypatch.setattr(
            module,
            "current_execution_bundle_identity",
            lambda **_kwargs: ExecutionBundleIdentity(BUNDLE_DIGEST),
        )
    monkeypatch.setattr(
        campaign_request_envelope_build,
        "entity_catalog_digest",
        lambda _ref: CATALOG_DIGEST,
    )
    monkeypatch.setattr(
        campaign_request_envelope,
        "_require_stable_source_inputs",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        campaign_request_envelope,
        "_git_branch",
        lambda _repo: "dev1.0",
    )
    monkeypatch.setattr(
        campaign_request_envelope,
        "_git_commit",
        lambda _repo: "c" * 40,
    )
    # quota=1 落在 bounded policy 内：不携带 governed receipt，
    # demand 事实由 confirmed handoff 拥有（vertical/regionRef/scope）。
    monkeypatch.setattr(
        campaign_request_envelope_build,
        "load_pre_acquisition_handoff",
        lambda _path: {
            "vertical": "travel",
            "regionRef": "china",
            "scope": "china",
            "primaryTopicRef": None,
            "sourceSelection": {
                "image": {"mode": "site_primary", "providers": ["pinterest"]},
            },
        },
    )
    policy_ref = "quwoquan_data/control_plane/_shared/catalogs/bounded_execution_authority_policy.json"
    policy_copy = repo / policy_ref
    policy_copy.parent.mkdir(parents=True, exist_ok=True)
    policy_copy.write_bytes((REPO_ROOT / policy_ref).read_bytes())
    preflight_path, _preflight_binding = ready_semantic_preflight(
        "default", output_root=tmp_path / "output"
    )
    envelope = campaign_request_envelope.build_envelope(
        quota=1,
        carrier="image",
        repo_root=repo,
        day="20260805",
        semantic_preflight_receipt=preflight_path,
        semantic_preflight_output_root=tmp_path / "output",
        pre_acquisition_handoff=tmp_path / "handoff.json",
        external_input_refs=[
            {
                "kind": refs[0]["kind"],
                "manifestRef": refs[0]["manifestRef"],
                "receiptRef": refs[0]["receiptRef"],
            }
        ],
        acquisition_root=acquisition_root,
    )
    assert envelope["sourceRevision"] == SOURCE_REVISION
    assert envelope["externalInputRefs"] == refs
    assert envelope["externalInputsDigest"] == external_inputs_digest(refs)
    # 每条 ref 只带 kind 子根（`.`/`video`），基准根不冻结就意味着消费方各自取默认值。
    assert envelope["acquisitionRootRef"] == "data/local/workspace/source-acquisition"
    assert envelope_acquisition_root(envelope) == acquisition_root.resolve()
    # 显式覆盖与冻结基准不一致时判否，CLI 参数不得把冻结字节改指到另一棵树。
    with pytest.raises(CampaignExternalInputError, match="acquisitionRootRef differs"):
        envelope_acquisition_root(envelope, override=tmp_path / "elsewhere")
    path = tmp_path / "image-envelope.json"
    write_json(path, envelope)
    assert campaign_request_envelope.load_campaign_envelope(path) == envelope

    # 提交面是 plan/capsule 的唯一上游：基准根必须原样落进 submission 文档。
    for name, value in (
        ("current_source_definition_snapshot", lambda **_k: SourceDefinitionSnapshot(SOURCE_DIGEST)),
        ("current_execution_bundle_identity", lambda **_k: ExecutionBundleIdentity(BUNDLE_DIGEST)),
        ("_require_stable_source_inputs", lambda *_a, **_k: None),
        ("_git_branch", lambda _repo: "dev1.0"),
        ("_git_commit", lambda _repo: "c" * 40),
    ):
        monkeypatch.setattr(campaign_submission, name, value)
    monkeypatch.setattr(
        campaign_submission, "entity_catalog_digest", lambda _ref: CATALOG_DIGEST
    )
    submission_path = campaign_submission.write_submission(
        root_execution_id=str(envelope["rootExecutionId"]),
        execution_id=str(envelope["executionId"]),
        request=RuntimeExecutionRequest(
            family_ref=str(envelope["familyRef"]),
            region_ref=str(envelope["regionRef"]),
            selector=TargetSelector(str(envelope["selector"])),
            count=int(envelope["count"]),
            quota=int(envelope["quota"]),
            execution_authority=dict(envelope["executionAuthority"]),
            topic=envelope["topic"],
            source_providers=tuple(envelope["sourceProviders"]),
            target_names=tuple(envelope["targetNames"]),
        ),
        retry_of=None,
        repo_root=repo,
        root=tmp_path / "campaigns",
        campaign_envelope=envelope,
        acquisition_root=acquisition_root,
        semantic_preflight_output_root=tmp_path / "output",
    )
    submission = json.loads(submission_path.read_text(encoding="utf-8"))
    assert submission["acquisitionRootRef"] == envelope["acquisitionRootRef"]


def test_submission_carries_the_acquisition_base_its_envelope_froze() -> None:
    """提交面必须把 envelope 冻结的基准根原样带下去。

    submission 是 plan/capsule 唯一的上游；这里丢掉基准根，下游就只剩默认采集根
    可取，而 ref 只带 kind 子根、自身无法暴露这次替换。
    """
    frozen = "data/local/workspace/source-acquisition/preparations/image-001"
    assert frozen_acquisition_root_ref({"acquisitionRootRef": frozen}) == frozen
    # 无外部输入的 envelope 不声明基准根：缺席是「无须解析」，不是空串默认值。
    assert frozen_acquisition_root_ref({}) == ""
    assert frozen_acquisition_root_ref(None) == ""
    assert frozen_acquisition_root_ref({"acquisitionRootRef": "  "}) == ""
