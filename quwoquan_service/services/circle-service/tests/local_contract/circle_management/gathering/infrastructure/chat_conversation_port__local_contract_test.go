package infrastructure_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

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
	conversationID, err := port.EnsureGroupConversation(
		context.Background(), "gathering-1", "贡嘎同行", "persona-owner", 8, "create-1",
	)
	if err != nil || conversationID != "conversation-1" {
		t.Fatalf("EnsureGroupConversation: id=%q err=%v", conversationID, err)
	}
	if err := port.ProjectParticipant(
		context.Background(), "gathering-1", "persona-owner", "persona/2",
		"joined", 20, "join-1",
	); err != nil {
		t.Fatalf("ProjectParticipant: %v", err)
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
