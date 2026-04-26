package failures

import (
	"strings"

	runtimeerrors "quwoquan_service/runtime/errors"
)

type Mapper[TInput any] interface {
	Map(input TInput) FailureBase
}

func FromLegacyAppError(err *runtimeerrors.AppError) Failure {
	if err == nil {
		return Unknown()
	}
	code := err.Code.String()
	return Failure{
		Code:   code,
		Origin: originFromLegacyKind(err.Code.Kind),
		Kind:   kindFromCode(code),
		Nature: natureFromLegacyKind(err.Code.Kind),
		Location: Location{
			BusinessObject: "cloud_request",
			FunctionModule: "runtime_errors_adapter",
		},
		Context: Context{
			Attributes: []ContextAttribute{
				{Key: "module", Value: string(err.Code.Module)},
				{Key: "reason", Value: err.Code.Reason},
			},
		},
	}.Normalized()
}

func originFromLegacyKind(kind runtimeerrors.Kind) Origin {
	switch kind {
	case runtimeerrors.KindUser:
		return OriginUser
	case runtimeerrors.KindNetwork:
		return OriginEnvironment
	case runtimeerrors.KindMiddleware:
		return OriginRemoteDependency
	case runtimeerrors.KindSystem:
		return OriginSystem
	default:
		return OriginSystem
	}
}

func natureFromLegacyKind(kind runtimeerrors.Kind) Nature {
	switch kind {
	case runtimeerrors.KindUser:
		return NatureRequiresUserAction
	case runtimeerrors.KindNetwork, runtimeerrors.KindMiddleware:
		return NatureTransient
	default:
		return NatureBug
	}
}

func kindFromCode(code string) Kind {
	lower := strings.ToLower(code)
	switch {
	case strings.Contains(lower, "timeout"):
		return KindTimeout
	case strings.Contains(lower, "permission"):
		return KindPermission
	case strings.Contains(lower, "unauthorized"):
		return KindAuth
	case strings.Contains(lower, "not_found"):
		return KindNotFound
	case strings.Contains(lower, "parse"):
		return KindParsing
	case strings.Contains(lower, "contract"):
		return KindContract
	case strings.Contains(lower, "unavailable"):
		return KindUnavailable
	default:
		return KindInternal
	}
}
