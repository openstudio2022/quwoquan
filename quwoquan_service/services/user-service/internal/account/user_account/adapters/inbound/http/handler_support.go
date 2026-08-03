package http

import (
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
)

func anyString(value any) string {
	if value == nil {
		return ""
	}
	if text, ok := value.(string); ok {
		return text
	}
	return ""
}

func hasUserErrorCode(err error, want string) bool {
	if err == nil {
		return false
	}
	return rterr.NormalizeError(err).Code.String() == want
}

func userErrorDebugMessage(err error) string {
	if err == nil {
		return ""
	}
	return rterr.NormalizeError(err).DebugMessage
}

func (h *UserHandler) commandIdempotencyKey(r *http.Request) string {
	if invocation, ok := operation.FromContext(r.Context()); ok {
		if key := strings.TrimSpace(invocation.IdempotencyKey); key != "" {
			return key
		}
	}
	return strings.TrimSpace(r.Header.Get("Idempotency-Key"))
}
