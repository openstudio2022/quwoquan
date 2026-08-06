package infrastructure_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
	external "quwoquan_service/services/circle-service/internal/circle_management/gathering/infrastructure/external"
)

type serviceCredentialStub struct{}

func (serviceCredentialStub) AuthorizationHeader(context.Context) (string, error) {
	return "Bearer service-token", nil
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-001
func TestChatConversationPortUsesOnlyGatheringProjectionOperations(t *testing.T) {
	requests := make([]string, 0, 2)
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodPut || request.Header.Get("Authorization") != "Bearer service-token" ||
			request.Header.Get("Idempotency-Key") == "" {
			t.Fatalf("untrusted Chat projection request: method=%s auth=%q idempotency=%q", request.Method, request.Header.Get("Authorization"), request.Header.Get("Idempotency-Key"))
		}
		requests = append(requests, request.URL.EscapedPath())
		writer.Header().Set("Content-Type", "application/json")
		if len(requests) == 1 {
			_ = json.NewEncoder(writer).Encode(map[string]any{
				"gatheringId": "gathering-1", "conversationId": "conversation-1",
			})
			return
		}
		_ = json.NewEncoder(writer).Encode(map[string]any{
			"gatheringId": "gathering-1", "conversationId": "conversation-1",
			"personaId": "persona/2", "state": "joined",
		})
	}))
	t.Cleanup(server.Close)
	port, err := external.NewChatConversationPort(server.URL, serviceCredentialStub{}, server.Client())
	if err != nil {
		t.Fatal(err)
	}
	conversationID, err := port.EnsureGatheringConversation(
		context.Background(),
		ports.EnsureGatheringConversationCommand{
			GatheringID: "gathering-1", SourceEventID: "create-1",
			SourceVersion: 8, OwnerPersonaID: "persona-owner",
			Title: "贡嘎同行", AccessMode: "active", PostingPolicy: "member_chat",
		},
	)
	if err != nil || conversationID != "conversation-1" {
		t.Fatalf("EnsureGatheringConversation: id=%q err=%v", conversationID, err)
	}
	if err := port.ProjectGatheringMembership(
		context.Background(),
		ports.ProjectGatheringMembershipCommand{
			GatheringID: "gathering-1", PersonaID: "persona/2",
			SourceEventID: "join-1", SourceVersion: 20,
			SourceType: "participation", State: "active",
		},
	); err != nil {
		t.Fatalf("ProjectGatheringMembership: %v", err)
	}
	want := []string{
		"/internal/chat/gathering-conversations/gathering-1",
		"/internal/chat/gathering-conversations/gathering-1/members/persona%2F2",
	}
	for index := range want {
		if requests[index] != want[index] {
			t.Fatalf("request[%d]=%q want %q", index, requests[index], want[index])
		}
	}
}
