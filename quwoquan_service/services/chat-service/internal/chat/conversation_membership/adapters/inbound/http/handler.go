package http

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
	membershipmodel "quwoquan_service/services/chat-service/internal/chat/conversation_membership/domain/model"
)

type Handler struct {
	useCases *membershipapp.UseCases
}

func NewHandler(backend membershipapp.Backend) *Handler {
	return &Handler{useCases: membershipapp.NewUseCases(backend)}
}

func (handler *Handler) Register(mux *http.ServeMux) {
	if mux == nil {
		panic("conversation membership route mux is required")
	}
	mux.HandleFunc("GET /chat/conversations/{conversationId}/members", handler.listMembers)
	mux.HandleFunc("POST /chat/conversations/{conversationId}/members", handler.addMembers)
	mux.HandleFunc("DELETE /chat/conversations/{conversationId}/members/{userId}", handler.removeMember)
	mux.HandleFunc("POST /chat/conversations/{conversationId}/leave", handler.leaveConversation)
	mux.HandleFunc("POST /chat/conversations/{conversationId}/assistant", handler.inviteAssistant)
	mux.HandleFunc("DELETE /chat/conversations/{conversationId}/assistant", handler.removeAssistant)
	mux.HandleFunc("PATCH /chat/conversations/{conversationId}/owner", handler.transferOwnership)
	mux.HandleFunc("PUT /chat/conversations/{conversationId}/admins", handler.updateGroupAdmins)
	mux.HandleFunc("GET /internal/chat/conversations/{conversationId}/assistant-delivery-membership", handler.resolveAssistantDeliveryMembership)
}

func (handler *Handler) listMembers(writer http.ResponseWriter, request *http.Request) {
	limit := queryInt(request, "limit", 20)
	sortMode := membershipmodel.NormalizeListSort(request.URL.Query().Get("sort"))
	members, err := handler.useCases.List(request.Context(), membershipapp.ListMembersRequest{
		ConversationId: request.PathValue("conversationId"),
		ViewerId:       personaID(request), Cursor: request.URL.Query().Get("cursor"),
		Limit: limit + 1, Role: request.URL.Query().Get("role"),
		Query: request.URL.Query().Get("query"), Sort: string(sortMode),
	})
	if err != nil {
		writeError(writer, request, err)
		return
	}
	hasNextPage := len(members) > limit
	if hasNextPage {
		members = members[:limit]
	}
	items := make([]map[string]any, 0, len(members))
	currentPersonaID := personaID(request)
	for _, member := range members {
		items = append(items, memberToWire(member, currentPersonaID))
	}
	response := map[string]any{"items": items}
	if hasNextPage {
		last := members[len(members)-1]
		if sortMode == membershipmodel.ListSortDisplayNameAsc {
			response["nextCursor"] = membershipmodel.EncodeDisplayNameCursor(last.DisplayName, last.UserId)
		} else {
			response["nextCursor"] = membershipmodel.EncodeJoinedCursor(last.JoinedAt, last.ID)
		}
	}
	writeJSON(writer, http.StatusOK, response)
}

func (handler *Handler) addMembers(writer http.ResponseWriter, request *http.Request) {
	var body struct {
		UserIDs []string `json:"userIds"`
	}
	if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleChat, "成员请求无效", err.Error()))
		return
	}
	if err := handler.useCases.Add(request.Context(), membershipapp.AddMembersRequest{
		ConversationId: request.PathValue("conversationId"),
		UserIds:        body.UserIDs, InvitedBy: personaID(request),
	}); err != nil {
		writeError(writer, request, err)
		return
	}
	writeAck(writer)
}

func (handler *Handler) removeMember(writer http.ResponseWriter, request *http.Request) {
	if err := handler.useCases.Remove(request.Context(), membershipapp.RemoveMemberRequest{
		ConversationId: request.PathValue("conversationId"),
		UserId:         request.PathValue("userId"), OperatorId: personaID(request),
	}); err != nil {
		writeError(writer, request, err)
		return
	}
	writeAck(writer)
}

func (handler *Handler) leaveConversation(writer http.ResponseWriter, request *http.Request) {
	if err := handler.useCases.Leave(request.Context(), membershipapp.LeaveConversationRequest{
		ConversationId: request.PathValue("conversationId"), UserId: personaID(request),
	}); err != nil {
		writeError(writer, request, err)
		return
	}
	writeAck(writer)
}

func (handler *Handler) inviteAssistant(writer http.ResponseWriter, request *http.Request) {
	if err := handler.useCases.InviteAssistant(request.Context(), membershipapp.InviteAssistantRequest{
		ConversationId:     request.PathValue("conversationId"),
		InvitedBy:          personaID(request),
		InvitedByAccountID: accountID(request),
	}); err != nil {
		writeError(writer, request, err)
		return
	}
	writeAck(writer)
}

func (handler *Handler) removeAssistant(writer http.ResponseWriter, request *http.Request) {
	if err := handler.useCases.RemoveAssistant(request.Context(), membershipapp.RemoveAssistantRequest{
		ConversationId:     request.PathValue("conversationId"),
		RemovedBy:          personaID(request),
		RemovedByAccountID: accountID(request),
	}); err != nil {
		writeError(writer, request, err)
		return
	}
	writeAck(writer)
}

func (handler *Handler) transferOwnership(writer http.ResponseWriter, request *http.Request) {
	var body struct {
		NewOwnerID string `json:"newOwnerId"`
	}
	if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleChat, "群主转移请求无效", err.Error()))
		return
	}
	if err := handler.useCases.TransferOwnership(request.Context(), membershipapp.TransferOwnershipRequest{
		ConversationId: request.PathValue("conversationId"),
		OperatorId:     personaID(request), NewOwnerId: body.NewOwnerID,
	}); err != nil {
		writeError(writer, request, err)
		return
	}
	writeAck(writer)
}

func (handler *Handler) updateGroupAdmins(writer http.ResponseWriter, request *http.Request) {
	var body struct {
		AdminIDs []string `json:"adminIds"`
	}
	if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleChat, "管理员请求无效", err.Error()))
		return
	}
	if err := handler.useCases.UpdateAdmins(request.Context(), membershipapp.UpdateGroupAdminsRequest{
		ConversationId: request.PathValue("conversationId"),
		OperatorId:     personaID(request), AdminIds: body.AdminIDs,
	}); err != nil {
		writeError(writer, request, err)
		return
	}
	writeAck(writer)
}

func (handler *Handler) resolveAssistantDeliveryMembership(writer http.ResponseWriter, request *http.Request) {
	view, err := handler.useCases.ResolveAssistantDeliveryMembership(
		request.Context(), request.PathValue("conversationId"),
		request.URL.Query().Get("creatorPersonaId"),
		request.URL.Query().Get("assistantMemberId"),
	)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	writeJSON(writer, http.StatusOK, view)
}

func memberToWire(member membershipmodel.Member, currentPersonaID string) map[string]any {
	return map[string]any{
		"userId": member.UserId, "userHandle": strings.TrimSpace(member.UserHandle),
		"displayName": member.DisplayName, "avatarUrl": member.AvatarUrl,
		"role": member.Role, "memberType": member.MemberType,
		"joinedAt":      member.JoinedAt,
		"isCurrentUser": member.UserId == currentPersonaID,
	}
}

func personaID(request *http.Request) string {
	if principal, ok := rtauth.PrincipalFromContext(request.Context()); ok {
		return strings.TrimSpace(principal.Actor.PersonaID)
	}
	return strings.TrimSpace(request.Header.Get("X-Client-Persona-Id"))
}

func accountID(request *http.Request) string {
	if principal, ok := rtauth.PrincipalFromContext(request.Context()); ok {
		return strings.TrimSpace(principal.Actor.AccountID)
	}
	return strings.TrimSpace(request.Header.Get("X-Client-Account-Id"))
}

func queryInt(request *http.Request, key string, fallback int) int {
	value, err := strconv.Atoi(request.URL.Query().Get(key))
	if err != nil {
		return fallback
	}
	return value
}

func writeAck(writer http.ResponseWriter) {
	writeJSON(writer, http.StatusOK, map[string]any{"status": "ok"})
}

func writeJSON(writer http.ResponseWriter, statusCode int, value any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(statusCode)
	_ = json.NewEncoder(writer).Encode(value)
}

func writeError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
