"""Content execution work-package contract.

Every content run is addressed by one readable ``executionId`` and owns one
runtime work package.  Reusable recipes, prompts, templates, schemas, and
coverage inventories stay in the repository; execution evidence never does.
"""

from .identity import (
    ContentType,
    RolloutMilestone,
    SelectionPolicy,
    build_execution_id,
    parse_execution_id,
    validate_execution_id,
)
from .workspace import (
    create_execution_manifest,
    execution_manifest_path,
    execution_root,
    load_execution_manifest,
)
from .qualification import (
    finalize_execution_qualification,
    prepare_execution_qualification,
)

__all__ = [
    "build_execution_id",
    "ContentType",
    "create_execution_manifest",
    "execution_manifest_path",
    "execution_root",
    "load_execution_manifest",
    "finalize_execution_qualification",
    "prepare_execution_qualification",
    "parse_execution_id",
    "RolloutMilestone",
    "SelectionPolicy",
    "validate_execution_id",
]
