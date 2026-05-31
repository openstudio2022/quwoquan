package http

import (
	"encoding/json"
	"net/http"
	"strconv"

	"quwoquan_service/services/tag-service/internal/application"
)

// TagHandler 暴露 tag-service 只读 HTTP API（对齐 contracts/metadata/tag/service.yaml）。
type TagHandler struct {
	svc *application.TagService
}

// NewTagHandler 注入应用服务。
func NewTagHandler(svc *application.TagService) *TagHandler {
	return &TagHandler{svc: svc}
}

// reservedRoutes 是 service.yaml 保留契约、仍未实现的端点；显式 501，不留静默 404。
//
// feedback 是写操作（用户对推荐的点击/忽略/修正），与 tag-service「只读消费导入产物」的
// 领域定位冲突——落地需新增写存储或路由到 behavior/recommendation 域，待架构评审，故保留 501。
// 其余 search / related / search-by-tags / cooccurrence / related-objects 已基于现有
// TagNode / ObjectTagIndex 只读数据实现。
var reservedRoutes = []string{
	"POST /v1/tag/feedback",
}

// Routes 注册交集核心、创作打标查询、推荐搜索与共现图谱路由 + 保留契约的 501 占位。
func (h *TagHandler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /v1/tag/resolve", h.resolve)
	mux.HandleFunc("GET /v1/tag/shared-tags", h.sharedTags)
	mux.HandleFunc("GET /v1/tag/inverted", h.inverted)
	mux.HandleFunc("GET /v1/tag/dimensions", h.listDimensions)
	mux.HandleFunc("GET /v1/tag/suggest", h.suggest)
	mux.HandleFunc("POST /v1/tag/validate", h.validate)
	mux.HandleFunc("GET /v1/tag/search", h.search)
	mux.HandleFunc("GET /v1/tag/related", h.related)
	mux.HandleFunc("POST /v1/tag/search-by-tags", h.searchByTags)
	mux.HandleFunc("GET /v1/tag/graph/cooccurrence", h.cooccurrence)
	mux.HandleFunc("GET /v1/tag/related-objects", h.relatedObjects)
	for _, p := range reservedRoutes {
		mux.HandleFunc(p, h.notImplemented)
	}
	return mux
}

func (h *TagHandler) resolve(w http.ResponseWriter, r *http.Request) {
	tagRef := r.URL.Query().Get("tagRef")
	if tagRef == "" {
		writeError(w, http.StatusBadRequest, "tagRef is required")
		return
	}
	view, err := h.svc.Resolve(r.Context(), tagRef)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if view == nil {
		writeError(w, http.StatusNotFound, "tagRef not found")
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *TagHandler) sharedTags(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	aID := q.Get("objectAId")
	bID := q.Get("objectBId")
	if aID == "" || bID == "" {
		writeError(w, http.StatusBadRequest, "objectAId and objectBId are required")
		return
	}
	views, err := h.svc.SharedTags(r.Context(), aID, q.Get("objectAType"), bID, q.Get("objectBType"), parseLimit(q.Get("limit")))
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, views)
}

func (h *TagHandler) inverted(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	tagRef := q.Get("tagRef")
	if tagRef == "" {
		writeError(w, http.StatusBadRequest, "tagRef is required")
		return
	}
	view, err := h.svc.Inverted(r.Context(), tagRef, q.Get("objectType"), parseLimit(q.Get("limit")))
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *TagHandler) listDimensions(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	views, err := h.svc.ListDimensions(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, views)
}

func (h *TagHandler) suggest(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	query := q.Get("q")
	if query == "" {
		writeError(w, http.StatusBadRequest, "q is required")
		return
	}
	views, err := h.svc.Suggest(r.Context(), query, q.Get("group"), parseLimit(q.Get("limit")))
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, views)
}

func (h *TagHandler) validate(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	var req struct {
		TagRefs []string `json:"tagRefs"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	view, err := h.svc.ValidateTagRefs(r.Context(), req.TagRefs)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *TagHandler) search(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	query := q.Get("q")
	if query == "" {
		writeError(w, http.StatusBadRequest, "q is required")
		return
	}
	views, err := h.svc.SearchTags(r.Context(), query, q.Get("group"), parseLimit(q.Get("limit")))
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, views)
}

func (h *TagHandler) related(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	tagRef := q.Get("tagRef")
	if tagRef == "" {
		writeError(w, http.StatusBadRequest, "tagRef is required")
		return
	}
	views, err := h.svc.RelatedTags(r.Context(), tagRef, parseLimit(q.Get("limit")))
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, views)
}

func (h *TagHandler) searchByTags(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	var req struct {
		TagRefs    []string `json:"tagRefs"`
		ObjectType string   `json:"objectType"`
		Limit      int      `json:"limit"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if len(req.TagRefs) == 0 {
		writeError(w, http.StatusBadRequest, "tagRefs is required")
		return
	}
	views, err := h.svc.SearchByTags(r.Context(), req.TagRefs, req.ObjectType, req.Limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, views)
}

func (h *TagHandler) cooccurrence(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	tagRef := q.Get("tagRef")
	if tagRef == "" {
		writeError(w, http.StatusBadRequest, "tagRef is required")
		return
	}
	views, err := h.svc.TagCooccurrence(r.Context(), tagRef, parseLimit(q.Get("minCount")), parseLimit(q.Get("limit")))
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, views)
}

func (h *TagHandler) relatedObjects(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	objectID := q.Get("objectId")
	if objectID == "" {
		writeError(w, http.StatusBadRequest, "objectId is required")
		return
	}
	views, err := h.svc.RelatedObjects(r.Context(), objectID, q.Get("objectType"), parseLimit(q.Get("limit")))
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, views)
}

func (h *TagHandler) notImplemented(w http.ResponseWriter, _ *http.Request) {
	writeError(w, http.StatusNotImplemented, "endpoint reserved; not implemented (feedback awaiting domain decision)")
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

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}
