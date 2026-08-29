"""Immutable local deployment candidate identity and release binding.

原 ``deployment_candidate_manifest.py`` 的同名包形态；对外 import 路径与符号
完全不变（含被测私有 ``_`` 符号）。按职责切分：

- ``constants``：schema、正则、SPEC_REFS、ROOT/CONTRACT_GRAPH_PATH 等共享常量。
- ``candidate_fs``：candidate 根内 symlink-safe 打开/读取/校验原语。
- ``candidate_staging``：candidate 文件原子写入与 staging 目录发布。
- ``release_binding``：release attestation 绑定与 ContractGraph 摘要。
- ``environment_artifact``：统一 environment artifact identity 的复算与校验。
- ``log_sink_package``：observability log-sink（Elasticsearch）package。
- ``provider_binding_overlay``：单环境 Provider Go source overlay 物化与校验。
- ``provider_runtime_package``：Provider runtime package 物化/封版/校验。
- ``manifest``：candidate manifest 写入、加载与全量校验。

测试通过 ``mock.patch.object(本包, "<符号>")`` 拦截内部依赖，因此子模块对这些
符号一律经包属性（``_pkg.``）消费；本模块 re-export 的名字就是 patch 的锚点。
"""

from __future__ import annotations

import yaml  # noqa: F401  # 测试经 subject.yaml 访问

from quwoquan_ops.cli.lib.immutable_image_composition import (  # noqa: F401
    first_party_service_names,
    immutable_image_digest,
)
from quwoquan_ops.cli.lib.output_paths import (  # noqa: F401
    app_deployment_package_dir,
    deployment_candidate_dir,
    legal_static_deployment_package_dir,
    runtime_shared_deployment_package_dir,
)
from quwoquan_ops.cli.lib.provider_runtime_composition import (  # noqa: F401
    compile_provider_runtime_composition,
    validate_provider_runtime_composition,
)
from quwoquan_ops.cli.lib.service_core_composition import (  # noqa: F401
    project_compose_document,
)
from quwoquan_ops.cli.lib.graphql_read_registry_package import (  # noqa: F401
    validate_packaged_graphql_read_registry,
)

from .constants import (  # noqa: F401
    _DIGEST,
    _RELEASE_BINDING_FIELDS,
    _RELEASE_LIFECYCLE_CLASSES,
    CANDIDATE_MANIFEST_SCHEMA,
    CANDIDATE_VALIDATION_PURPOSES,
    CONTRACT_GRAPH_PATH,
    ENVIRONMENT_ARTIFACT_METADATA_PATH,
    ENVIRONMENT_ARTIFACT_SCHEMA_PATH,
    LOG_SINK_ADAPTER_ID,
    OBSERVABILITY_LOG_SINK_PACKAGE_SCHEMA,
    PROVIDER_RUNTIME_PACKAGE_SCHEMA,
    RELEASE_INPUT_CLASSIFICATIONS,
    ROOT,
    RUNTIME_CANDIDATE_TYPE,
    SPEC_REFS,
)
from .candidate_fs import (  # noqa: F401
    _UnsafeCandidatePath,
    _candidate_directory_flags,
    _candidate_file_flags,
    _candidate_relative_path,
    _open_candidate_file,
    _open_candidate_parent,
    _open_candidate_root,
    _read_candidate_bytes,
    _read_candidate_object,
    _read_object,
    _revalidate_candidate_file,
    _revalidate_candidate_parent,
    _sha256_candidate_file,
    _sha256_file,
    _sha256_json,
    _validate_candidate_artifact_ref,
)
from .candidate_staging import (  # noqa: F401
    _atomic_write_candidate_file,
    _begin_candidate_directory_materialization,
    _discard_candidate_staging_directory,
    _publish_candidate_staging_directory,
    _validate_candidate_payload_tree,
    _validate_open_candidate_tree,
)
from .release_binding import (  # noqa: F401
    _release_binding,
    canonical_contract_graph_digest,
    release_input_classification,
    validate_release_attestations,
)
from .environment_artifact import (  # noqa: F401
    build_environment_artifact,
    environment_artifact_digest,
    environment_artifact_identity_core_digest,
    validate_environment_artifact,
)
from .log_sink_package import (  # noqa: F401
    _ELASTICSEARCH_IMAGE_DEFAULT_RE,
    _ELASTICSEARCH_IMAGE_LITERAL_RE,
    _ELASTICSEARCH_IMAGE_LOCAL_TAG_DEFAULT_RE,
    _ELASTICSEARCH_IMAGE_LOCAL_TAG_RE,
    _canonical_observability_log_sink_binding,
    _local_elasticsearch_runtime_selection,
    load_observability_log_sink_package,
    local_elasticsearch_image_digest,
    materialize_observability_log_sink_package,
    validate_observability_log_sink_package,
)
from .provider_binding_overlay import (  # noqa: F401
    PROVIDER_BINDING_OVERLAY_SCHEMA,
    load_provider_binding_overlay,
    materialize_mutable_provider_binding_overlay,
    materialize_provider_binding_overlay,
    provider_binding_overlay_build_inputs,
    validate_provider_binding_overlay,
)
from .provider_runtime_package import (  # noqa: F401
    _validate_candidate_provider_oci_binding,
    load_provider_runtime_package,
    materialize_provider_runtime_package,
    provider_runtime_image_environment_key,
    seal_provider_runtime_package_images,
    validate_packaged_provider_runtime,
)
from .manifest import (  # noqa: F401
    _validate_candidate_app_runtime_binding,
    load_candidate_manifest,
    validate_candidate_manifest,
    write_candidate_manifest,
)
