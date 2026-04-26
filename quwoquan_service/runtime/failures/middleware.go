package failures

import (
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

func WriteHTTPError(
	w http.ResponseWriter,
	statusCode int,
	failure FailureBase,
	opts ResponseOptions,
) {
	if opts.RequestID == "" {
		opts.RequestID = fmt.Sprintf("runtime.err.req.%d", time.Now().UnixNano())
	}
	if opts.TraceID == "" {
		opts.TraceID = opts.RequestID
	}
	w.Header().Set("Content-Type", "application/json")
	if opts.RequestID != "" {
		w.Header().Set("X-Request-Id", opts.RequestID)
	}
	if opts.TraceID != "" {
		w.Header().Set("X-Trace-Id", opts.TraceID)
	}
	w.WriteHeader(statusCode)
	_ = json.NewEncoder(w).Encode(ToResponse(failure, opts))
}
