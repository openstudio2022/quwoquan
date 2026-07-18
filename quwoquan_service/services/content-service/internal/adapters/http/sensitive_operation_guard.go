package http

import (
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

// RequireSensitiveOperationPrincipal is the fail-closed containment boundary
// used until generated operation authorization guards own every route.
func RequireSensitiveOperationPrincipal(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !isSensitiveOperation(r.Method, r.URL.Path) {
			next.ServeHTTP(w, r)
			return
		}
		if _, ok := verifiedOperationActorID(r); !ok {
			writeHTTPError(
				w,
				r,
				contentgenerated.AppErrorFromUnauthorized(
					"sensitive content operation requires a verified principal",
				),
			)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func isSensitiveOperation(method, path string) bool {
	if method == http.MethodPost && path == "/content/behaviors" {
		return true
	}
	if strings.HasPrefix(path, "/content/media/") {
		return true
	}
	if method != http.MethodPost {
		return false
	}
	return strings.HasSuffix(path, "/media:bind") &&
		(strings.HasPrefix(path, "/content/posts/") ||
			strings.HasPrefix(path, "/content/comments/"))
}

func verifiedOperationActorID(r *http.Request) (string, bool) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return "", false
	}
	return principal.Actor.BusinessActorID()
}

func operationActorID(r *http.Request) string {
	if actorID, ok := verifiedOperationActorID(r); ok {
		return actorID
	}
	return ""
}
