package http

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	profileinteractionapp "quwoquan_service/services/content-service/internal/application/content/profile_interaction"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
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
		writeHTTPError(w, r, contentgenerated.AppErrorFromInteractionReadModelUnavailable(
			"ProfileInteractionActivity query facade is not configured",
		))
		return
	}
	subAccountID := strings.TrimSpace(r.PathValue("subAccountId"))
	if subAccountID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"互动身份不能为空",
			"missing subAccountId",
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
			OwnerPersonaID: subAccountID,
			ViewerPersonaID: operationActorID(r),
			Direction: direction,
			ActivityType: strings.TrimSpace(r.URL.Query().Get("type")),
			Cursor: strings.TrimSpace(r.URL.Query().Get("cursor")),
			Limit: limit,
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
		writeHTTPError(w, r, contentgenerated.AppErrorFromInteractionReadModelUnavailable(
			"ProfileInteractionReadFact append facade is not configured",
		))
		return
	}
	subAccountID := strings.TrimSpace(r.PathValue("subAccountId"))
	activityID := strings.TrimSpace(r.PathValue("interactionId"))
	if subAccountID == "" || activityID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"互动标识不能为空",
			"missing subAccountId or interactionId",
		))
		return
	}
	if err := requireActiveProfileInteractionOwner(r, subAccountID); err != nil {
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
			"decode ProfileInteractionReadFact request: " + err.Error(),
		))
		return
	}
	ack, err := h.profileInteractionService.AppendReadFact(
		r.Context(),
		profileinteractionapp.AppendReadFactCommand{
			OwnerPersonaID: subAccountID,
			ActivityID: activityID,
			State: strings.TrimSpace(body.State),
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
	subAccountID string,
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
	if activePersonaID != strings.TrimSpace(subAccountID) {
		return contentgenerated.AppErrorFromInteractionOwnerForbidden(
			"requested sub-account is not the active principal persona",
		)
	}
	return nil
}
