package http

import (
	"encoding/json"
	"log/slog"
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
	circleCommands          *application.CircleCommandFacade
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
	circleCommands *application.CircleCommandFacade,
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
	if cs == nil || circleCommands == nil || fileCommands == nil || fileQueries == nil || behaviorFacts == nil || groupCommands == nil || groupQueries == nil || groupMembershipCommands == nil || groupMembershipQueries == nil || membershipCommands == nil || membershipQueries == nil || placements == nil {
		panic("CircleHandler requires all object facades")
	}
	return &CircleHandler{
		circleService: cs, circleCommands: circleCommands,
		fileCommands: fileCommands, fileQueries: fileQueries, behaviorFacts: behaviorFacts,
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
	mux.HandleFunc("GET /circles/discovery-feed", h.handleCircleDiscoveryFeed)
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
	limit, err := parsePageLimit(q.Get("limit"))
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "分页参数无效", err.Error()))
		return
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
	limit, err := parsePageLimit(q.Get("limit"))
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "分页参数无效", err.Error()))
		return
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

func (h *CircleHandler) handleCircleDiscoveryFeed(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	limit, err := parsePageLimit(q.Get("limit"))
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "分页参数无效", err.Error()))
		return
	}
	result, err := h.circleService.ListCircleDiscoveryFeed(r.Context(), application.CircleDiscoveryFeedQuery{
		Category: q.Get("category"), SubCategory: q.Get("subCategory"),
		Scope: application.CircleDiscoveryFeedScope(q.Get("scope")),
		Sort:  q.Get("sort"), Cursor: q.Get("cursor"), Limit: limit,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *CircleHandler) handleCreateCircle(w http.ResponseWriter, r *http.Request) {
	var command application.CreateCircleCommand
	if err := readStrictJSON(r, &command); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
		return
	}
	result, err := h.circleCommands.Create(r.Context(), command)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, result)
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
	var command application.UpdateCircleCommand
	if err := readStrictJSON(r, &command); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
		return
	}
	command.CircleID = circleID
	result, err := h.circleCommands.Update(r.Context(), command)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *CircleHandler) handleArchiveCircle(w http.ResponseWriter, r *http.Request, circleID string) {
	result, err := h.circleCommands.Archive(r.Context(), circleID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

// --- Feed ---

// 展示位（pin/feature）唯一写入口是 CirclePostPlacement 命令
// （/circles/{circleId}/post-placements/{placementId}/pin|feature），
// feed 路由只保留只读投影。
func (h *CircleHandler) handleFeed(w http.ResponseWriter, r *http.Request, circleID string, rest []string) {
	if len(rest) != 0 || r.Method != http.MethodGet {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "only GET /circles/{circleId}/feed"))
		return
	}
	q := r.URL.Query()
	limit, err := parsePageLimit(q.Get("limit"))
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "分页参数无效", err.Error()))
		return
	}
	result, err := h.circleService.GetCircleFeed(
		r.Context(), circleID, limit, q.Get("cursor"), q.Get("sort"),
		q.Get("identity"), q.Get("type"),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
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
	writeJSON(w, http.StatusOK, map[string]any{"data": statsWirePayload(stats)})
}

// statsWirePayload 保持既有 wire 键集合（documented keys 见
// projections/circle_stats_wire.yaml）。
func statsWirePayload(stats application.CircleStatsWire) map[string]any {
	return map[string]any{
		"totalMembers":      stats.TotalMembers,
		"weeklyActive":      stats.WeeklyActive,
		"totalPosts":        stats.TotalPosts,
		"totalDiscussions":  stats.TotalDiscussions,
		"storageUsedBytes":  stats.StorageUsedBytes,
		"storageQuotaBytes": stats.StorageQuotaBytes,
	}
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
	if err := readStrictJSON(r, &body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
		return
	}
	result, err := h.circleCommands.UpdateSections(r.Context(), application.UpdateCircleSectionsCommand{
		CircleID: circleID, Sections: body.Sections,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
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

func parsePageLimit(raw string) (int, error) {
	if strings.TrimSpace(raw) == "" {
		return 20, nil
	}
	limit, err := strconv.Atoi(raw)
	if err != nil {
		return 0, err
	}
	if limit <= 0 {
		return 20, nil
	}
	return limit, nil
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(v); err != nil {
		slog.Default().Warn("circle response encode failed", "error", err)
	}
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
