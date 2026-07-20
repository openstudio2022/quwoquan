package notificationclient

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	serviceclients "quwoquan_service/generated/serviceclients"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/application"
)

type fixedCredentials string

func (c fixedCredentials) AuthorizationHeader(context.Context) (string, error) {
	return "Bearer " + string(c), nil
}

func TestClientSendsTypedIdempotentNotificationCommand(t *testing.T) {
	var received createAppMessageRequest
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != serviceclients.NotificationCreateAppMessagePath {
			http.NotFound(w, r)
			return
		}
		if r.Header.Get("Authorization") != "Bearer service-token" ||
			r.Header.Get("Idempotency-Key") != "assistant:turn:turn-1" {
			http.Error(w, "missing service authorization or idempotency", http.StatusUnauthorized)
			return
		}
		decoder := json.NewDecoder(r.Body)
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&received); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(appMessageResponse{
			MessageID:   "notification-1",
			UserID:      received.UserID,
			MessageType: received.MessageType,
			Source:      received.Source,
			SourceID:    received.SourceID,
			Destination: appMessageDestinationResponse(received.Destination),
			Title:       received.Title,
			Summary:     received.Summary,
			Target: appMessageTargetResponse{
				TargetType: received.Target.TargetType,
				TargetID:   received.Target.TargetID,
				RouteID:    received.Target.RouteID,
				RoutePath:  received.Target.RoutePath,
				Query:      appMessageRouteQueryResponse(received.Target.Query),
			},
			CreatedAt: "2026-07-13T10:00:00Z",
		})
	}))
	t.Cleanup(server.Close)

	client, err := NewClient(server.Client(), server.URL, fixedCredentials("service-token"))
	if err != nil {
		t.Fatalf("construct notification client: %v", err)
	}
	receipt, err := client.CreateAppMessage(context.Background(), application.NotificationAppMessageCommand{
		IdempotencyKey: "assistant:turn:turn-1",
		UserID:         "user-1",
		MessageType:    "assistant",
		Source:         "assistant_turn",
		SourceID:       "turn-1",
		Destination:    application.NotificationAppMessageDestination{Type: "user", ID: "user-1"},
		Title:          "小趣提醒",
		Summary:        "你关注的主题有新进展。",
		Target: application.NotificationAppMessageTarget{
			TargetType: "assistant_turn",
			TargetID:   "turn-1",
		},
		Provenance: application.NotificationAppMessageProvenance{
			Personalized:    true,
			InterestTags:    []string{"travel"},
			MatchedSegments: []string{"travel_enthusiast"},
			LifecycleStage:  "active",
		},
	})
	if err != nil {
		t.Fatalf("create notification app message: %v", err)
	}
	if receipt.MessageID != "notification-1" || !received.Provenance.Personalized ||
		received.Provenance.LifecycleStage != "active" {
		t.Fatalf("typed command or receipt drifted: receipt=%+v request=%+v", receipt, received)
	}
}

func TestClientRejectsUnknownSuccessField(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusCreated)
		_, _ = w.Write([]byte(`{"messageId":"notification-1","unknown":true}`))
	}))
	t.Cleanup(server.Close)
	client, err := NewClient(server.Client(), server.URL, fixedCredentials("service-token"))
	if err != nil {
		t.Fatalf("construct notification client: %v", err)
	}
	_, err = client.CreateAppMessage(context.Background(), application.NotificationAppMessageCommand{})
	if err == nil {
		t.Fatal("unknown notification success field must fail strict decoding")
	}
}

func TestClientPreservesRuntimeFailureIdentity(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rterr.WriteHTTPError(
			w,
			rterr.NewAppError(
				rterr.NewCode(rterr.ModuleNotification, rterr.KindUser, "idempotency_conflict"),
				"请求与已提交消息不一致",
				"idempotency payload mismatch",
			).WithRecovery("surface", 0),
			rterr.HTTPWriteOptionsFromRequest(r),
		)
	}))
	t.Cleanup(server.Close)
	client, err := NewClient(server.Client(), server.URL, fixedCredentials("service-token"))
	if err != nil {
		t.Fatalf("construct notification client: %v", err)
	}
	_, err = client.CreateAppMessage(context.Background(), application.NotificationAppMessageCommand{})
	appErr, ok := err.(*rterr.AppError)
	if !ok || appErr.Code.String() != "NOTIFICATION.USER.idempotency_conflict" {
		t.Fatalf("runtime failure identity was not preserved: %T %v", err, err)
	}
}
