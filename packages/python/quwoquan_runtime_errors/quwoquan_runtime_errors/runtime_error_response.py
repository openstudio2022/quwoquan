from dataclasses import dataclass

from quwoquan_runtime_errors.runtime_failure import RuntimeFailure


@dataclass(frozen=True)
class RuntimeErrorResponse(RuntimeFailure):
    request_id: str = ""
    trace_id: str = ""
    user_message: str = ""
    debug_message: str = ""
