package http

import (
	"net/http"
	"time"

	"quwoquan_service/services/user-service/internal/generated"
)

func (h *UserHandler) handleCreateAlipayAuthorizationRequest(w http.ResponseWriter, r *http.Request) {
	if _, err := readBody(r); err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	if h.alipayLogin == nil {
		writeHTTPError(
			w,
			r,
			generated.AppErrorFromSocialProviderUnavailable(
				"federated authorization capability unavailable",
			),
		)
		return
	}
	request, err := h.alipayLogin.IssueAuthorizationRequest(r.Context())
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"authorizationPayload": request.Payload,
		"expiresAt":            request.ExpiresAt.UTC().Format(time.RFC3339),
	})
}
