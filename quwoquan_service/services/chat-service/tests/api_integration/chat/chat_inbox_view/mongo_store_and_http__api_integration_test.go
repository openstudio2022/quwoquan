// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
// readiness_case: list-inbox-api
// readiness_case: project-chat-inbox-api
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	inboxhttp "quwoquan_service/services/chat-service/internal/chat/chat_inbox_view/adapters/inbound/http"
	inboxapp "quwoquan_service/services/chat-service/internal/chat/chat_inbox_view/application"
	inboxpersistence "quwoquan_service/services/chat-service/internal/chat/chat_inbox_view/infrastructure/persistence"
)

var (
	inboxMongoClient    *mongo.Client
	inboxMongoDatabase  *mongo.Database
	inboxMongoContainer *mongomod.MongoDBContainer
	inboxStore          *inboxpersistence.MongoStore
)

func TestMain(suite *testing.M) {
	testinfra.ConfigureLocalContainerRuntime()
	startupContext, cancelStartup := context.WithTimeout(context.Background(), 2*time.Minute)
	mongoURI := strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	if mongoURI == "" {
		container, err := startInboxMongo(startupContext)
		if err != nil {
			panic("ChatInboxView api_integration requires MongoDB: " + err.Error())
		}
		inboxMongoContainer = container
		connectionString, err := container.ConnectionString(startupContext)
		if err != nil {
			panic("resolve ChatInboxView MongoDB URI: " + err.Error())
		}
		mongoURI = connectionString + "&directConnection=true"
	}
	var err error
	inboxMongoClient, err = mongo.Connect(options.Client().ApplyURI(mongoURI))
	if err != nil {
		panic("connect ChatInboxView MongoDB: " + err.Error())
	}
	inboxMongoDatabase = inboxMongoClient.Database(fmt.Sprintf("chat_inbox_view_%d", time.Now().UnixNano()))
	inboxStore = inboxpersistence.NewMongoStore(inboxMongoDatabase)
	if err := inboxStore.EnsureIndexes(startupContext); err != nil {
		panic("ensure ChatInboxView indexes: " + err.Error())
	}
	cancelStartup()

	exitCode := suite.Run()
	cleanupContext, cancelCleanup := context.WithTimeout(context.Background(), 30*time.Second)
	_ = inboxMongoDatabase.Drop(cleanupContext)
	_ = inboxMongoClient.Disconnect(cleanupContext)
	if inboxMongoContainer != nil {
		_ = inboxMongoContainer.Terminate(cleanupContext)
	}
	cancelCleanup()
	os.Exit(exitCode)
}

func startInboxMongo(ctx context.Context) (container *mongomod.MongoDBContainer, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("testcontainers panic: %v", recovered)
		}
	}()
	return mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
}

func TestChatInboxViewMongoStoreOwnsStablePageAndTombstone(t *testing.T) {
	ctx := context.Background()
	_, _ = inboxMongoDatabase.Collection("chat_inbox_views").DeleteMany(ctx, map[string]any{})
	base := time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC)
	items := []inboxapp.Item{
		{UserID: "persona-1", ConversationID: "conversation-1", Type: "group", Title: "pinned", Pinned: true, LastMessageTime: base},
		{UserID: "persona-1", ConversationID: "conversation-2", Type: "direct", Title: "newer", LastMessageTime: base.Add(time.Minute)},
		{UserID: "persona-1", ConversationID: "conversation-3", Type: "direct", Title: "older", LastMessageTime: base.Add(-time.Minute)},
	}
	for index, item := range items {
		if _, err := inboxStore.UpsertIfNewer(ctx, item, "conversation", int64(index+1), ""); err != nil {
			t.Fatal(err)
		}
	}
	first, err := inboxStore.List(ctx, "persona-1", 2, "")
	if err != nil || len(first.Items) != 2 || first.Items[0].ConversationID != "conversation-1" || first.NextCursor == "" {
		t.Fatalf("first stable page drifted: page=%+v err=%v", first, err)
	}
	second, err := inboxStore.List(ctx, "persona-1", 2, first.NextCursor)
	if err != nil || len(second.Items) != 1 || second.Items[0].ConversationID != "conversation-3" {
		t.Fatalf("second stable page drifted: page=%+v err=%v", second, err)
	}
	if _, err := inboxStore.TombstoneIfNewer(ctx, inboxapp.Identity{UserID: "persona-1", ConversationID: "conversation-2"}, "membership", 4); err != nil {
		t.Fatal(err)
	}
	visible, err := inboxStore.List(ctx, "persona-1", 10, "")
	if err != nil || len(visible.Items) != 2 {
		t.Fatalf("tombstone must remove content from the visible page: page=%+v err=%v", visible, err)
	}
}

func TestChatInboxViewHTTPUsesTrustedPersonaAndOpaqueCursor(t *testing.T) {
	ctx := context.Background()
	_, _ = inboxMongoDatabase.Collection("chat_inbox_views").DeleteMany(ctx, map[string]any{})
	if _, err := inboxStore.UpsertIfNewer(ctx, inboxapp.Item{
		UserID: "trusted-persona", ConversationID: "conversation-http", Type: "group",
		Title: "materialized", LastMessageTime: time.Now().UTC(),
	}, "conversation", 1, ""); err != nil {
		t.Fatal(err)
	}
	mux := http.NewServeMux()
	inboxhttp.NewHandler(inboxStore).Register(mux)
	request := httptest.NewRequest(http.MethodGet, "/chat/inbox?limit=10", nil)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{PersonaID: "trusted-persona"},
	}))
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, request)
	var body struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &body); response.Code != http.StatusOK || err != nil ||
		len(body.Items) != 1 || body.Items[0]["conversationId"] != "conversation-http" {
		t.Fatalf("typed inbox HTTP drifted: status=%d body=%s err=%v", response.Code, response.Body.String(), err)
	}

	invalid := httptest.NewRequest(http.MethodGet, "/chat/inbox?cursor=invalid-offset", nil)
	invalid = invalid.WithContext(request.Context())
	invalidResponse := httptest.NewRecorder()
	mux.ServeHTTP(invalidResponse, invalid)
	if invalidResponse.Code != http.StatusBadRequest {
		t.Fatalf("non-canonical cursor must fail closed: status=%d body=%s", invalidResponse.Code, invalidResponse.Body.String())
	}
}

type inboxAPIEventSource struct{ events []inboxapp.Event }

func (source inboxAPIEventSource) ReadAfter(
	_ context.Context,
	checkpoint string,
	_ int,
) ([]inboxapp.Event, error) {
	if checkpoint != "" {
		return nil, nil
	}
	return source.events, nil
}

type inboxAPISnapshotSource struct{ item inboxapp.Item }

func (source inboxAPISnapshotSource) Load(
	_ context.Context,
	identity inboxapp.Identity,
) (inboxapp.Item, bool, error) {
	item := source.item
	item.UserID = identity.UserID
	item.ConversationID = identity.ConversationID
	return item, true, nil
}

func (inboxAPISnapshotSource) ListIdentities(
	context.Context,
	string,
	int,
) ([]inboxapp.Identity, string, error) {
	return nil, "", nil
}

type inboxAPIMembers []string

func (members inboxAPIMembers) ListPersonaIDs(context.Context, string) ([]string, error) {
	return append([]string(nil), members...), nil
}

type inboxAPIStateAdvancer struct{ calls int }

func (advancer *inboxAPIStateAdvancer) AdvanceUnread(
	context.Context,
	inboxapp.Identity,
	int64,
	int,
	int,
	time.Time,
) error {
	advancer.calls++
	return nil
}

func TestChatInboxProjectorCommitsCheckpointAndViewThroughRealMongo(t *testing.T) {
	ctx := t.Context()
	if _, err := inboxMongoDatabase.Collection("chat_inbox_views").DeleteMany(ctx, map[string]any{}); err != nil {
		t.Fatal(err)
	}
	if _, err := inboxMongoDatabase.Collection("chat_inbox_view_checkpoints").DeleteMany(ctx, map[string]any{}); err != nil {
		t.Fatal(err)
	}
	advancer := &inboxAPIStateAdvancer{}
	projector := inboxapp.NewProjector(
		inboxStore,
		inboxStore,
		inboxAPISnapshotSource{item: inboxapp.Item{
			Type: "group", Title: "projected through production path",
			LastMessageTime: time.Date(2026, 8, 2, 13, 0, 0, 0, time.UTC),
		}},
		inboxAPIMembers{"persona-projector"},
		advancer,
		map[string]inboxapp.EventSource{
			"message": inboxAPIEventSource{events: []inboxapp.Event{{
				ID: "message-event-101", Type: "MessageSent",
				ConversationID: "conversation-projector", ActorID: "persona-sender",
				Checkpoint: "101", Payload: map[string]any{
					"seq": int64(1), "timestamp": time.Date(2026, 8, 2, 13, 0, 0, 0, time.UTC),
				},
			}, {
				ID: "message-event-102", Type: "MessageRecalled",
				ConversationID: "conversation-projector", ActorID: "persona-sender",
				Checkpoint: "102", Payload: map[string]any{
					"seq": int64(1), "recalledAt": time.Date(2026, 8, 2, 13, 1, 0, 0, time.UTC),
				},
			}}},
		},
	)
	if processed, err := projector.Drain(ctx, 100); err != nil || processed != 2 {
		t.Fatalf("first Drain() processed=%d err=%v", processed, err)
	}
	if processed, err := projector.Drain(ctx, 100); err != nil || processed != 0 {
		t.Fatalf("checkpoint replay Drain() processed=%d err=%v", processed, err)
	}
	page, err := inboxStore.List(ctx, "persona-projector", 10, "")
	if err != nil || len(page.Items) != 1 || page.Items[0].ConversationID != "conversation-projector" {
		t.Fatalf("projected page=%+v err=%v", page, err)
	}
	checkpoint, err := inboxStore.Load(ctx, "chat-inbox-view-message")
	if err != nil || checkpoint != "102" || advancer.calls != 1 {
		t.Fatalf("projector checkpoint=%q unread advances=%d err=%v", checkpoint, advancer.calls, err)
	}
}
