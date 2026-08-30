package http

import (
	"net/http"
	"strconv"

	rterr "quwoquan_service/runtime/errors"
	rtgov "quwoquan_service/runtime/governance"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
)

// WriteFeedAdmissionRejection owns the public wire response emitted when the
// content-feed operation admission limiter is exhausted.
func WriteFeedAdmissionRejection(
	w http.ResponseWriter,
	r *http.Request,
	reason rtgov.OperationAdmissionRejection,
) {
	const retryAfterSeconds = 1
	w.Header().Set("Retry-After", strconv.Itoa(retryAfterSeconds))
	rterr.WriteHTTPError(
		w,
		contentgenerated.AppErrorFromFeedCapacityUnavailable(
			"content feed owner concurrency exhausted: "+string(reason),
		).WithRecoveryDirective("retry", "snackbar", retryAfterSeconds),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}
