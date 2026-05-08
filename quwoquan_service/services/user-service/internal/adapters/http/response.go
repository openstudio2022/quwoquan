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

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	opts := rterr.HTTPWriteOptionsFromRequest(r)
	opts.IncludeDebug = true
	rterr.WriteHTTPError(w, err, opts)
}

func writeNotFound(w http.ResponseWriter, r *http.Request, msg string) {
	writeHTTPError(w, r, generated.AppErrorFromUserNotFound(msg))
}

func writeInvalidArg(w http.ResponseWriter, r *http.Request, msg string) {
	writeHTTPError(w, r, generated.AppErrorFromInvalidArgument(msg))
}

func writeForbidden(w http.ResponseWriter, r *http.Request, msg string) {
	writeHTTPError(w, r, generated.AppErrorFromForbidden(msg))
}

func writeConflict(w http.ResponseWriter, r *http.Request, userMessage string, debugMessage string) {
	writeHTTPError(w, r, rterr.NewAppError(
		rterr.NewCode(rterr.ModuleUser, rterr.KindUser, "conflict"),
		userMessage,
		debugMessage,
	))
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
	return strings.TrimSpace(r.Header.Get("X-Client-User-Id"))
}

func subAccountIDFromHeader(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-Client-Sub-Account-Id"))
}

func personaContextVersionFromHeader(r *http.Request) string {
	if value := strings.TrimSpace(r.Header.Get("X-Client-Sub-Account-Context-Version")); value != "" {
		return value
	}
	return strings.TrimSpace(r.Header.Get("X-Persona-Context-Version"))
}

func readBody(r *http.Request) (map[string]any, error) {
	var data map[string]any
	if err := json.NewDecoder(r.Body).Decode(&data); err != nil {
		return nil, err
	}
	return data, nil
}
