package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/circle-service/internal/application"
	behaviorfactapp "quwoquan_service/services/circle-service/internal/application/circle/circle_behavior_fact"
	fileapp "quwoquan_service/services/circle-service/internal/application/circle/circle_file"
	groupapp "quwoquan_service/services/circle-service/internal/application/circle/circle_group"
	groupmembershipapp "quwoquan_service/services/circle-service/internal/application/circle/circle_group_membership"
	membershipapp "quwoquan_service/services/circle-service/internal/application/circle/circle_membership"
	placementapp "quwoquan_service/services/circle-service/internal/application/circle/circle_post_placement"
	behaviorfactmodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_behavior_fact/model"
	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
)

// CircleHandler adapts circle application services to HTTP.
type CircleHandler struct {
	circleService           *application.CircleService
	fileCommands            *fileapp.CommandFacade
	fileQueries             *fileapp.QueryFacade
	behaviorFacts           *behaviorfactapp.Writer
	groupCommands           *groupapp.CommandFacade
	groupQueries            *groupapp.QueryFacade
	groupMembershipCommands *groupmembershipapp.CommandFacade
	groupMembershipQueries  *groupmembershipapp.QueryFacade
	membershipCommands      *membershipapp.CommandFacade
	membershipQueries       *membershipapp.QueryFacade
	placementCommands       *placementapp.CommandFacade
}

func NewCircleHandler(
	cs *application.CircleService,
	fileCommands *fileapp.CommandFacade,
	fileQueries *fileapp.QueryFacade,
	behaviorFacts *behaviorfactapp.Writer,
	groupCommands *groupapp.CommandFacade,
	groupQueries *groupapp.QueryFacade,
	groupMembershipCommands *groupmembershipapp.CommandFacade,
	groupMembershipQueries *groupmembershipapp.QueryFacade,
	membershipCommands *membershipapp.CommandFacade,
	membershipQueries *membershipapp.QueryFacade,
	placements *placementapp.CommandFacade,
) *CircleHandler {
	if cs == nil || fileCommands == nil || fileQueries == nil || behaviorFacts == nil || groupCommands == nil || groupQueries == nil || groupMembershipCommands == nil || groupMembershipQueries == nil || membershipCommands == nil || membershipQueries == nil || placements == nil {
		panic("CircleHandler requires all object facades")
	}
	return &CircleHandler{
		circleService: cs, fileCommands: fileCommands, fileQueries: fileQueries, behaviorFacts: behaviorFacts,
		groupCommands: groupCommands, groupQueries: groupQueries,
		groupMembershipCommands: groupMembershipCommands, groupMembershipQueries: groupMembershipQueries,
		membershipCommands: membershipCommands, membershipQueries: membershipQueries,
		placementCommands: placements,
	}
}

func (h *CircleHandler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", h.handleHealthz)

	// Circles CRUD
	mux.HandleFunc("/circles", h.handleCircles)
	mux.HandleFunc("GET /circles/search", h.handleSearchCircles)
	mux.HandleFunc("/circles/behaviors", h.handleBehaviors)
	mux.HandleFunc("/circles/", h.handleCircleSubRoutes)

	// Persona membership projection
	mux.HandleFunc("/personas/", h.handlePersonaCircles)

	return mux
}

func (h *CircleHandler) handleHealthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

// --- /circles ---

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

// --- /circles/{circleId}/... ---

func (h *CircleHandler) handleCircleSubRoutes(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/circles/")
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
	case "memberships":
		h.handleMemberships(w, r, circleID, parts[2:])
	case "groups":
		h.handleGroups(w, r, circleID, parts[2:])
	case "feed":
		h.handleFeed(w, r, circleID, parts[2:])
	case "stats":
		h.handleGetStats(w, r, circleID)
	case "impact":
		h.handleGetImpact(w, r, circleID)
	case "sections":
		h.handleUpdateSections(w, r, circleID)
	case "files":
		h.handleFiles(w, r, circleID, parts[2:])
	case "post-placements":
		h.handlePostPlacements(w, r, circleID, parts[2:])
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

	// /circles/{circleId}/feed/{postId}/pin or /feature
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

func (h *CircleHandler) handleGetImpact(w http.ResponseWriter, r *http.Request, circleID string) {
	if r.Method != http.MethodGet {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "only GET"))
		return
	}
	impact, err := h.circleService.GetCircleImpact(r.Context(), circleID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"data": impact})
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

// --- Behaviors ---

func (h *CircleHandler) handleBehaviors(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "only POST"))
		return
	}
	var request struct {
		CircleID  string `json:"circleId"`
		EventType string `json:"eventType"`
	}
	if err := readStrictJSON(r, &request); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
		return
	}
	if _, err := h.behaviorFacts.Append(r.Context(), behaviorfactapp.AppendCommand{
		CircleID: request.CircleID, EventType: behaviorfactmodel.BehaviorEventType(request.EventType),
	}); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// --- Helpers ---

func resolveUserID(r *http.Request) string {
	if uid := r.Header.Get("X-Client-User-Id"); uid != "" {
		return uid
	}
	return "anonymous"
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
