package http

import "net/http"

func (h *UserHandler) handleListCredentials(w http.ResponseWriter, r *http.Request) {
	creds, err := h.credentialQueries.ListCredentials(r.Context())
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"credentials": creds})
}

func (h *UserHandler) handleBindPhoneCredential(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	phone, _ := body["phone"].(string)
	otpCode, _ := body["otpCode"].(string)
	label, _ := body["displayLabel"].(string)
	result, err := h.auth.BindPhoneCredential(
		r.Context(),
		userID,
		phone,
		otpCode,
		label,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleBindCarrierPhoneCredential(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	carrierToken, _ := body["carrierToken"].(string)
	deviceID, _ := body["deviceId"].(string)
	platform, _ := body["platform"].(string)
	label, _ := body["displayLabel"].(string)
	result, err := h.auth.BindCarrierPhoneCredential(
		r.Context(),
		userID,
		carrierToken,
		deviceID,
		platform,
		label,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleUnbindCredential(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	credType := r.PathValue("credType")
	result, err := h.auth.UnbindCredential(r.Context(), userID, credType)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}
