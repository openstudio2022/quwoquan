package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

func requireJSONEOF(decoder *json.Decoder) error {
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"请求体必须只包含一个 JSON 对象",
			"request contains trailing JSON values",
		)
	}
	return nil
}

func decodeRequiredJSONBody(r *http.Request, target any) error {
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error())
	}
	return requireJSONEOF(decoder)
}

func requiredCommentPersona(r *http.Request) (string, error) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok || strings.TrimSpace(principal.Actor.PersonaID) == "" {
		return "", contentgenerated.AppErrorFromUnauthorized(
			"Comment operation requires verified persona principal",
		)
	}
	return strings.TrimSpace(principal.Actor.PersonaID), nil
}

func optionalCommentPersona(r *http.Request) string {
	if r == nil {
		return ""
	}
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return ""
	}
	return strings.TrimSpace(principal.Actor.PersonaID)
}

// HTTP 请求解析 / 响应写出小工具，自 content_handler.go 拆出
// （同 http 包，R03 行数预算，行为不变）。

func pathParamAfter(path, prefix, suffix string) string {
	v := strings.TrimSpace(strings.TrimPrefix(path, prefix))
	if suffix != "" {
		v = strings.TrimSuffix(v, suffix)
	}
	return strings.Trim(strings.TrimSpace(v), "/")
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

// resolveSessionID extracts sessionId from query param → body → X-Client-Session-Id header.
func resolveSessionID(r *http.Request) string {
	if v := strings.TrimSpace(r.URL.Query().Get("sessionId")); v != "" {
		return v
	}
	return strings.TrimSpace(r.Header.Get("X-Client-Session-Id"))
}

// resolveUserID always prefers the verified principal. Query/header values are
// accepted only by isolated transport tests; a client must never be able to
// select another account once authentication has completed.
func resolveUserID(r *http.Request) string {
	if r != nil {
		if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
			return strings.TrimSpace(principal.Actor.AccountID)
		}
	}
	if v := strings.TrimSpace(r.URL.Query().Get("userId")); v != "" {
		return v
	}
	return strings.TrimSpace(r.Header.Get("X-Client-User-Id"))
}

// resolvePersonaID returns the verified public business actor. Account IDs must
// never be persisted as Post author IDs because persona is the aggregate owner
// declared by the SubmitPostPublication operation contract. Header fallbacks exist only
// for unguarded local transport tests.
func resolvePersonaID(r *http.Request) string {
	if r != nil {
		if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
			return strings.TrimSpace(principal.Actor.PersonaID)
		}
	}
	if v := strings.TrimSpace(r.Header.Get("X-Client-Sub-Account-Id")); v != "" {
		return v
	}
	return strings.TrimSpace(r.Header.Get("X-Client-User-Id"))
}

// resolveDeviceActorID always prefers the verified device principal. Query and
// header values remain only for isolated transport tests without auth middleware.
func resolveDeviceActorID(r *http.Request) string {
	if r != nil {
		if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
			return strings.TrimSpace(principal.Actor.DeviceActorID)
		}
	}
	if v := strings.TrimSpace(r.URL.Query().Get("deviceActorId")); v != "" {
		return v
	}
	return strings.TrimSpace(r.Header.Get("X-Client-Device-Actor-Id"))
}

// resolveBlockedUserIDs extracts blocked author IDs from:
//  1. query: blockedUserIds=a,b
//  2. header: X-Blocked-User-Ids: a,b
func resolveBlockedUserIDs(r *http.Request) []string {
	if v := strings.TrimSpace(r.URL.Query().Get("blockedUserIds")); v != "" {
		return splitCSV(v)
	}
	return splitCSV(r.Header.Get("X-Blocked-User-Ids"))
}

// resolveBlockedKeywords extracts blocked keywords from:
//  1. query: blockedKeywords=k1,k2
//  2. header: X-Blocked-Keywords: k1,k2
func resolveBlockedKeywords(r *http.Request) []string {
	if v := strings.TrimSpace(r.URL.Query().Get("blockedKeywords")); v != "" {
		return splitCSV(v)
	}
	return splitCSV(r.Header.Get("X-Blocked-Keywords"))
}

func splitCSV(raw string) []string {
	if strings.TrimSpace(raw) == "" {
		return nil
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		v := strings.TrimSpace(p)
		if v != "" {
			out = append(out, v)
		}
	}
	return out
}
