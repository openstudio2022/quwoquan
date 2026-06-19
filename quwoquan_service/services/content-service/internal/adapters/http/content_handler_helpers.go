package http

import (
	"encoding/json"
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
)

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

// resolveUserID extracts userId from query param → X-Client-User-Id header.
func resolveUserID(r *http.Request) string {
	if v := strings.TrimSpace(r.URL.Query().Get("userId")); v != "" {
		return v
	}
	return strings.TrimSpace(r.Header.Get("X-Client-User-Id"))
}

// resolveDeviceActorID extracts the privacy-safe derived device actor id from
// query param deviceActorId → X-Client-Device-Actor-Id header. Used for guest
// device-dimension like/share counting (separate from account dimension).
func resolveDeviceActorID(r *http.Request) string {
	if v := strings.TrimSpace(r.URL.Query().Get("deviceActorId")); v != "" {
		return v
	}
	return strings.TrimSpace(r.Header.Get("X-Client-Device-Actor-Id"))
}

func resolveViewerCircleIDs(r *http.Request) []string {
	if v := strings.TrimSpace(r.URL.Query().Get("viewerCircleIds")); v != "" {
		return splitCSV(v)
	}
	return splitCSV(r.Header.Get("X-Client-Circle-Ids"))
}

func resolveViewerUserID(r *http.Request) string {
	if v := strings.TrimSpace(r.URL.Query().Get("viewerId")); v != "" {
		return v
	}
	return strings.TrimSpace(r.Header.Get("X-Client-User-Id"))
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
