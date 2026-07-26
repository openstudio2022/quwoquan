package httpadapter

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	rterrors "quwoquan_service/runtime/errors"
)

const (
	moduleSearch                    = rterrors.Module("SEARCH")
	recentSearchMaxRequestBodyBytes = 64 << 10
)

func requestIDFrom(r *http.Request) string {
	if id := strings.TrimSpace(r.Header.Get("X-Request-Id")); id != "" {
		return id
	}
	return fmt.Sprintf("search.recent.req.%d", time.Now().UnixNano())
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeErr(w http.ResponseWriter, requestID string, err error) {
	rterrors.WriteHTTPError(w, err, rterrors.HTTPWriteOptions{RequestID: requestID})
}
