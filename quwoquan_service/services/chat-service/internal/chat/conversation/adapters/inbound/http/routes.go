package http

import (
	"net/http"

	rterr "quwoquan_service/runtime/errors"
	conversationtransport "quwoquan_service/services/chat-service/generated/chat/conversation/transport"
	membershiptransport "quwoquan_service/services/chat-service/generated/chat/conversation_membership/transport"
	statetransport "quwoquan_service/services/chat-service/generated/chat/conversation_user_state/transport"
	messagetransport "quwoquan_service/services/chat-service/generated/chat/message/transport"
)

func RegisterGeneratedRoutes(mux *http.ServeMux, h *ChatHandler) {
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		op, ok := resolveGeneratedOperation(r.Method, r.URL.Path)
		if !ok {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "接口不存在", "route not found"))
			return
		}
		dispatchGeneratedOperation(h, op, w, r)
	})
}

func dispatchGeneratedOperation(h *ChatHandler, operation string, w http.ResponseWriter, r *http.Request) {
	switch operation {
	case "ListConversations":
		h.handleListConversations(w, r)
	case "CreateConversation":
		h.handleCreateConversation(w, r)
	case "GetConversation":
		h.handleGetConversation(w, r)
	case "UpdateAnnouncement":
		h.handleUpdateAnnouncement(w, r)
	case "UpdateGroupGovernanceSettings":
		h.handleUpdateGroupGovernanceSettings(w, r)
	case "GetReceipts":
		h.handleGetReceipts(w, r)
	case "ListInbox":
		h.handleListInbox(w, r)
	case "ListContacts":
		h.handleListContacts(w, r)
	case "ListGroupCandidates":
		h.handleListGroupCandidates(w, r)
	case "ListSelectableGroupConversations":
		h.handleListSelectableGroupConversations(w, r)
	case "ListSelectableGroupContactMembers":
		h.handleListSelectableGroupContactMembers(w, r)
	case "SendMessage":
		h.handleSendMessage(w, r)
	case "RecallMessage":
		h.handleRecallMessage(w, r)
	case "ListMessages":
		h.handleListMessages(w, r)
	case "ListAssistantGroundingMessages":
		h.handleListAssistantGroundingMessages(w, r)
	case "SendAssistantDeliveryMessage":
		h.handleSendAssistantDeliveryMessage(w, r)
	case "SyncMessages":
		h.handleSyncMessages(w, r)
	case "AddMembers":
		h.handleAddMembers(w, r)
	case "RemoveMember":
		h.handleRemoveMember(w, r)
	case "LeaveConversation":
		h.handleLeaveConversation(w, r)
	case "InviteAssistant":
		h.handleInviteAssistant(w, r)
	case "RemoveAssistant":
		h.handleRemoveAssistant(w, r)
	case "TransferOwnership":
		h.handleTransferOwnership(w, r)
	case "UpdateGroupAdmins":
		h.handleUpdateGroupAdmins(w, r)
	case "ListMembers":
		h.handleListMembers(w, r)
	case "ResolveAssistantDeliveryMembership":
		h.handleResolveAssistantDeliveryMembership(w, r)
	case "MarkAsRead":
		h.handleMarkAsRead(w, r)
	case "UpdateConversationSettings":
		h.handleUpdateConversationSettings(w, r)
	default:
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "接口不存在", "operation not found"))
	}
}

func resolveGeneratedOperation(method, path string) (string, bool) {
	resolvers := []func(string, string) (string, bool){
		conversationtransport.ResolveOperation,
		membershiptransport.ResolveOperation,
		statetransport.ResolveOperation,
		messagetransport.ResolveOperation,
	}
	for _, resolve := range resolvers {
		if operation, ok := resolve(method, path); ok {
			return operation, true
		}
	}
	return "", false
}

func extractPathParam(path, template, paramName string) string {
	return conversationtransport.ExtractPathParam(path, template, paramName)
}
