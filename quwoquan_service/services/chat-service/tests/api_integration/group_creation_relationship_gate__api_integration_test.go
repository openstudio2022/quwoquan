package api_integration

import (
	"context"
	"fmt"
	"os"
	"sync"
	"testing"

	"github.com/alicebob/miniredis/v2"
	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	rterr "quwoquan_service/runtime/errors"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/chat-service/internal/application"
	chatcache "quwoquan_service/services/chat-service/internal/infrastructure/cache"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

var (
	groupCreationMongoOnce      sync.Once
	groupCreationMongoDB        *mongo.Database
	groupCreationMongoClient    *mongo.Client
	groupCreationMongoContainer *mongomod.MongoDBContainer
	groupCreationMongoErr       error
)

var groupCreationCollections = []string{
	"conversations",
	"messages",
	"conversation_members",
	"conversation_user_states",
	"message_receipts",
	"reliable_task_outbox",
	"reliable_async_task",
	"notification_outbox",
	"notification_delivery_ledger",
}

func TestMain(m *testing.M) {
	code := m.Run()
	ctx := context.Background()
	if groupCreationMongoClient != nil {
		_ = groupCreationMongoClient.Disconnect(ctx)
	}
	if groupCreationMongoContainer != nil {
		_ = groupCreationMongoContainer.Terminate(ctx)
	}
	os.Exit(code)
}

func requireGroupCreationMongoDB(tb testing.TB) *mongo.Database {
	tb.Helper()
	groupCreationMongoOnce.Do(func() {
		ctx := context.Background()
		mongoURI := os.Getenv("TEST_MONGO_URI")
		if mongoURI == "" {
			container, err := tryRunGroupCreationMongoContainer(ctx)
			if err != nil {
				groupCreationMongoErr = fmt.Errorf("start mongo testcontainer: %w", err)
				return
			}
			groupCreationMongoContainer = container
			uri, err := container.ConnectionString(ctx)
			if err != nil {
				groupCreationMongoErr = fmt.Errorf("get mongo connection string: %w", err)
				return
			}
			mongoURI = uri
		}
		client, err := mongo.Connect(mongoopts.Client().ApplyURI(mongoURI))
		if err != nil {
			groupCreationMongoErr = fmt.Errorf("connect mongo: %w", err)
			return
		}
		groupCreationMongoClient = client
		groupCreationMongoDB = client.Database("chat_group_creation_test")
	})
	if groupCreationMongoErr != nil {
		tb.Fatalf("group creation mongo unavailable: %v", groupCreationMongoErr)
	}
	if groupCreationMongoDB == nil {
		tb.Fatal("group creation mongo database not initialized")
	}
	return groupCreationMongoDB
}

func tryRunGroupCreationMongoContainer(ctx context.Context) (c *mongomod.MongoDBContainer, err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("testcontainers panic (Docker unavailable?): %v", r)
		}
	}()
	c, err = mongomod.Run(ctx, "mongo:7-jammy")
	return
}

func cleanGroupCreationCollections(t *testing.T) {
	t.Helper()
	db := requireGroupCreationMongoDB(t)
	for _, name := range groupCreationCollections {
		_, _ = db.Collection(name).DeleteMany(context.Background(), bson.M{})
	}
}

type groupCreationProfileResolver struct{}

func (groupCreationProfileResolver) ResolveMany(
	_ context.Context,
	userIDs []string,
) (map[string]application.ProfileSnapshot, error) {
	out := make(map[string]application.ProfileSnapshot, len(userIDs))
	for _, id := range userIDs {
		out[id] = application.ProfileSnapshot{
			DisplayName:   "Display_" + id,
			AvatarURL:     "https://test.avatar/" + id,
			AvatarAssetID: "ua_" + id,
			AvatarVersion: 1,
			Bio:           "Bio_" + id,
		}
	}
	return out, nil
}

type groupCreationStubRelationshipGate struct {
	cap application.RelationshipCapability
	err error
}

func (g groupCreationStubRelationshipGate) GetCapability(
	context.Context,
	string,
	string,
) (application.RelationshipCapability, error) {
	return g.cap, g.err
}

type keyedRelationshipGate struct {
	caps    map[string]application.RelationshipCapability
	missing application.RelationshipCapability
}

func (g keyedRelationshipGate) GetCapability(
	_ context.Context,
	_ string,
	targetID string,
) (application.RelationshipCapability, error) {
	if cap, ok := g.caps[targetID]; ok {
		return cap, nil
	}
	return g.missing, nil
}

func mutualCapability() application.RelationshipCapability {
	return application.RelationshipCapability{
		CanCreateDirectConversation: true,
		CanSendMessage:              true,
		HasFormalConversation:       true,
		IsMutual:                    true,
	}
}

func newGroupCreationConversationService(
	t *testing.T,
	gate application.RelationshipGate,
) *application.ConversationService {
	t.Helper()
	mr, err := miniredis.Run()
	if err != nil {
		t.Fatalf("miniredis: %v", err)
	}
	t.Cleanup(mr.Close)
	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {Mode: "standalone", Addr: mr.Addr()},
		},
		DefaultScene: "general",
	})
	t.Cleanup(func() { _ = router.Close() })
	store := persistence.NewMongoChatStore(requireGroupCreationMongoDB(t))
	cache := chatcache.NewConversationCache(router.Scene("general"))
	return application.NewConversationService(
		store,
		cache,
		nil,
		groupCreationProfileResolver{},
		gate,
		nil,
		nil,
		nil,
	)
}

func TestCreateConversation_Group_RequiresMutualMembers(t *testing.T) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationService(t, groupCreationStubRelationshipGate{
		cap: application.RelationshipCapability{},
	})

	_, err := svc.CreateConversation(context.Background(), application.CreateConversationRequest{
		Type:             "group",
		Title:            "非互关群",
		MaxGroupSize:     500,
		CreatorId:        "user_a",
		InitialMemberIds: []string{"user_b", "user_c"},
	})
	if err == nil {
		t.Fatal("expected group_member_not_mutual gate error for non-mutual group member")
	}
	appErr, ok := err.(*rterr.AppError)
	if !ok {
		t.Fatalf("expected AppError, got %T (%v)", err, err)
	}
	if got := appErr.Code.String(); got != "CHAT.USER.group_member_not_mutual" {
		t.Fatalf("code = %q, want CHAT.USER.group_member_not_mutual", got)
	}
}

func TestCreateConversation_Group_BlockedMember(t *testing.T) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationService(t, groupCreationStubRelationshipGate{
		cap: application.RelationshipCapability{IsBlocked: true},
	})

	_, err := svc.CreateConversation(context.Background(), application.CreateConversationRequest{
		Type:             "group",
		Title:            "拉黑群",
		MaxGroupSize:     500,
		CreatorId:        "user_a",
		InitialMemberIds: []string{"user_b"},
	})
	if err == nil {
		t.Fatal("expected group_member_blocked gate error for blocked group member")
	}
	appErr, ok := err.(*rterr.AppError)
	if !ok {
		t.Fatalf("expected AppError, got %T (%v)", err, err)
	}
	if got := appErr.Code.String(); got != "CHAT.USER.group_member_blocked" {
		t.Fatalf("code = %q, want CHAT.USER.group_member_blocked", got)
	}
}

func TestCreateConversation_Group_AllowsMutualMembers(t *testing.T) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationService(
		t,
		groupCreationStubRelationshipGate{cap: mutualCapability()},
	)

	conv, err := svc.CreateConversation(context.Background(), application.CreateConversationRequest{
		Type:             "group",
		Title:            "互关群",
		MaxGroupSize:     500,
		CreatorId:        "user_a",
		InitialMemberIds: []string{"user_b", "user_c"},
	})
	if err != nil {
		t.Fatalf("create mutual group conversation: %v", err)
	}
	if conv == nil || conv.ID == "" {
		t.Fatal("expected conversation id")
	}
	if conv.MemberCount != 3 {
		t.Fatalf("member count = %d, want 3 (creator + 2 members)", conv.MemberCount)
	}
}

func TestCreateConversation_Group_MixedMembersRejectsNonMutual(t *testing.T) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationService(t, keyedRelationshipGate{
		caps: map[string]application.RelationshipCapability{
			"user_b": mutualCapability(),
			"user_c": {},
		},
	})

	_, err := svc.CreateConversation(context.Background(), application.CreateConversationRequest{
		Type:             "group",
		Title:            "混合群",
		MaxGroupSize:     500,
		CreatorId:        "user_a",
		InitialMemberIds: []string{"user_b", "user_c"},
	})
	if err == nil {
		t.Fatal("expected group_member_not_mutual gate error when any member is non-mutual")
	}
	appErr, ok := err.(*rterr.AppError)
	if !ok {
		t.Fatalf("expected AppError, got %T (%v)", err, err)
	}
	if got := appErr.Code.String(); got != "CHAT.USER.group_member_not_mutual" {
		t.Fatalf("code = %q, want CHAT.USER.group_member_not_mutual", got)
	}
}

func TestCreateConversation_Group_CircleBoundSkipsMutualGate(t *testing.T) {
	t.Cleanup(func() { cleanGroupCreationCollections(t) })
	svc := newGroupCreationConversationService(t, groupCreationStubRelationshipGate{
		cap: application.RelationshipCapability{},
	})

	conv, err := svc.CreateConversation(context.Background(), application.CreateConversationRequest{
		Type:             "group",
		Title:            "圈子群",
		CircleId:         "circle_001",
		CircleGroupId:    "circle_group_default_001",
		MaxGroupSize:     500,
		CreatorId:        "user_a",
		InitialMemberIds: []string{"user_b"},
	})
	if err != nil {
		t.Fatalf("circle-bound group should bypass mutual gate, got: %v", err)
	}
	if conv == nil || conv.ID == "" {
		t.Fatal("expected conversation id")
	}
}
