// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
// readiness_case: add-members-api
// readiness_case: remove-member-api
// readiness_case: leave-conversation-api
// readiness_case: resolve-assistant-delivery-membership-api
// readiness_case: invite-assistant-api
// readiness_case: remove-assistant-api
// readiness_case: transfer-ownership-api
// readiness_case: update-group-admins-api
// readiness_case: list-members-api
package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	membershiphttp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/adapters/inbound/http"
	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
	membershipmodel "quwoquan_service/services/chat-service/internal/chat/conversation_membership/domain/model"
)

type membershipBackend struct {
	added membershipapp.AddMembersRequest
	calls map[string]int
}

func (backend *membershipBackend) record(name string) {
	if backend.calls == nil {
		backend.calls = map[string]int{}
	}
	backend.calls[name]++
}

func (backend *membershipBackend) ListMembers(context.Context, membershipapp.ListMembersRequest) ([]membershipmodel.Member, error) {
	backend.record("ListMembers")
	return []membershipmodel.Member{}, nil
}
func (backend *membershipBackend) ResolveAssistantDeliveryMembership(context.Context, string, string, string) (membershipapp.AssistantDeliveryMembershipView, error) {
	backend.record("ResolveAssistantDeliveryMembership")
	return membershipapp.AssistantDeliveryMembershipView{CreatorMember: true, AssistantMember: true}, nil
}
func (backend *membershipBackend) AddMembers(_ context.Context, request membershipapp.AddMembersRequest) error {
	backend.record("AddMembers")
	backend.added = request
	return nil
}
func (backend *membershipBackend) RemoveMember(context.Context, membershipapp.RemoveMemberRequest) error {
	backend.record("RemoveMember")
	return nil
}
func (backend *membershipBackend) LeaveConversation(context.Context, membershipapp.LeaveConversationRequest) error {
	backend.record("LeaveConversation")
	return nil
}
func (backend *membershipBackend) InviteAssistant(context.Context, membershipapp.InviteAssistantRequest) error {
	backend.record("InviteAssistant")
	return nil
}
func (backend *membershipBackend) RemoveAssistant(context.Context, membershipapp.RemoveAssistantRequest) error {
	backend.record("RemoveAssistant")
	return nil
}
func (backend *membershipBackend) TransferOwnership(context.Context, membershipapp.TransferOwnershipRequest) error {
	backend.record("TransferOwnership")
	return nil
}
func (backend *membershipBackend) UpdateGroupAdmins(context.Context, membershipapp.UpdateGroupAdminsRequest) error {
	backend.record("UpdateGroupAdmins")
	return nil
}

func TestConversationMembershipHTTPExecutesEveryCanonicalOperation(t *testing.T) {
	backend := &membershipBackend{calls: map[string]int{}}
	routes := http.NewServeMux()
	membershiphttp.NewHandler(backend).Register(routes)
	principal := rtauth.Principal{Actor: operation.ActorContext{AccountID: "account-owner", PersonaID: "persona-owner"}}
	cases := []struct{ method, path, body string }{
		{http.MethodGet, "/chat/conversations/conversation-1/members?limit=20", ""},
		{http.MethodPost, "/chat/conversations/conversation-1/members", `{"userIds":["persona-2"]}`},
		{http.MethodDelete, "/chat/conversations/conversation-1/members/persona-2", ""},
		{http.MethodPost, "/chat/conversations/conversation-1/leave", ""},
		{http.MethodPost, "/chat/conversations/conversation-1/assistant", ""},
		{http.MethodDelete, "/chat/conversations/conversation-1/assistant", ""},
		{http.MethodPatch, "/chat/conversations/conversation-1/owner", `{"newOwnerId":"persona-2"}`},
		{http.MethodPut, "/chat/conversations/conversation-1/admins", `{"adminIds":["persona-2"]}`},
		{http.MethodGet, "/internal/chat/conversations/conversation-1/assistant-delivery-membership?creatorPersonaId=persona-owner", ""},
	}
	for _, item := range cases {
		request := httptest.NewRequest(item.method, item.path, strings.NewReader(item.body))
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
		response := httptest.NewRecorder()
		routes.ServeHTTP(response, request)
		if response.Code != http.StatusOK {
			t.Fatalf("%s %s status=%d body=%s", item.method, item.path, response.Code, response.Body.String())
		}
	}
	for _, name := range []string{"ListMembers", "AddMembers", "RemoveMember", "LeaveConversation", "InviteAssistant", "RemoveAssistant", "TransferOwnership", "UpdateGroupAdmins", "ResolveAssistantDeliveryMembership"} {
		if backend.calls[name] != 1 {
			t.Fatalf("%s calls=%d want=1", name, backend.calls[name])
		}
	}
}

func TestConversationMembershipHTTPUsesObjectLocalRouteAndTrustedPersona(t *testing.T) {
	backend := &membershipBackend{}
	routes := http.NewServeMux()
	membershiphttp.NewHandler(backend).Register(routes)
	routes.HandleFunc("/", func(writer http.ResponseWriter, _ *http.Request) {
		http.Error(writer, "fallback", http.StatusTeapot)
	})
	request := httptest.NewRequest(
		http.MethodPost,
		"/chat/conversations/conversation-1/members",
		strings.NewReader(`{"userIds":["persona-2"]}`),
	)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{PersonaID: "trusted-persona"},
	}))
	response := httptest.NewRecorder()
	routes.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if backend.added.ConversationId != "conversation-1" ||
		backend.added.InvitedBy != "trusted-persona" ||
		len(backend.added.UserIds) != 1 || backend.added.UserIds[0] != "persona-2" {
		t.Fatalf("typed membership command drifted: %+v", backend.added)
	}
}
