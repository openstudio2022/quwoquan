package http

import (
	"net/http"

	rterr "quwoquan_service/runtime/errors"
	conversationtransport "quwoquan_service/services/chat-service/generated/chat/conversation/transport"
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
	case "ListContacts":
		h.handleListContacts(w, r)
	case "ListGroupCandidates":
		h.handleListGroupCandidates(w, r)
	case "ListSelectableGroupConversations":
		h.handleListSelectableGroupConversations(w, r)
	case "ListSelectableGroupContactMembers":
		h.handleListSelectableGroupContactMembers(w, r)
	case "ProjectGatheringConversation":
		h.handleProjectGatheringConversation(w, r)
	default:
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleChat, "接口不存在", "operation not found"))
	}
}

func resolveGeneratedOperation(method, path string) (string, bool) {
	resolvers := []func(string, string) (string, bool){conversationtransport.ResolveOperation}
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
