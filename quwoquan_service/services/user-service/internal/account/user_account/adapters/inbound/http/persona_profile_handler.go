package http

import "net/http"

func (h *UserHandler) handleGetPersonaProfile(w http.ResponseWriter, r *http.Request) {
	personaID := r.PathValue("personaId")
	profile, err := h.persona.GetPersonaProfileView(r.Context(), personaID)
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
