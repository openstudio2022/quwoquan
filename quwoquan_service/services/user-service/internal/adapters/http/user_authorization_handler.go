package http

import (
	"net/http"
	"time"
)

func (h *UserHandler) handleCreateAlipayAuthorizationRequest(w http.ResponseWriter, r *http.Request) {
	if _, err := readBody(r); err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	payload, expiresAt, err := h.auth.CreateSocialAuthorizationRequest(r.Context(), "alipay")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"authorizationPayload": payload,
		"expiresAt":            expiresAt.UTC().Format(time.RFC3339),
	})
}
