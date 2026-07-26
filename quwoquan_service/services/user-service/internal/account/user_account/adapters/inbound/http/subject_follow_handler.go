package http

import (
	"net/http"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/user-service/generated/account/user_account"
	followingapp "quwoquan_service/services/user-service/internal/profile_projection/following_subject/application"
	visitapp "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/application"
	subjectfollowapp "quwoquan_service/services/user-service/internal/relationship/subject_follow/application"
)

// registerSubjectFollowRoutes 注册 SubjectFollow / FollowedSubjectVisitState /
// FollowingSubject 三个对象的路由；path 与 metadata operations.yaml 同源。
func (h *UserHandler) registerSubjectFollowRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /relationships/subjects/{subjectType}/{subjectId}/follow", h.handleFollowSubject)
	mux.HandleFunc("DELETE /relationships/subjects/{subjectType}/{subjectId}/follow", h.handleUnfollowSubject)
	// {subjectAction} 匹配 "{subjectId}:mark-visited" 整段（ServeMux 通配符
	// 不支持段内混排），handler 内解析动作后缀。
	mux.HandleFunc("POST /user/followed-subjects/{subjectType}/{subjectAction}", h.handleMarkFollowedSubjectVisited)
	mux.HandleFunc("GET /user/following-subjects", h.handleListFollowingSubjects)
}

func (h *UserHandler) commandIdempotencyKey(r *http.Request) string {
	if invocation, ok := operation.FromContext(r.Context()); ok {
		if key := strings.TrimSpace(invocation.IdempotencyKey); key != "" {
			return key
		}
	}
	return strings.TrimSpace(r.Header.Get("Idempotency-Key"))
}

func (h *UserHandler) handleFollowSubject(w http.ResponseWriter, r *http.Request) {
	h.executeSubjectFollow(w, r, true)
}

func (h *UserHandler) handleUnfollowSubject(w http.ResponseWriter, r *http.Request) {
	h.executeSubjectFollow(w, r, false)
}

func (h *UserHandler) executeSubjectFollow(w http.ResponseWriter, r *http.Request, follow bool) {
	if h.subjectFollow == nil {
		writeHTTPError(w, r, generated.AppErrorFromInternalError("subject follow service is unavailable"))
		return
	}
	personaID, err := h.resolveActorSubAccountID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	idempotencyKey := h.commandIdempotencyKey(r)
	if idempotencyKey == "" {
		writeInvalidArg(w, r, "Idempotency-Key is required")
		return
	}
	body := readOptionalBody(r)
	command := subjectfollowapp.FollowSubjectCommand{
		PersonaID:      personaID,
		SubjectType:    r.PathValue("subjectType"),
		SubjectID:      r.PathValue("subjectId"),
		Source:         anyString(body["source"]),
		IdempotencyKey: idempotencyKey,
	}
	execute := h.subjectFollow.Follow
	if !follow {
		execute = h.subjectFollow.Unfollow
	}
	result, err := execute(r.Context(), command)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"personaId":        result.Follow.PersonaID,
		"subjectType":      result.Follow.SubjectType,
		"subjectId":        result.Follow.SubjectID,
		"state":            result.Follow.State,
		"idempotentReplay": result.IdempotentReplay,
		"updatedAt":        result.Follow.UpdatedAt.UTC().Format(time.RFC3339),
	})
}

func (h *UserHandler) handleMarkFollowedSubjectVisited(w http.ResponseWriter, r *http.Request) {
	if h.followedSubjectVisit == nil {
		writeHTTPError(w, r, generated.AppErrorFromInternalError("followed subject visit service is unavailable"))
		return
	}
	action := r.PathValue("subjectAction")
	subjectID, suffixOK := strings.CutSuffix(action, ":mark-visited")
	if !suffixOK || strings.TrimSpace(subjectID) == "" {
		writeInvalidArg(w, r, "path must be {subjectId}:mark-visited")
		return
	}
	personaID, err := h.resolveActorSubAccountID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	body := readOptionalBody(r)
	visitedAt := time.Now().UTC()
	if raw := strings.TrimSpace(anyString(body["visitedAt"])); raw != "" {
		if parsed, parseErr := time.Parse(time.RFC3339, raw); parseErr == nil {
			visitedAt = parsed
		}
	}
	clientRequestID := strings.TrimSpace(anyString(body["clientRequestId"]))
	if clientRequestID == "" {
		clientRequestID = h.commandIdempotencyKey(r)
	}
	result, err := h.followedSubjectVisit.MarkVisited(r.Context(), visitapp.MarkVisitedInput{
		PersonaID:       personaID,
		SubjectType:     r.PathValue("subjectType"),
		SubjectID:       subjectID,
		VisitedAt:       visitedAt,
		ClientRequestID: clientRequestID,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"subjectId":        result.SubjectID,
		"subjectType":      result.SubjectType,
		"lastVisitedAt":    result.LastVisitedAt.UTC().Format(time.RFC3339),
		"hasUnreadChanges": result.HasUnreadChanges,
	})
}

func (h *UserHandler) handleListFollowingSubjects(w http.ResponseWriter, r *http.Request) {
	if h.followingSubjects == nil {
		writeHTTPError(w, r, generated.AppErrorFromInternalError("following subject query service is unavailable"))
		return
	}
	personaID, err := h.resolveActorSubAccountID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	items, err := h.followingSubjects.ListFollowingSubjects(
		r.Context(),
		personaID,
		strings.TrimSpace(r.URL.Query().Get("subjectType")),
		parseLimit(r, 20),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if items == nil {
		items = []followingapp.FollowingSubjectItem{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}
