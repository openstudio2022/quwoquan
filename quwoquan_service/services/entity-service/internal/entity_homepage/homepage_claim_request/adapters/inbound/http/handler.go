package http

import (
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	httpcodec "quwoquan_service/runtime/httpcodec"
	"quwoquan_service/runtime/operation"
	entitygenerated "quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	claimapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/application"
	claimmodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/domain/model"
)

type Handler struct{ facade *claimapp.Facade }

func NewHandler(facade *claimapp.Facade) *Handler {
	if facade == nil {
		panic("HomepageClaimRequest HTTP handler requires facade")
	}
	return &Handler{facade: facade}
}

func (h *Handler) ListQueue(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	status := strings.TrimSpace(query.Get("status"))
	if status == "" {
		status = string(claimmodel.StatusPendingReview)
	}
	payload, err := h.facade.ListQueue(r.Context(), claimapp.QueueQuery{
		HomepageID: strings.TrimSpace(query.Get("homepageId")),
		Status:     claimmodel.Status(status),
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
			"CreateHomepageClaimRequest requires trusted persona actor",
		))
		return
	}
	var body struct {
		ClaimTier            claimmodel.ClaimTier `json:"claimTier"`
		BusinessLicenseURL   string               `json:"businessLicenseUrl"`
		ContactPhone         string               `json:"contactPhone"`
		IdentityCardFrontURL string               `json:"identityCardFrontUrl"`
		IdentityCardBackURL  string               `json:"identityCardBackUrl"`
		Note                 string               `json:"note"`
	}
	if err := httpcodec.DecodeStrictJSON(r, &body); err != nil {
		writeError(w, r, entitygenerated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	view, err := h.facade.Create(r.Context(), claimapp.CreateCommand{
		HomepageID: strings.TrimSpace(homepageID), ActorPersonaID: actor,
		ClaimTier: body.ClaimTier, BusinessLicenseURL: body.BusinessLicenseURL,
		ContactPhone: body.ContactPhone, IdentityCardFrontURL: body.IdentityCardFrontURL,
		IdentityCardBackURL: body.IdentityCardBackURL, Note: body.Note,
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
	claimRequestID string,
) {
	actor, ok := accountActor(r)
	if !ok {
		writeError(w, r, entitygenerated.AppErrorFromPermissionDenied(
			"ReviewHomepageClaimRequest requires trusted account actor",
		))
		return
	}
	var body struct {
		Status     claimmodel.Status `json:"status"`
		ReviewNote string            `json:"reviewNote"`
	}
	if err := httpcodec.DecodeStrictJSON(r, &body); err != nil {
		writeError(w, r, entitygenerated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	view, err := h.facade.Review(r.Context(), claimapp.ReviewCommand{
		HomepageID:     strings.TrimSpace(homepageID),
		ClaimRequestID: strings.TrimSpace(claimRequestID), ActorAccountID: actor,
		TargetStatus: body.Status, ReviewNote: body.ReviewNote,
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
	return strings.TrimSpace(current.Actor.PersonaID), ok && strings.TrimSpace(current.Actor.PersonaID) != ""
}

func accountActor(r *http.Request) (string, bool) {
	current, ok := operation.FromContext(r.Context())
	return strings.TrimSpace(current.Actor.AccountID), ok && strings.TrimSpace(current.Actor.AccountID) != ""
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	httpcodec.WriteJSON(w, status, payload, "homepage_claim_request")
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
