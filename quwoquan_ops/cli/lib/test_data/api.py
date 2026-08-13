"""Public strong types for declarative acceptance-data requests.

Tests import this module and ``capabilities/*`` only. Stable string keys remain
an internal serialization/receipt detail and are never accepted by Session.

spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t1
spec_ref: specs/feature-tree/runtime/runtime-testinfra/test-data-provisioning-and-isolation/spec.md#gwt-001
"""

from __future__ import annotations

import types
import uuid
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    ClassVar,
    Generic,
    Iterator,
    Mapping,
    Protocol,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)


ParamsT = TypeVar("ParamsT")
ResultT = TypeVar("ResultT")
ValueT = TypeVar("ValueT")


@dataclass(frozen=True)
class BusinessObjectRef:
    """Canonical object identity without duplicating per-object ID wrappers."""

    object_type: str
    object_id: str

    def __post_init__(self) -> None:
        if not self.object_type.strip() or not self.object_id.strip():
            raise ValueError("business object reference requires type and id")


@dataclass(frozen=True)
class CapabilityKey:
    """Stable internal wire identity; test code must not construct/read it."""

    value: str

    def __post_init__(self) -> None:
        parts = self.value.split(".")
        if len(parts) < 3 or any(not part.strip() for part in parts):
            raise ValueError("capability key must be a dotted stable identity")


@dataclass(frozen=True, order=True)
class ProviderCapabilityKey:
    """Typed reference to a governed external Provider capability."""

    value: str

    def __post_init__(self) -> None:
        parts = self.value.split(".")
        if len(parts) < 3 or any(not part.strip() for part in parts):
            raise ValueError(
                "Provider capability key must be a dotted stable identity"
            )


@dataclass(frozen=True)
class RequestId:
    value: str

    @classmethod
    def new(cls) -> "RequestId":
        return cls(str(uuid.uuid4()))


@dataclass(frozen=True)
class ReceiptRef:
    path: Path
    digest: str


@dataclass(frozen=True)
class OutputRef(Generic[ValueT]):
    """Typed dependency edge to a whole result or one result field."""

    request_id: RequestId
    value_type: type[Any]
    field_path: tuple[str, ...] = ()
    request: "CapabilityRequest[Any, Any] | None" = field(
        default=None,
        repr=False,
        compare=False,
    )


class _RequestOutput(Generic[ResultT]):
    def __init__(self, request: "CapabilityRequest[Any, ResultT]") -> None:
        self._request = request

    def whole(self) -> OutputRef[ResultT]:
        return OutputRef(
            request_id=self._request.request_id,
            value_type=self._request.capability.result_type,
            request=self._request,
        )

    def __getattr__(self, name: str) -> OutputRef[Any]:
        result_type = self._request.capability.result_type
        if not is_dataclass(result_type):
            raise AttributeError(
                f"{result_type.__name__} has no typed output field {name}"
            )
        hints = get_type_hints(result_type)
        if name not in hints:
            raise AttributeError(
                f"{result_type.__name__} has no typed output field {name}"
            )
        field_type = hints[name]
        if not isinstance(field_type, type):
            raise TypeError(
                f"output field {result_type.__name__}.{name} must have a concrete type"
            )
        return OutputRef(
            request_id=self._request.request_id,
            value_type=field_type,
            field_path=(name,),
            request=self._request,
        )


@dataclass(frozen=True)
class CapabilityRef(Generic[ParamsT, ResultT]):
    key: CapabilityKey
    params_type: type[ParamsT]
    result_type: type[ResultT]
    owner_service: str
    required_provider_capabilities: tuple[ProviderCapabilityKey, ...] = ()
    mutates_environment: bool = True
    candidate_cacheable: bool = False

    def __post_init__(self) -> None:
        if not self.owner_service.strip() or "-" in self.owner_service:
            raise ValueError("owner_service must be a Python module identity")
        if not is_dataclass(self.params_type):
            raise TypeError("capability params_type must be a dataclass")
        if any(
            not isinstance(item, ProviderCapabilityKey)
            for item in self.required_provider_capabilities
        ):
            raise TypeError(
                "required_provider_capabilities must use ProviderCapabilityKey"
            )
        if len(set(self.required_provider_capabilities)) != len(
            self.required_provider_capabilities
        ):
            raise ValueError("required Provider capabilities must be unique")
        if self.candidate_cacheable and self.mutates_environment:
            raise ValueError("only immutable capabilities may use candidate cache")

    def bind(self, params: ParamsT) -> "CapabilityRequest[ParamsT, ResultT]":
        _validate_value(params, self.params_type, "params")
        return CapabilityRequest(
            capability=self,
            params=params,
            request_id=RequestId.new(),
        )


@dataclass(frozen=True)
class CapabilityRequest(Generic[ParamsT, ResultT]):
    capability: CapabilityRef[ParamsT, ResultT]
    params: ParamsT
    request_id: RequestId

    def __post_init__(self) -> None:
        _validate_value(self.params, self.capability.params_type, "params")

    @property
    def output(self) -> _RequestOutput[ResultT]:
        return _RequestOutput(self)


@dataclass(frozen=True)
class Provisioned(Generic[ResultT]):
    value: ResultT
    receipt: ReceiptRef


class AssertionStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class CaseAssertion:
    assertion_id: str
    status: AssertionStatus

    def __post_init__(self) -> None:
        if not self.assertion_id.strip() or any(
            character.isspace() for character in self.assertion_id
        ):
            raise ValueError("case assertion_id must be a stable non-empty identity")


@dataclass(frozen=True)
class CaseExecution:
    assertions: tuple[CaseAssertion, ...]

    def __post_init__(self) -> None:
        assertion_ids = tuple(item.assertion_id for item in self.assertions)
        if not assertion_ids:
            raise ValueError("business case must emit at least one assertion")
        if len(assertion_ids) != len(set(assertion_ids)):
            raise ValueError("business case assertion identities must be unique")

    @property
    def status(self) -> AssertionStatus:
        if all(item.status is AssertionStatus.PASSED for item in self.assertions):
            return AssertionStatus.PASSED
        return AssertionStatus.FAILED


@dataclass(frozen=True)
class CaseExecutionContext:
    environment: str
    target: str
    base_url: str
    candidate_binding_digest: str
    test_data_instance_id: str
    request_id: RequestId
    provision_receipt: ReceiptRef
    runtime: object = field(repr=False, compare=False)

    def actor(self, role: object) -> object:
        """Resolve one typed ActorHandle for this isolated CaseResult attempt."""

        from .capabilities.common import ActorRole
        from .operations import TestDataRuntime

        if not isinstance(role, ActorRole):
            raise TypeError("business case actor role must use ActorRole")
        if not isinstance(self.runtime, TestDataRuntime):
            raise TypeError("business case runtime is unavailable")
        return self.runtime.actor_for(
            test_data_instance_id=self.test_data_instance_id,
            role=role,
        )

    def public_operations(self, capability_key: str) -> object:
        """Create a receipt-bound executor for a source-owned business query."""

        from .operations import PublicOperationExecutor, TestDataRuntime

        if not capability_key.strip():
            raise ValueError("business case capability key is required")
        if not isinstance(self.runtime, TestDataRuntime):
            raise TypeError("business case runtime is unavailable")
        return PublicOperationExecutor(
            base_url=self.base_url,
            target=self.target,
            test_data_instance_id=self.test_data_instance_id,
            capability_key=capability_key,
            runtime=self.runtime,
        )


class BusinessCaseRunner(Generic[ResultT]):
    """Source-owned business assertions executed while provisioned data is live."""

    result_type: ClassVar[type[Any]]

    @classmethod
    def execute(
        cls,
        value: ResultT,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        raise NotImplementedError


@dataclass(frozen=True)
class CaseRef(Generic[ResultT]):
    case_id: Enum
    request: CapabilityRequest[Any, ResultT]
    runner_type: type[BusinessCaseRunner[ResultT]]

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, Enum):
            raise TypeError("case_id must be a strongly typed Enum member")
        if not isinstance(self.runner_type, type) or not issubclass(
            self.runner_type,
            BusinessCaseRunner,
        ):
            raise TypeError("runner_type must derive from BusinessCaseRunner")
        if self.runner_type.result_type is not self.request.capability.result_type:
            raise TypeError(
                "business case result_type must exactly match capability result_type"
            )


@dataclass(frozen=True)
class ExecutedCase:
    case_id: str
    execution: CaseExecution
    candidate_binding_digest: str
    test_data_instance_id: str
    request_id: RequestId
    provision_receipt: ReceiptRef
    test_body_receipt: ReceiptRef
    readback_receipts: tuple[ReceiptRef, ...] = ()
    cleanup_receipts: tuple[ReceiptRef, ...] = ()

    @property
    def status(self) -> AssertionStatus:
        return self.execution.status

    def document(self, *, receipt_path_base: Path) -> dict[str, object]:
        def relative_receipt_path(receipt: ReceiptRef) -> str:
            base = receipt_path_base.expanduser().resolve()
            try:
                relative = receipt.path.expanduser().resolve().relative_to(base)
            except ValueError as exc:
                raise ValueError(
                    "receipt path must be inside the CaseResult report directory"
                ) from exc
            return relative.as_posix()

        assertions = [
            {
                "assertionId": assertion.assertion_id,
                "status": assertion.status.value,
            }
            for assertion in self.execution.assertions
        ]
        return {
            "caseId": self.case_id,
            "status": self.status.value,
            "candidateBindingDigest": self.candidate_binding_digest,
            "testDataInstanceId": self.test_data_instance_id,
            "requestId": self.request_id.value,
            "assertionIds": [item["assertionId"] for item in assertions],
            "assertions": assertions,
            "testExecution": {
                "executed": 1,
                "failed": 0 if self.status is AssertionStatus.PASSED else 1,
                "skipped": 0,
            },
            "provisionReceiptDigest": self.provision_receipt.digest,
            "provisionReceiptPath": relative_receipt_path(self.provision_receipt),
            "testBodyReceiptDigest": self.test_body_receipt.digest,
            "testBodyReceiptPath": relative_receipt_path(self.test_body_receipt),
            "readbackReceiptDigests": [
                receipt.digest for receipt in self.readback_receipts
            ],
            "readbackReceiptPaths": [
                relative_receipt_path(receipt) for receipt in self.readback_receipts
            ],
            "cleanupReceiptDigests": [
                receipt.digest for receipt in self.cleanup_receipts
            ],
            "cleanupReceiptPaths": [
                relative_receipt_path(receipt) for receipt in self.cleanup_receipts
            ],
        }


class _ProvisionScope(Generic[ResultT], Protocol):
    def __enter__(self) -> Provisioned[ResultT]: ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool: ...


class TestDataSession:
    """Test-facing façade; implementation is loaded only when a session starts."""

    __test__ = False

    @classmethod
    def for_case(
        cls,
        case_id: Enum,
        *,
        context: object | None = None,
    ) -> "TestDataSession":
        if not isinstance(case_id, Enum):
            raise TypeError("case_id must be a strongly typed Enum member")
        from .control_plane import build_session

        return build_session(case_id=case_id, context=context)

    def provision(
        self,
        request: CapabilityRequest[ParamsT, ResultT],
    ) -> _ProvisionScope[ResultT]:
        raise NotImplementedError

    def execute(self, case: CaseRef[ResultT]) -> ExecutedCase:
        raise NotImplementedError


def validate_result(value: object, result_type: type[ResultT]) -> ResultT:
    _validate_value(value, result_type, "provider result")
    return value  # type: ignore[return-value]


def iter_output_refs(value: object) -> Iterator[OutputRef[Any]]:
    if isinstance(value, OutputRef):
        yield value
        return
    if is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            yield from iter_output_refs(getattr(value, field.name))
        return
    if isinstance(value, (tuple, list)):
        for item in value:
            yield from iter_output_refs(item)
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from iter_output_refs(item)


def _validate_value(value: object, expected: object, path: str) -> None:
    origin = get_origin(expected)
    args = get_args(expected)
    if expected is Any:
        return
    if origin in (Union, types.UnionType):
        errors: list[str] = []
        for option in args:
            try:
                _validate_value(value, option, path)
                return
            except TypeError as exc:
                errors.append(str(exc))
        raise TypeError(f"{path} does not match any declared type")
    if origin is OutputRef:
        if not isinstance(value, OutputRef):
            raise TypeError(f"{path} must be OutputRef")
        expected_value_type = args[0]
        if isinstance(expected_value_type, type) and value.value_type is not expected_value_type:
            raise TypeError(
                f"{path} expects OutputRef[{expected_value_type.__name__}], "
                f"got OutputRef[{value.value_type.__name__}]"
            )
        return
    if origin in (tuple, list):
        if not isinstance(value, origin):
            raise TypeError(f"{path} must be {origin.__name__}")
        item_types = args
        if origin is tuple and len(args) == 2 and args[1] is Ellipsis:
            item_types = tuple(args[0] for _ in value)
        if len(item_types) != len(value):
            raise TypeError(f"{path} tuple arity mismatch")
        for index, (item, item_type) in enumerate(zip(value, item_types)):
            _validate_value(item, item_type, f"{path}[{index}]")
        return
    if isinstance(expected, type) and is_dataclass(expected):
        if type(value) is not expected:
            raise TypeError(f"{path} must be exactly {expected.__name__}")
        hints = get_type_hints(expected)
        for field in fields(expected):
            _validate_value(
                getattr(value, field.name),
                hints[field.name],
                f"{path}.{field.name}",
            )
        return
    if isinstance(expected, type):
        if type(value) is not expected:
            raise TypeError(f"{path} must be exactly {expected.__name__}")
        return
    raise TypeError(f"{path} has unsupported declared type {expected!r}")
