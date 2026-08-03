package http

import (
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	httpcodec "quwoquan_service/runtime/httpcodec"
	"quwoquan_service/runtime/operation"
	entitygenerated "quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	reviewapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/application"
)

type Handler struct{ facade *reviewapp.Facade }

func NewHandler(facade *reviewapp.Facade) *Handler {
	if facade == nil {
		panic("HomepageReview HTTP handler requires facade")
	}
	return &Handler{facade: facade}
}

type requestBody struct {
	Rating                    int      `json:"rating"`
	Body                      string   `json:"body,omitempty"`
	TagRefs                   []string `json:"tagRefs,omitempty"`
	AuthorDisplayNameSnapshot string   `json:"authorDisplayNameSnapshot,omitempty"`
	AuthorAvatarURLSnapshot   string   `json:"authorAvatarUrlSnapshot,omitempty"`
}

func (h *Handler) List(w http.ResponseWriter, r *http.Request, homepageID string) {
	query := r.URL.Query()
	page, err := h.facade.ListByHomepage(r.Context(), reviewapp.ListQuery{
		HomepageID: strings.TrimSpace(homepageID),
		Cursor: strings.TrimSpace(query.Get("cursor")), Limit: positiveLimit(query.Get("limit")),
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, page)
}

func (h *Handler) Create(w http.ResponseWriter, r *http.Request, homepageID string) {
	actor, ok := personaActor(r)
	if !ok {
		writeError(w, r, entitygenerated.AppErrorFromPermissionDenied(
			"CreateHomepageReview requires trusted persona actor",
		))
		return
	}
	var body requestBody
	if err := httpcodec.DecodeStrictJSON(r, &body); err != nil {
		writeError(w, r, entitygenerated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	view, err := h.facade.Create(r.Context(), reviewapp.CreateCommand{
		HomepageID: strings.TrimSpace(homepageID), ActorPersonaID: actor,
		Rating: body.Rating, Body: body.Body, TagRefs: body.TagRefs,
		AuthorDisplayNameSnapshot: body.AuthorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot: body.AuthorAvatarURLSnapshot,
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, view)
}

func (h *Handler) GetMine(w http.ResponseWriter, r *http.Request, homepageID string) {
	actor, ok := personaActor(r)
	if !ok {
		writeError(w, r, entitygenerated.AppErrorFromPermissionDenied(
			"GetMyHomepageReview requires trusted persona actor",
		))
		return
	}
	view, err := h.facade.GetMine(r.Context(), strings.TrimSpace(homepageID), actor)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) Update(w http.ResponseWriter, r *http.Request, reviewID string) {
	actor, ok := personaActor(r)
	if !ok {
		writeError(w, r, entitygenerated.AppErrorFromPermissionDenied(
			"UpdateHomepageReview requires trusted persona actor",
		))
		return
	}
	var body requestBody
	if err := httpcodec.DecodeStrictJSON(r, &body); err != nil {
		writeError(w, r, entitygenerated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	view, err := h.facade.Update(r.Context(), reviewapp.UpdateCommand{
		ReviewID: strings.TrimSpace(reviewID), ActorPersonaID: actor,
		Rating: body.Rating, Body: body.Body, TagRefs: body.TagRefs,
		AuthorDisplayNameSnapshot: body.AuthorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot: body.AuthorAvatarURLSnapshot,
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) Delete(w http.ResponseWriter, r *http.Request, reviewID string) {
	actor, ok := personaActor(r)
	if !ok {
		writeError(w, r, entitygenerated.AppErrorFromPermissionDenied(
			"DeleteHomepageReview requires trusted persona actor",
		))
		return
	}
	view, err := h.facade.Delete(r.Context(), reviewapp.DeleteCommand{
		ReviewID: strings.TrimSpace(reviewID), ActorPersonaID: actor,
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

func writeJSON(w http.ResponseWriter, status int, payload any) {
	httpcodec.WriteJSON(w, status, payload, "homepage_review")
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
