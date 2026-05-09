package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/circle-service/internal/application"
	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
	"quwoquan_service/services/circle-service/internal/infrastructure/persistence"
)

// CircleHandler adapts circle application services to HTTP.
type CircleHandler struct {
	circleService *application.CircleService
	fileService   *application.FileService
}

func NewCircleHandler(cs *application.CircleService, fs *application.FileService) *CircleHandler {
	return &CircleHandler{circleService: cs, fileService: fs}
}

func (h *CircleHandler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", h.handleHealthz)

	// Circles CRUD
	mux.HandleFunc("/v1/circles", h.handleCircles)
	mux.HandleFunc("GET /v1/circles/search", h.handleSearchCircles)
	mux.HandleFunc("/v1/circles/behaviors", h.handleBehaviors)
	mux.HandleFunc("/v1/circles/", h.handleCircleSubRoutes)

	// User circles
	mux.HandleFunc("/v1/users/", h.handleUserCircles)

	return mux
}

func (h *CircleHandler) handleHealthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

// --- /v1/circles ---

func (h *CircleHandler) handleCircles(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		h.handleListCircles(w, r)
	case http.MethodPost:
		h.handleCreateCircle(w, r)
	default:
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "method not allowed"))
	}
}

func (h *CircleHandler) handleListCircles(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	limit, _ := strconv.Atoi(q.Get("limit"))
	if limit <= 0 {
		limit = 20
	}
	resp := h.circleService.ListCircles(r.Context(), application.ListCirclesRequest{
		Category:     q.Get("category"),
		DomainID:     q.Get("domainId"),
		RecommendFor: q.Get("recommendFor"),
		Sort:         q.Get("sort"),
		Cursor:       q.Get("cursor"),
		Limit:        limit,
	})
	writeJSON(w, http.StatusOK, resp)
}

func (h *CircleHandler) handleSearchCircles(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	limit, _ := strconv.Atoi(q.Get("limit"))
	if limit <= 0 {
		limit = 20
	}
	resp := h.circleService.SearchCircles(r.Context(), application.SearchCirclesRequest{
		Query:       q.Get("query"),
		CategoryID:  q.Get("categoryId"),
		SubCategory: q.Get("subCategory"),
		Cursor:      q.Get("cursor"),
		Limit:       limit,
	})
	writeJSON(w, http.StatusOK, resp)
}

func (h *CircleHandler) handleCreateCircle(w http.ResponseWriter, r *http.Request) {
	var req application.CreateCircleRequest
	if err := readJSON(r, &req); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
		return
	}
	req.OwnerID = resolveUserID(r)

	circle, err := h.circleService.CreateCircle(r.Context(), req)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"data": circle})
}

// --- /v1/circles/{circleId}/... ---

func (h *CircleHandler) handleCircleSubRoutes(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/v1/circles/")
	parts := strings.Split(path, "/")
	if len(parts) == 0 {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "missing circleId"))
		return
	}
	circleID := parts[0]

	if len(parts) == 1 {
		switch r.Method {
		case http.MethodGet:
			h.handleGetCircle(w, r, circleID)
		case http.MethodPatch:
			h.handleUpdateCircle(w, r, circleID)
		case http.MethodDelete:
			h.handleArchiveCircle(w, r, circleID)
		default:
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "method not allowed"))
		}
		return
	}

	subResource := parts[1]
	switch subResource {
	case "join":
		h.handleJoinCircle(w, r, circleID)
	case "leave":
		h.handleLeaveCircle(w, r, circleID)
	case "members":
		h.handleMembers(w, r, circleID, parts[2:])
	case "groups":
		h.handleGroups(w, r, circleID, parts[2:])
	case "feed":
		h.handleFeed(w, r, circleID, parts[2:])
	case "stats":
		h.handleGetStats(w, r, circleID)
	case "sections":
		h.handleUpdateSections(w, r, circleID)
	case "files":
		h.handleFiles(w, r, circleID, parts[2:])
	default:
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "unknown sub-resource: "+subResource))
	}
}

// --- Circle detail ---

func (h *CircleHandler) handleGetCircle(w http.ResponseWriter, r *http.Request, circleID string) {
	circle, err := h.circleService.GetCircle(r.Context(), circleID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"data": circle})
}

func (h *CircleHandler) handleUpdateCircle(w http.ResponseWriter, r *http.Request, circleID string) {
	var data map[string]any
	if err := readJSON(r, &data); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
		return
	}
	circle, err := h.circleService.UpdateCircle(r.Context(), circleID, data)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"data": circle})
}

func (h *CircleHandler) handleArchiveCircle(w http.ResponseWriter, r *http.Request, circleID string) {
	if err := h.circleService.ArchiveCircle(r.Context(), circleID); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// --- Membership ---

func (h *CircleHandler) handleJoinCircle(w http.ResponseWriter, r *http.Request, circleID string) {
	if r.Method != http.MethodPost {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "only POST"))
		return
	}
	if err := h.circleService.JoinCircle(r.Context(), circleID, resolveActorSubAccountID(r)); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *CircleHandler) handleLeaveCircle(w http.ResponseWriter, r *http.Request, circleID string) {
	if r.Method != http.MethodPost {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "only POST"))
		return
	}
	if err := h.circleService.LeaveCircle(r.Context(), circleID, resolveActorSubAccountID(r)); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *CircleHandler) handleMembers(w http.ResponseWriter, r *http.Request, circleID string, rest []string) {
	if len(rest) == 0 {
		if r.Method != http.MethodGet {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "only GET"))
			return
		}
		q := r.URL.Query()
		limit, _ := strconv.Atoi(q.Get("limit"))
		if limit <= 0 {
			limit = 20
		}
		members, cursor := h.circleService.ListMembers(r.Context(), circleID, limit, q.Get("cursor"))
		if members == nil {
			members = []model.CircleMember{}
		}
		writeJSON(w, http.StatusOK, map[string]any{"items": members, "cursor": cursor})
		return
	}

	// /v1/circles/{circleId}/members/{userId}/role
	if len(rest) >= 2 && rest[1] == "role" {
		if r.Method != http.MethodPatch {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "only PATCH"))
			return
		}
		var body struct {
			Role string `json:"role"`
		}
		if err := readJSON(r, &body); err != nil {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
			return
		}
		if err := h.circleService.UpdateMemberRole(r.Context(), circleID, rest[0], body.Role); err != nil {
			writeHTTPError(w, r, err)
			return
		}
		w.WriteHeader(http.StatusNoContent)
		return
	}

	writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "unknown member sub-resource"))
}

// --- Feed ---

func (h *CircleHandler) handleFeed(w http.ResponseWriter, r *http.Request, circleID string, rest []string) {
	if len(rest) == 0 {
		if r.Method != http.MethodGet {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "only GET"))
			return
		}
		q := r.URL.Query()
		limit, _ := strconv.Atoi(q.Get("limit"))
		if limit <= 0 {
			limit = 20
		}
		items, cursor := h.circleService.GetCircleFeed(r.Context(), circleID, limit, q.Get("cursor"), q.Get("sort"))
		writeJSON(w, http.StatusOK, map[string]any{"items": items, "cursor": cursor})
		return
	}

	// /v1/circles/{circleId}/feed/{postId}/pin or /feature
	if len(rest) >= 2 {
		postID := rest[0]
		action := rest[1]
		if r.Method != http.MethodPatch {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "only PATCH"))
			return
		}
		var body struct {
			Pinned   *bool `json:"pinned"`
			Featured *bool `json:"featured"`
		}
		if err := readJSON(r, &body); err != nil {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
			return
		}
		var err error
		switch action {
		case "pin":
			pinned := body.Pinned != nil && *body.Pinned
			err = h.circleService.PinPost(r.Context(), circleID, postID, pinned)
		case "feature":
			featured := body.Featured != nil && *body.Featured
			err = h.circleService.FeaturePost(r.Context(), circleID, postID, featured)
		default:
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效操作", "unknown feed action"))
			return
		}
		if err != nil {
			writeHTTPError(w, r, err)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	}
}

// --- Stats ---

func (h *CircleHandler) handleGetStats(w http.ResponseWriter, r *http.Request, circleID string) {
	if r.Method != http.MethodGet {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "only GET"))
		return
	}
	stats, err := h.circleService.GetCircleStats(r.Context(), circleID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"data": stats})
}

// --- Sections ---

func (h *CircleHandler) handleUpdateSections(w http.ResponseWriter, r *http.Request, circleID string) {
	if r.Method != http.MethodPatch {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "only PATCH"))
		return
	}
	var body struct {
		Sections []model.CircleSectionConfig `json:"sections"`
	}
	if err := readJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
		return
	}
	if err := h.circleService.UpdateSections(r.Context(), circleID, body.Sections); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *CircleHandler) handleGroups(w http.ResponseWriter, r *http.Request, circleID string, rest []string) {
	if len(rest) != 0 || r.Method != http.MethodGet {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "only GET"))
		return
	}
	q := r.URL.Query()
	limit, _ := strconv.Atoi(q.Get("limit"))
	if limit <= 0 {
		limit = 20
	}
	resp, err := h.circleService.ListGroups(r.Context(), application.ListCircleGroupsRequest{
		CircleID:      circleID,
		GroupType:     q.Get("groupType"),
		Visibility:    q.Get("visibility"),
		ParentGroupID: q.Get("parentGroupId"),
		NodeType:      q.Get("nodeType"),
		Cursor:        q.Get("cursor"),
		Limit:         limit,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

// --- Files ---

func (h *CircleHandler) handleFiles(w http.ResponseWriter, r *http.Request, circleID string, rest []string) {
	if len(rest) == 0 {
		switch r.Method {
		case http.MethodGet:
			q := r.URL.Query()
			limit, _ := strconv.Atoi(q.Get("limit"))
			if limit <= 0 {
				limit = 20
			}
			files, cursor := h.fileService.ListFiles(r.Context(), circleID, persistence.ListFilesOpts{
				ParentID: q.Get("parentId"),
				Sort:     q.Get("sort"),
				Cursor:   q.Get("cursor"),
				Limit:    limit,
			})
			if files == nil {
				files = []model.CircleFile{}
			}
			writeJSON(w, http.StatusOK, map[string]any{"items": files, "cursor": cursor})
		case http.MethodPost:
			var req application.CreateFileRequest
			if err := readJSON(r, &req); err != nil {
				writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
				return
			}
			req.CircleID = circleID
			req.UploaderID = resolveUserID(r)
			file, err := h.fileService.CreateFile(r.Context(), req)
			if err != nil {
				writeHTTPError(w, r, err)
				return
			}
			writeJSON(w, http.StatusCreated, map[string]any{"data": file})
		default:
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "method not allowed"))
		}
		return
	}

	fileID := rest[0]
	switch r.Method {
	case http.MethodGet:
		file, err := h.fileService.GetFile(r.Context(), circleID, fileID)
		if err != nil {
			writeHTTPError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"data": file})
	case http.MethodPatch:
		var req application.UpdateFileRequest
		if err := readJSON(r, &req); err != nil {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
			return
		}
		file, err := h.fileService.UpdateFile(r.Context(), circleID, fileID, req)
		if err != nil {
			writeHTTPError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"data": file})
	case http.MethodDelete:
		if err := h.fileService.DeleteFile(r.Context(), circleID, fileID); err != nil {
			writeHTTPError(w, r, err)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	default:
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "method not allowed"))
	}
}

// --- Behaviors ---

func (h *CircleHandler) handleBehaviors(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "only POST"))
		return
	}
	var report map[string]any
	if err := readJSON(r, &report); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
		return
	}
	if err := h.circleService.ReportBehavior(r.Context(), report); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// --- User circles ---

func (h *CircleHandler) handleUserCircles(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "only GET"))
		return
	}
	// /v1/users/{userId}/circles
	path := strings.TrimPrefix(r.URL.Path, "/v1/users/")
	parts := strings.Split(path, "/")
	if len(parts) < 2 || parts[1] != "circles" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "expected /v1/users/{userId}/circles"))
		return
	}
	userID := parts[0]
	q := r.URL.Query()
	limit, _ := strconv.Atoi(q.Get("limit"))
	if limit <= 0 {
		limit = 20
	}
	circles, cursor := h.circleService.ListUserCircles(r.Context(), userID, limit, q.Get("cursor"))
	if circles == nil {
		circles = []model.Circle{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": circles, "cursor": cursor})
}

// --- Helpers ---

func resolveUserID(r *http.Request) string {
	if uid := r.Header.Get("X-Client-User-Id"); uid != "" {
		return uid
	}
	return "anonymous"
}

func resolveActorSubAccountID(r *http.Request) string {
	if actorID := r.Header.Get("X-Client-Sub-Account-Id"); actorID != "" {
		return actorID
	}
	return resolveUserID(r)
}

func readJSON(r *http.Request, v any) error {
	body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil {
		return err
	}
	return json.Unmarshal(body, v)
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
