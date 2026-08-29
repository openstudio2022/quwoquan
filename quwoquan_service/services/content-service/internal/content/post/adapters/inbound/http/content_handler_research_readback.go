package http

import (
	"errors"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
)

// requestHasResearchRole 从已验签 principal 派生 research 身份标志
// （DEC-032）：role 由服务端签发进 access token，客户端无法自选。
func requestHasResearchRole(r *http.Request) bool {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return false
	}
	for _, role := range principal.Roles {
		if role == rtauth.RoleResearch {
			return true
		}
	}
	return false
}

func (h *ContentHandler) handleGetResearchReleaseReadback(
	w http.ResponseWriter,
	r *http.Request,
) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	accountID := ""
	if ok {
		accountID = strings.TrimSpace(principal.Actor.AccountID)
	}
	if accountID == "" {
		writeHTTPError(w, r, contentgenerated.AppErrorFromUnauthorized(
			"research release readback requires verified account principal",
		))
		return
	}
	if h.researchReleaseReadback == nil {
		writeHTTPError(w, r, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"research release readback is unavailable in this environment",
		))
		return
	}
	view, err := h.researchReleaseReadback.GetResearchReleaseReadback(
		r.Context(),
		accountID,
		r.Header.Get("X-Research-Identity-Attestation"),
	)
	if err != nil {
		switch {
		case errors.Is(err, postapp.ErrResearchIdentityInvalid):
			writeHTTPError(w, r, contentgenerated.AppErrorFromResearchIdentityInvalid(err.Error()))
		case errors.Is(err, postapp.ErrResearchReleaseNotResearch):
			writeHTTPError(w, r, contentgenerated.AppErrorFromResearchIdentityInvalid(
				"active release is not research-only",
			))
		default:
			writeHTTPError(w, r, contentgenerated.AppErrorFromRequiredDependencyUnavailable(err.Error()))
		}
		return
	}
	writeJSON(w, http.StatusOK, view)
}
