package http

import (
	"net/http"
	"strconv"

	rterrors "quwoquan_service/runtime/errors"
)

const searchUnavailableRecoveryAfterSeconds = 5

// writeSearchUnavailable is the single HTTP writer for
// SEARCH.MIDDLEWARE.unavailable. The paired local contract binds its wire
// recovery directive to search_index_view/errors.yaml.
func writeSearchUnavailable(w http.ResponseWriter, requestID string, debugMessage string) {
	w.Header().Set(
		"Retry-After",
		strconv.Itoa(searchUnavailableRecoveryAfterSeconds),
	)
	writeErr(
		w,
		requestID,
		rterrors.NewUnavailable(
			moduleSearch,
			"搜索暂时不可用，请稍后再试。",
			debugMessage,
		).WithRecoveryDirective(
			"retry",
			"snackbar",
			searchUnavailableRecoveryAfterSeconds,
		),
	)
}
