package http

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	profileinteractiongenerated "quwoquan_service/services/content-service/generated/content/profile_interaction_activity_view"
	profileinteractionapp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/application"
	profileinteractionreadapp "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/application"
)

func (h *ContentHandler) handleListProfileInteractionActivitiesReceived(
	w http.ResponseWriter,
	r *http.Request,
) {
	h.handleListProfileInteractionActivities(w, r, "received")
}

func (h *ContentHandler) handleListProfileInteractionActivitiesSent(
	w http.ResponseWriter,
	r *http.Request,
) {
	h.handleListProfileInteractionActivities(w, r, "sent")
}

func (h *ContentHandler) handleListProfileInteractionActivities(
	w http.ResponseWriter,
	r *http.Request,
	direction string,
) {
	if h.profileInteractionService == nil {
		writeHTTPError(w, r, profileinteractiongenerated.AppErrorFromInteractionReadModelUnavailable(
			"ProfileInteractionActivity query facade is not configured",
		))
		return
	}
	personaID := strings.TrimSpace(r.PathValue("personaId"))
	if personaID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"互动身份不能为空",
			"missing personaId",
		))
		return
	}
	limit := 20
	if raw := strings.TrimSpace(r.URL.Query().Get("limit")); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed <= 0 {
			writeHTTPError(w, r, contentgenerated.AppErrorFromInvalidArgument(
				"profile interaction limit must be positive",
			))
			return
		}
		limit = parsed
	}
	page, err := h.profileInteractionService.ListActivities(
		r.Context(),
		profileinteractionapp.ActivityPageQuery{
			OwnerPersonaID:  personaID,
			ViewerPersonaID: operationActorID(r),
			Direction:       direction,
			ActivityType:    strings.TrimSpace(r.URL.Query().Get("type")),
			Cursor:          strings.TrimSpace(r.URL.Query().Get("cursor")),
			Limit:           limit,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, page)
}

func (h *ContentHandler) handleUpdateProfileInteractionState(
	w http.ResponseWriter,
	r *http.Request,
) {
	if h.profileInteractionService == nil {
		writeHTTPError(w, r, profileinteractiongenerated.AppErrorFromInteractionReadModelUnavailable(
			"ProfileInteractionReadFact append facade is not configured",
		))
		return
	}
	personaID := strings.TrimSpace(r.PathValue("personaId"))
	activityID := strings.TrimSpace(r.PathValue("interactionId"))
	if personaID == "" || activityID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"互动标识不能为空",
			"missing personaId or interactionId",
		))
		return
	}
	if err := requireActiveProfileInteractionOwner(r, personaID); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	var body struct {
		State string `json:"state"`
	}
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeHTTPError(w, r, contentgenerated.AppErrorFromInvalidArgument(
			"decode ProfileInteractionReadFact request: "+err.Error(),
		))
		return
	}
	ack, err := h.profileInteractionService.AppendReadFact(
		r.Context(),
		profileinteractionreadapp.AppendReadFactCommand{
			OwnerPersonaID: personaID,
			ActivityID:     activityID,
			State:          strings.TrimSpace(body.State),
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusAccepted, ack)
}

func requireActiveProfileInteractionOwner(
	r *http.Request,
	personaID string,
) error {
	claims, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok || strings.TrimSpace(claims.Subject) == "" {
		return contentgenerated.AppErrorFromUnauthorized(
			"profile interactions require authenticated principal",
		)
	}
	activePersonaID := strings.TrimSpace(claims.Persona)
	if activePersonaID == "" {
		return contentgenerated.AppErrorFromUnauthorized(
			"profile interactions require an active persona",
		)
	}
	if activePersonaID != strings.TrimSpace(personaID) {
		return profileinteractiongenerated.AppErrorFromInteractionOwnerForbidden(
			"requested persona is not the active principal persona",
		)
	}
	return nil
}
