// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
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
}

func (*membershipBackend) ListMembers(context.Context, membershipapp.ListMembersRequest) ([]membershipmodel.Member, error) {
	return []membershipmodel.Member{}, nil
}
func (*membershipBackend) ResolveAssistantDeliveryMembership(context.Context, string, string, string) (membershipapp.AssistantDeliveryMembershipView, error) {
	return membershipapp.AssistantDeliveryMembershipView{}, nil
}
func (backend *membershipBackend) AddMembers(_ context.Context, request membershipapp.AddMembersRequest) error {
	backend.added = request
	return nil
}
func (*membershipBackend) RemoveMember(context.Context, membershipapp.RemoveMemberRequest) error {
	return nil
}
func (*membershipBackend) LeaveConversation(context.Context, membershipapp.LeaveConversationRequest) error {
	return nil
}
func (*membershipBackend) InviteAssistant(context.Context, membershipapp.InviteAssistantRequest) error {
	return nil
}
func (*membershipBackend) RemoveAssistant(context.Context, membershipapp.RemoveAssistantRequest) error {
	return nil
}
func (*membershipBackend) TransferOwnership(context.Context, membershipapp.TransferOwnershipRequest) error {
	return nil
}
func (*membershipBackend) UpdateGroupAdmins(context.Context, membershipapp.UpdateGroupAdminsRequest) error {
	return nil
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
