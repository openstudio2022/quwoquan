package httpadapter

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/application"
)

// TagHandler 暴露 tag-service 只读 HTTP API（对齐 services/tag-service/contracts/operations.yaml）。
type TagHandler struct {
	svc *application.TagService
}

// NewTagHandler 注入应用服务。
func NewTagHandler(svc *application.TagService) *TagHandler {
	return &TagHandler{svc: svc}
}

// Routes 注册已实现的交集核心、创作打标查询、推荐搜索与共现图谱路由。
func (h *TagHandler) Routes() http.Handler {
	mux := http.NewServeMux()
	h.Register(mux)
	return mux
}

// Register 挂载只读查询路由到既有 mux（与 release/feedback handler 组合装配）。
func (h *TagHandler) Register(mux *http.ServeMux) {
	Register(mux, Handlers{
		Resolve: h.resolve, ListChildren: h.listChildren,
		SharedTags: h.sharedTags, Inverted: h.inverted,
		ListDimensions: h.listDimensions, Suggest: h.suggest,
		Validate: h.validate, Search: h.search, Related: h.related,
		SearchByTags: h.searchByTags, Cooccurrence: h.cooccurrence,
		RelatedObjects: h.relatedObjects,
	})
}

func (h *TagHandler) resolve(w http.ResponseWriter, r *http.Request) {
	tagRef := r.URL.Query().Get("tagRef")
	if tagRef == "" {
		writeTagError(w, r, tagInvalidArgument("tagRef is required"))
		return
	}
	view, err := h.svc.Resolve(r.Context(), tagRef)
	if err != nil {
		writeTagError(w, r, tagStorageReadFailed(err))
		return
	}
	if view == nil {
		writeTagError(w, r, tagNotFound("tagRef not found"))
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *TagHandler) listChildren(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	parentTagRef := q.Get("parentTagRef")
	if parentTagRef == "" {
		writeTagError(w, r, tagInvalidArgument("parentTagRef is required"))
		return
	}
	views, err := h.svc.ListChildren(r.Context(), parentTagRef, parseLimit(q.Get("limit")))
	if err != nil {
		if errors.Is(err, application.ErrTagParentNotFound) {
			writeTagError(w, r, tagNotFound("parentTagRef not found"))
			return
		}
		writeTagError(w, r, tagStorageReadFailed(err))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": views})
}

func (h *TagHandler) sharedTags(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	aID := q.Get("objectAId")
	bID := q.Get("objectBId")
	if aID == "" || bID == "" {
		writeTagError(w, r, tagInvalidArgument("objectAId and objectBId are required"))
		return
	}
	views, err := h.svc.SharedTags(r.Context(), aID, q.Get("objectAType"), bID, q.Get("objectBType"), parseLimit(q.Get("limit")))
	if err != nil {
		writeTagError(w, r, tagStorageReadFailed(err))
		return
	}
	writeJSON(w, http.StatusOK, views)
}

func (h *TagHandler) inverted(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	tagRef := q.Get("tagRef")
	if tagRef == "" {
		writeTagError(w, r, tagInvalidArgument("tagRef is required"))
		return
	}
	includeDescendants := strings.EqualFold(strings.TrimSpace(q.Get("includeDescendants")), "true")
	view, err := h.svc.Inverted(r.Context(), tagRef, q.Get("objectType"), parseLimit(q.Get("limit")), includeDescendants)
	if err != nil {
		writeTagError(w, r, tagStorageReadFailed(err))
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *TagHandler) listDimensions(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeTagError(w, r, tagInvalidArgument("method not allowed"))
		return
	}
	views, err := h.svc.ListDimensions(r.Context())
	if err != nil {
		writeTagError(w, r, tagStorageReadFailed(err))
		return
	}
	writeJSON(w, http.StatusOK, views)
}

func (h *TagHandler) suggest(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	query := q.Get("q")
	if query == "" {
		writeTagError(w, r, tagInvalidArgument("q is required"))
		return
	}
	views, err := h.svc.Suggest(r.Context(), query, q.Get("group"), parseLimit(q.Get("limit")))
	if err != nil {
		writeTagError(w, r, tagStorageReadFailed(err))
		return
	}
	writeJSON(w, http.StatusOK, views)
}

func (h *TagHandler) validate(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeTagError(w, r, tagInvalidArgument("method not allowed"))
		return
	}
	var req struct {
		ExpectedTaxonomyReleaseID string   `json:"expectedTaxonomyReleaseId"`
		TagRefs                   []string `json:"tagRefs"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeTagError(w, r, tagInvalidArgument("invalid request body"))
		return
	}
	if strings.TrimSpace(req.ExpectedTaxonomyReleaseID) == "" {
		writeTagError(w, r, tagInvalidArgument("expectedTaxonomyReleaseId is required"))
		return
	}
	view, err := h.svc.ValidateTagRefs(
		r.Context(),
		req.ExpectedTaxonomyReleaseID,
		req.TagRefs,
	)
	if err != nil {
		writeTagError(w, r, tagStorageReadFailed(err))
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *TagHandler) search(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	query := q.Get("q")
	if query == "" {
		writeTagError(w, r, tagInvalidArgument("q is required"))
		return
	}
	views, err := h.svc.SearchTags(r.Context(), query, q.Get("group"), parseLimit(q.Get("limit")))
	if err != nil {
		writeTagError(w, r, tagStorageReadFailed(err))
		return
	}
	writeJSON(w, http.StatusOK, views)
}

func (h *TagHandler) related(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	tagRef := q.Get("tagRef")
	if tagRef == "" {
		writeTagError(w, r, tagInvalidArgument("tagRef is required"))
		return
	}
	views, err := h.svc.RelatedTags(r.Context(), tagRef, parseLimit(q.Get("limit")))
	if err != nil {
		writeTagError(w, r, tagStorageReadFailed(err))
		return
	}
	writeJSON(w, http.StatusOK, views)
}

func (h *TagHandler) searchByTags(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeTagError(w, r, tagInvalidArgument("method not allowed"))
		return
	}
	var req struct {
		TagRefs    []string `json:"tagRefs"`
		ObjectType string   `json:"objectType"`
		Limit      int      `json:"limit"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeTagError(w, r, tagInvalidArgument("invalid request body"))
		return
	}
	if len(req.TagRefs) == 0 {
		writeTagError(w, r, tagInvalidArgument("tagRefs is required"))
		return
	}
	views, err := h.svc.SearchByTags(r.Context(), req.TagRefs, req.ObjectType, req.Limit)
	if err != nil {
		writeTagError(w, r, tagStorageReadFailed(err))
		return
	}
	writeJSON(w, http.StatusOK, views)
}

func (h *TagHandler) cooccurrence(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	tagRef := q.Get("tagRef")
	if tagRef == "" {
		writeTagError(w, r, tagInvalidArgument("tagRef is required"))
		return
	}
	views, err := h.svc.TagCooccurrence(r.Context(), tagRef, parseLimit(q.Get("minCount")), parseLimit(q.Get("limit")))
	if err != nil {
		writeTagError(w, r, tagStorageReadFailed(err))
		return
	}
	writeJSON(w, http.StatusOK, views)
}

func (h *TagHandler) relatedObjects(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	objectID := q.Get("objectId")
	if objectID == "" {
		writeTagError(w, r, tagInvalidArgument("objectId is required"))
		return
	}
	views, err := h.svc.RelatedObjects(r.Context(), objectID, q.Get("objectType"), parseLimit(q.Get("limit")))
	if err != nil {
		writeTagError(w, r, tagStorageReadFailed(err))
		return
	}
	writeJSON(w, http.StatusOK, views)
}

func parseLimit(s string) int {
	if s == "" {
		return 0
	}
	n, err := strconv.Atoi(s)
	if err != nil || n < 0 {
		return 0
	}
	return n
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}
