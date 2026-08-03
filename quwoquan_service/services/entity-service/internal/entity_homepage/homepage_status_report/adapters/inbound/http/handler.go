package http

import (
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	httpcodec "quwoquan_service/runtime/httpcodec"
	"quwoquan_service/runtime/operation"
	entitygenerated "quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	statusapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_status_report/application"
	statusmodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_status_report/domain/model"
)

type Handler struct{ facade *statusapp.Facade }

func NewHandler(facade *statusapp.Facade) *Handler {
	if facade == nil {
		panic("HomepageStatusReport HTTP handler requires facade")
	}
	return &Handler{facade: facade}
}

func (h *Handler) ListQueue(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	status := strings.TrimSpace(query.Get("status"))
	if status == "" {
		status = string(statusmodel.StatusPendingReview)
	}
	payload, err := h.facade.ListQueue(r.Context(), statusapp.QueueQuery{
		HomepageID: strings.TrimSpace(query.Get("homepageId")),
		Status:     statusmodel.Status(status),
		Cursor:     strings.TrimSpace(query.Get("cursor")),
		Limit:      positiveLimit(query.Get("limit")),
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, payload)
}

func (h *Handler) Create(w http.ResponseWriter, r *http.Request, homepageID string) {
	actor, ok := personaActor(r)
	if !ok {
		writeError(w, r, entitygenerated.AppErrorFromPermissionDenied(
			"CreateHomepageStatusReport requires trusted persona actor",
		))
		return
	}
	var body struct {
		Reason       statusmodel.Reason `json:"reason"`
		Description  string             `json:"description"`
		EvidenceURLs []string           `json:"evidenceUrls"`
	}
	if err := httpcodec.DecodeStrictJSON(r, &body); err != nil {
		writeError(w, r, entitygenerated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	view, err := h.facade.Create(r.Context(), statusapp.CreateCommand{
		HomepageID: strings.TrimSpace(homepageID), ActorPersonaID: actor,
		Reason: body.Reason, Description: body.Description,
		EvidenceURLs: append([]string(nil), body.EvidenceURLs...),
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, view)
}

func (h *Handler) Review(
	w http.ResponseWriter,
	r *http.Request,
	homepageID string,
	reportID string,
) {
	actor, ok := accountActor(r)
	if !ok {
		writeError(w, r, entitygenerated.AppErrorFromPermissionDenied(
			"ReviewHomepageStatusReport requires trusted account actor",
		))
		return
	}
	var body struct {
		Status     statusmodel.Status `json:"status"`
		ReviewNote string             `json:"reviewNote"`
	}
	if err := httpcodec.DecodeStrictJSON(r, &body); err != nil {
		writeError(w, r, entitygenerated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	view, err := h.facade.Review(r.Context(), statusapp.ReviewCommand{
		HomepageID: strings.TrimSpace(homepageID), ReportID: strings.TrimSpace(reportID),
		ActorAccountID: actor, TargetStatus: body.Status, ReviewNote: body.ReviewNote,
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func positiveLimit(raw string) int {
	value, err := strconv.Atoi(strings.TrimSpace(raw))
	if err != nil || value < 1 {
		return 20
	}
	if value > 100 {
		return 100
	}
	return value
}

func personaActor(r *http.Request) (string, bool) {
	current, ok := operation.FromContext(r.Context())
	actor := strings.TrimSpace(current.Actor.PersonaID)
	return actor, ok && actor != ""
}

func accountActor(r *http.Request) (string, bool) {
	current, ok := operation.FromContext(r.Context())
	actor := strings.TrimSpace(current.Actor.AccountID)
	return actor, ok && actor != ""
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	httpcodec.WriteJSON(w, status, payload, "homepage_status_report")
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
