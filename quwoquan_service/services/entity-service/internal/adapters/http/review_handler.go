package httpadapter

import (
	"net/http"
	"strings"

	"quwoquan_service/runtime/operation"
	reviewapp "quwoquan_service/services/entity-service/internal/application/homepage_review"
	entitygenerated "quwoquan_service/services/entity-service/internal/generated"
)

// reviewRequestBody 与 contracts/metadata/entity/homepage_review/service.yaml
// 的 writable_fields 对齐；actor 只来自可信 operation.Context，不接收 body 身份。
type reviewRequestBody struct {
	Rating                    int      `json:"rating"`
	Body                      string   `json:"body,omitempty"`
	TagRefs                   []string `json:"tagRefs,omitempty"`
	AuthorDisplayNameSnapshot string   `json:"authorDisplayNameSnapshot,omitempty"`
	AuthorAvatarURLSnapshot   string   `json:"authorAvatarUrlSnapshot,omitempty"`
}

// requiredPersonaActor 从 generated operation guard 注入的可信上下文取 persona；
// 缺失即结构化拒绝，禁止任何 header 或默认身份兜底。
func requiredPersonaActor(r *http.Request) (string, error) {
	invocation, ok := operation.FromContext(r.Context())
	if !ok {
		return "", entitygenerated.AppErrorFromPermissionDenied(
			"operation context is missing a trusted invocation",
		)
	}
	personaID := strings.TrimSpace(invocation.Actor.PersonaID)
	if personaID == "" {
		return "", entitygenerated.AppErrorFromPermissionDenied(
			"operation requires an authenticated persona actor",
		)
	}
	return personaID, nil
}

// handleHomepageReviews 处理 /homepages/{homepageId}/reviews 与 .../reviews/mine。
func (h *Handler) handleHomepageReviews(
	w http.ResponseWriter,
	r *http.Request,
	homepageID string,
	segments []string,
) {
	if h.reviews == nil {
		writeRuntimeNotFound(w, r)
		return
	}
	switch {
	case len(segments) == 2 && r.Method == http.MethodGet:
		query := r.URL.Query()
		page, err := h.reviews.ListByHomepage(r.Context(), reviewapp.ListQuery{
			HomepageID: homepageID,
			Cursor:     query.Get("cursor"),
			Limit:      parsePositiveInt(query.Get("limit"), 20),
		})
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, page)
	case len(segments) == 2 && r.Method == http.MethodPost:
		actorID, err := requiredPersonaActor(r)
		if err != nil {
			writeError(w, r, err)
			return
		}
		var body reviewRequestBody
		if err := decodeJSON(r, &body); err != nil {
			writeError(w, r, newBadRequest(err.Error()))
			return
		}
		view, err := h.reviews.Create(r.Context(), reviewapp.CreateCommand{
			HomepageID:                homepageID,
			ActorPersonaID:            actorID,
			Rating:                    body.Rating,
			Body:                      body.Body,
			TagRefs:                   body.TagRefs,
			AuthorDisplayNameSnapshot: body.AuthorDisplayNameSnapshot,
			AuthorAvatarURLSnapshot:   body.AuthorAvatarURLSnapshot,
		})
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusCreated, view)
	case len(segments) == 3 && segments[2] == "mine" && r.Method == http.MethodGet:
		actorID, err := requiredPersonaActor(r)
		if err != nil {
			writeError(w, r, err)
			return
		}
		view, err := h.reviews.GetMine(r.Context(), homepageID, actorID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, view)
	default:
		writeRuntimeNotFound(w, r)
	}
}

// handleReviewByID 处理 /homepage-reviews/{reviewId} 的 PATCH/DELETE。
func (h *Handler) handleReviewByID(w http.ResponseWriter, r *http.Request) {
	if h.reviews == nil {
		writeRuntimeNotFound(w, r)
		return
	}
	reviewID := strings.Trim(strings.TrimPrefix(r.URL.Path, "/homepage-reviews/"), "/")
	if reviewID == "" || strings.Contains(reviewID, "/") {
		writeRuntimeNotFound(w, r)
		return
	}
	actorID, err := requiredPersonaActor(r)
	if err != nil {
		writeError(w, r, err)
		return
	}
	switch r.Method {
	case http.MethodPatch:
		var body reviewRequestBody
		if err := decodeJSON(r, &body); err != nil {
			writeError(w, r, newBadRequest(err.Error()))
			return
		}
		view, err := h.reviews.Update(r.Context(), reviewapp.UpdateCommand{
			ReviewID:                  reviewID,
			ActorPersonaID:            actorID,
			Rating:                    body.Rating,
			Body:                      body.Body,
			TagRefs:                   body.TagRefs,
			AuthorDisplayNameSnapshot: body.AuthorDisplayNameSnapshot,
			AuthorAvatarURLSnapshot:   body.AuthorAvatarURLSnapshot,
		})
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, view)
	case http.MethodDelete:
		view, err := h.reviews.Delete(r.Context(), reviewapp.DeleteCommand{
			ReviewID:       reviewID,
			ActorPersonaID: actorID,
		})
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, view)
	default:
		writeRuntimeNotFound(w, r)
	}
}
