"""Local environment auth material, protected identities and OTP sessions.

原 ``local_environment_auth.py`` 的同名包形态；对外 import 路径与符号完全
不变（含被测私有 ``_`` 符号）。按职责切分：

- ``constants``：秘密键集合、target 映射、身份集 schema 等共享常量。
- ``models``：``LocalEnvironmentAuth`` 等对外 dataclass。
- ``guards``：环境/target/角色输入校验与 ``_require_mode`` 小工具。
- ``secret_material``：target 级 auth 秘密文件的创建、加载与 runtime 投影。
- ``research_identity``：Research 身份绑定的物化/加载与确定性账号推导。
- ``service_credentials``：本地 FilterCatalog / Product Ops 短时 JWT 铸造。
- ``http_transport``：本地环境 JSON HTTP（bearer/公开）传输层。
- ``identity_sets``：受保护 test-data 电话身份集的物化与读取。
- ``acceptance_sessions``：OTP 真实登录会话编排与账号关闭。
- ``__main__``：``python -m`` 的 ``--shell`` 导出入口。

测试通过 ``mock.patch.object(本包, "<符号>")`` 拦截内部依赖，因此子模块对这些
符号一律经包属性（``_pkg.``）消费；本模块 re-export 的名字就是 patch 的锚点。
``subprocess`` 与 output_paths 等外部名字也保持为包属性，维持原模块的
patch 语义（如 ``local_environment_auth.subprocess.run``）。
"""

from __future__ import annotations

import subprocess  # noqa: F401  # 测试经 local_environment_auth.subprocess patch

from ..output_paths import (  # noqa: F401
    active_deployment_candidate,
    deployment_target_path,
    deployment_target_path_in_work_root,
    env_runs_root,
)
from ..local_target_handoff import target_for_hostname  # noqa: F401
from ..public_domain_tls import root_certificate_path  # noqa: F401

from .constants import (  # noqa: F401
    _CROCKFORD_LOWER,
    _LOCAL_TARGETS,
    _REPO_ROOT,
    _RESEARCH_IDENTITY_BINDING_NAME,
    _RESEARCH_IDENTITY_BINDING_SCHEMA,
    _SECRET_KEYS,
    _TEST_DATA_IDENTITY_SET_LOCK_NAME,
    _TEST_DATA_IDENTITY_SET_NAME,
    _TEST_DATA_IDENTITY_SET_PATH_ENV,
    _TEST_DATA_IDENTITY_SET_SCHEMA,
    _TEST_DATA_PHONE_PROFILES,
)
from .models import (  # noqa: F401
    LocalAcceptanceActor,
    LocalAcceptanceSession,
    LocalEnvironmentAuth,
    LocalEnvironmentHTTPError,
)
from .guards import (  # noqa: F401
    _canonical_actor_role,
    _canonical_test_data_instance_id,
    _require_local_environment,
    _require_mode,
    _require_nonprod_target,
    _required_string,
)
from .secret_material import (  # noqa: F401
    _load_or_create_secrets,
    _local_environment_auth,
    _local_environment_secret_path,
    _print_shell_environment,
    _read_secret_file,
    load_local_environment_auth,
    prepare_local_environment_auth,
)
from .research_identity import (  # noqa: F401
    _deterministic_phone_owner_id,
    _xxh64,
    load_local_research_identity_binding,
    materialize_local_research_identity_binding,
)
from .service_credentials import (  # noqa: F401
    _decode_local_jwt_claims,
    mint_local_filter_catalog_service_token,
    mint_local_product_ops_operator_token,
)
from .http_transport import (  # noqa: F401
    _trusted_json_request,
    request_local_environment_json,
    request_local_environment_public_json,
)
from .identity_sets import (  # noqa: F401
    _atomic_write_test_data_identity_set,
    _read_test_data_identity_set,
    _test_data_actor_phone,
    _test_data_identity_set_path,
    _validate_test_data_identity_set,
    materialize_local_capture_ui_acceptance_phone,
    materialize_test_data_identity_set,
)
from .acceptance_sessions import (  # noqa: F401
    _clear_local_otp_send_throttle,
    close_test_data_acceptance_actor,
    open_local_phone_acceptance_session,
    open_test_data_acceptance_session,
)
