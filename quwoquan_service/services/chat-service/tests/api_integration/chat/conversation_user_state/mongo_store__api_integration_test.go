// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
package api_integration

import (
	"context"
	"errors"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/internal/platform/testinfra"
	userstatemodel "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/domain/model"
	userstatepersistence "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/infrastructure/persistence"
)

var (
	userStateMongoClient    *mongo.Client
	userStateMongoDatabase  *mongo.Database
	userStateMongoContainer *mongomod.MongoDBContainer
	userStateStore          *userstatepersistence.MongoStore
)

func TestMain(suite *testing.M) {
	testinfra.ConfigureLocalContainerRuntime()
	startupContext, cancelStartup := context.WithTimeout(context.Background(), 2*time.Minute)
	mongoURI := strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	if mongoURI == "" {
		container, err := startUserStateMongo(startupContext)
		if err != nil {
			panic("ConversationUserState api_integration requires MongoDB: " + err.Error())
		}
		userStateMongoContainer = container
		connectionString, err := container.ConnectionString(startupContext)
		if err != nil {
			panic("resolve ConversationUserState MongoDB URI: " + err.Error())
		}
		mongoURI = connectionString + "&directConnection=true"
	}
	var err error
	userStateMongoClient, err = mongo.Connect(options.Client().ApplyURI(mongoURI))
	if err != nil {
		panic("connect ConversationUserState MongoDB: " + err.Error())
	}
	userStateMongoDatabase = userStateMongoClient.Database(
		fmt.Sprintf("chat_conversation_user_state_%d", time.Now().UnixNano()),
	)
	userStateStore = userstatepersistence.NewMongoStore(userStateMongoDatabase)
	if err := userStateStore.EnsureIndexes(startupContext); err != nil {
		panic("ensure ConversationUserState indexes: " + err.Error())
	}
	cancelStartup()

	exitCode := suite.Run()
	cleanupContext, cancelCleanup := context.WithTimeout(context.Background(), 30*time.Second)
	_ = userStateMongoDatabase.Drop(cleanupContext)
	_ = userStateMongoClient.Disconnect(cleanupContext)
	if userStateMongoContainer != nil {
		_ = userStateMongoContainer.Terminate(cleanupContext)
	}
	cancelCleanup()
	os.Exit(exitCode)
}

func startUserStateMongo(ctx context.Context) (container *mongomod.MongoDBContainer, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("testcontainers panic: %v", recovered)
		}
	}()
	return mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
}

func TestMongoStoreOwnsMonotonicInboxProjectionAndTerminalDelete(t *testing.T) {
	state := userstatemodel.State{
		ID: "state-1", UserId: "persona-1", ConversationId: "conversation-1",
		UpdatedAt: time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC),
	}
	if err := userStateStore.UpsertUserState(context.Background(), &state); err != nil {
		t.Fatal(err)
	}
	messageTime := time.Date(2026, 8, 2, 12, 1, 0, 0, time.UTC)
	for range 2 {
		if err := userStateStore.AdvanceInboxUnread(
			context.Background(), "persona-1", "conversation-1", 7, 1, 1, messageTime,
		); err != nil {
			t.Fatal(err)
		}
	}
	stored, err := userStateStore.FindUserState(context.Background(), "persona-1", "conversation-1")
	if err != nil || stored.InboxProjectedSeq != 7 || stored.UnreadCount != 1 || stored.MentionUnreadCount != 1 {
		t.Fatalf("replay-safe projection drifted: state=%+v err=%v", stored, err)
	}
	if err := userStateStore.DeleteUserState(context.Background(), "persona-1", "conversation-1"); err != nil {
		t.Fatal(err)
	}
	if _, err := userStateStore.FindUserState(context.Background(), "persona-1", "conversation-1"); !errors.Is(err, userstatemodel.ErrNotFound) {
		t.Fatalf("terminal delete must remove state, got %v", err)
	}
	if err := userStateStore.AdvanceInboxUnread(
		context.Background(), "persona-1", "conversation-1", 8, 1, 0, messageTime,
	); err != nil {
		t.Fatalf("late projection after terminal delete must be a no-op: %v", err)
	}
}
