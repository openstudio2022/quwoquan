from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuntimeContextAttribute:
    key: str
    value: str


@dataclass(frozen=True)
class RuntimeFailureContext:
    attributes: list[RuntimeContextAttribute] = field(default_factory=list)


@dataclass(frozen=True)
class RuntimeFailureLocation:
    business_object: str
    function_module: str
    source_file_path: str | None = None
    source_line_number: int | None = None
    source_line_text: str | None = None


@dataclass(frozen=True)
class RuntimeFailure:
    code: str
    origin: str
    kind: str
    nature: str
    location: RuntimeFailureLocation
    context: RuntimeFailureContext = field(default_factory=RuntimeFailureContext)
