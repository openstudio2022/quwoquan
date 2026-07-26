package http

import "net/http"

func (h *UserHandler) handleGetSubAccountProfile(w http.ResponseWriter, r *http.Request) {
	subAccountID := r.PathValue("subAccountId")
	profile, err := h.subAccount.GetSubAccountProfileView(r.Context(), subAccountID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if profile == nil {
		writeNotFound(w, r, "resource not found")
		return
	}
	writeJSON(w, http.StatusOK, profile)
}
