package http

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/user-service/internal/generated"
)

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeHTTPError(w http.ResponseWriter, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptions{IncludeDebug: true})
}

func writeNotFound(w http.ResponseWriter, msg string) {
	writeHTTPError(w, generated.AppErrorFromUserNotFound(msg))
}

func writeInvalidArg(w http.ResponseWriter, msg string) {
	writeHTTPError(w, generated.AppErrorFromInvalidArgument(msg))
}

func writeForbidden(w http.ResponseWriter, msg string) {
	writeHTTPError(w, generated.AppErrorFromForbidden(msg))
}

func parseLimit(r *http.Request, defaultVal int) int {
	if s := r.URL.Query().Get("limit"); s != "" {
		if n, err := strconv.Atoi(s); err == nil && n > 0 && n <= 100 {
			return n
		}
	}
	return defaultVal
}

func parseCursor(r *http.Request) string {
	return r.URL.Query().Get("cursor")
}

func pathParam(r *http.Request, name string) string {
	path := r.URL.Path
	parts := strings.Split(path, "/")
	for i, p := range parts {
		if p == "{"+name+"}" || (i > 0 && isParamSlot(parts, i, name)) {
			return ""
		}
	}
	return r.PathValue(name)
}

func isParamSlot(_ []string, _ int, _ string) bool { return false }

func userIDFromHeader(r *http.Request) string {
	return r.Header.Get("X-Client-User-Id")
}

func readBody(r *http.Request) (map[string]any, error) {
	var data map[string]any
	if err := json.NewDecoder(r.Body).Decode(&data); err != nil {
		return nil, err
	}
	return data, nil
}
