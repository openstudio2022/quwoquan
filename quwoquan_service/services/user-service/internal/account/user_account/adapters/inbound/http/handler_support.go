package http

import rterr "quwoquan_service/runtime/errors"

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
