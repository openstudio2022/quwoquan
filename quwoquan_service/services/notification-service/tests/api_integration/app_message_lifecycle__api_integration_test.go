package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	httpadapter "quwoquan_service/services/notification-service/internal/adapters/http"
	"quwoquan_service/services/notification-service/internal/application"
)

func TestAppMessageLifecycleUsesNotificationAggregateAndTransactionalOutbox(t *testing.T) {
	resetNotificationCollections(t)
	commands, err := application.NewAppMessageCommandFacade(
		notificationAppMessageStore,
		notificationAppMessageStore,
		notificationReliableStore,
	)
	if err != nil {
		t.Fatalf("construct command facade: %v", err)
	}
	queries, err := application.NewAppMessageQueryFacade(
		notificationAppMessageStore,
		notificationAppMessageStore,
		notificationAppMessageStore,
	)
	if err != nil {
		t.Fatalf("construct query facade: %v", err)
	}
	deliveryQueries, err := application.NewNotificationDeliveryJobQueryFacade(
		notificationReliableStore,
		notificationReliableStore,
	)
	if err != nil {
		t.Fatalf("construct delivery query facade: %v", err)
	}
	deliveryCommands, err := application.NewNotificationDeliveryJobCommandFacade(
		notificationReliableStore,
	)
	if err != nil {
		t.Fatalf("construct delivery command facade: %v", err)
	}
	httpHandler, err := httpadapter.NewHandler(httpadapter.HandlerDependencies{
		AppMessageCommands: commands,
		AppMessageQueries:  queries,
		DeliveryCommands:   deliveryCommands,
		DeliveryQueries:    deliveryQueries,
	})
	if err != nil {
		t.Fatalf("construct notification handler: %v", err)
	}
	handler := httpHandler.Routes()

	payload := []byte(`{
  "userId":"account_001",
  "messageType":"assistant",
  "source":"assistant_turn",
  "sourceId":"turn_001",
  "destination":{"type":"user","id":"account_001"},
  "title":"小趣提醒",
  "summary":"你关注的主题有新进展。",
  "target":{"targetType":"assistant_turn","targetId":"turn_001","routeId":"personalAssistantDialog","routePath":"/assistant","query":{"dimension":"content"}},
  "provenance":{"personalized":true,"interestTags":["travel"],"matchedSegments":["travel_enthusiast"],"lifecycleStage":"active"}
}`)
	created := requestAppMessage(t, handler, http.MethodPost, "/internal/app-messages", "account_001", "idem-app-message-001", payload)
	if created.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", created.Code, created.Body.String())
	}
	createdBody := decodeResponse(t, created)
	messageID := stringValue(createdBody["messageId"])
	if messageID == "" {
		t.Fatalf("create response missing messageId: %#v", createdBody)
	}

	replayed := requestAppMessage(t, handler, http.MethodPost, "/internal/app-messages", "account_001", "idem-app-message-001", payload)
	if replayed.Code != http.StatusCreated {
		t.Fatalf("replay status=%d body=%s", replayed.Code, replayed.Body.String())
	}
	if got := stringValue(decodeResponse(t, replayed)["messageId"]); got != messageID {
		t.Fatalf("idempotent replay messageId=%q want %q", got, messageID)
	}

	list := requestAppMessage(t, handler, http.MethodGet, "/app-messages?limit=20", "account_001", "", nil)
	if list.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", list.Code, list.Body.String())
	}
	items, ok := decodeResponse(t, list)["items"].([]any)
	if !ok || len(items) != 1 {
		t.Fatalf("list items=%#v", items)
	}

	isolated := requestAppMessage(t, handler, http.MethodGet, "/app-messages/"+messageID, "account_002", "", nil)
	if isolated.Code != http.StatusNotFound {
		t.Fatalf("cross-account get status=%d body=%s", isolated.Code, isolated.Body.String())
	}
	if code := stringValue(decodeResponse(t, isolated)["code"]); code != "NOTIFICATION.USER.app_message_not_found" {
		t.Fatalf("cross-account stable code=%q", code)
	}

	ack := requestAppMessage(t, handler, http.MethodPost, "/app-messages/"+messageID+"/ack", "account_001", "", nil)
	if ack.Code != http.StatusOK || stringValue(decodeResponse(t, ack)["ackedAt"]) == "" {
		t.Fatalf("ack status=%d body=%s", ack.Code, ack.Body.String())
	}
	read := requestAppMessage(t, handler, http.MethodPost, "/app-messages/"+messageID+"/read", "account_001", "", nil)
	readBody := decodeResponse(t, read)
	if read.Code != http.StatusOK || readBody["read"] != true || stringValue(readBody["readAt"]) == "" {
		t.Fatalf("read status=%d body=%#v", read.Code, readBody)
	}
	unread := requestAppMessage(t, handler, http.MethodGet, "/app-messages/unread-count", "account_001", "", nil)
	if unread.Code != http.StatusOK || numberValue(decodeResponse(t, unread)["unreadCount"]) != 0 {
		t.Fatalf("unread status=%d body=%s", unread.Code, unread.Body.String())
	}

	if count, err := notificationMongoDB.Collection("app_messages").CountDocuments(context.Background(), bson.M{"_id": messageID}); err != nil || count != 1 {
		t.Fatalf("aggregate count=%d err=%v", count, err)
	}
	if count, err := notificationMongoDB.Collection("app_messages").CountDocuments(context.Background(), bson.M{
		"_id":                        messageID,
		"provenance.personalized":    true,
		"provenance.interestTags":    "travel",
		"provenance.matchedSegments": "travel_enthusiast",
		"provenance.lifecycleStage":  "active",
	}); err != nil || count != 1 {
		t.Fatalf("provenance persistence count=%d err=%v", count, err)
	}
	if count, err := notificationMongoDB.Collection("notification_delivery_jobs").CountDocuments(context.Background(), bson.M{"notificationId": messageID}); err != nil || count != 1 {
		t.Fatalf("delivery-job count=%d err=%v", count, err)
	}
	if count, err := notificationMongoDB.Collection("notification_delivery_jobs_outbox").CountDocuments(context.Background(), bson.M{
		"eventType": "NotificationDeliveryJobCreated",
	}); err != nil || count != 1 {
		t.Fatalf("delivery-job outbox count=%d err=%v", count, err)
	}
}

func requestAppMessage(
	t *testing.T,
	handler http.Handler,
	method, path, actorID, idempotencyKey string,
	body []byte,
) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, bytes.NewReader(body))
	if actorID != "" {
		req.Header.Set("X-Client-User-Id", actorID)
	}
	if idempotencyKey != "" {
		req.Header.Set("Idempotency-Key", idempotencyKey)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, req)
	return recorder
}

func decodeResponse(t *testing.T, recorder *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var body map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response %q: %v", recorder.Body.String(), err)
	}
	return body
}

func stringValue(value any) string {
	text, _ := value.(string)
	return text
}

func numberValue(value any) int64 {
	number, _ := value.(float64)
	return int64(number)
}
