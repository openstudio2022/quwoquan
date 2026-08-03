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
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/internal/platform/testinfra"
	membershipmodel "quwoquan_service/services/chat-service/internal/chat/conversation_membership/domain/model"
	membershippersistence "quwoquan_service/services/chat-service/internal/chat/conversation_membership/infrastructure/persistence"
)

var (
	membershipMongoClient    *mongo.Client
	membershipMongoDatabase  *mongo.Database
	membershipMongoContainer *mongomod.MongoDBContainer
	membershipStore          *membershippersistence.MongoStore
)

func TestMain(suite *testing.M) {
	testinfra.ConfigureLocalContainerRuntime()
	startupContext, cancelStartup := context.WithTimeout(context.Background(), 2*time.Minute)
	mongoURI := strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	if mongoURI == "" {
		container, err := startMongo(startupContext)
		if err != nil {
			panic("ConversationMembership api_integration requires MongoDB: " + err.Error())
		}
		membershipMongoContainer = container
		connectionString, err := container.ConnectionString(startupContext)
		if err != nil {
			panic("resolve ConversationMembership MongoDB URI: " + err.Error())
		}
		mongoURI = connectionString + "&directConnection=true"
	}
	var err error
	membershipMongoClient, err = mongo.Connect(options.Client().ApplyURI(mongoURI))
	if err != nil {
		panic("connect ConversationMembership MongoDB: " + err.Error())
	}
	if err := membershipMongoClient.Ping(startupContext, nil); err != nil {
		panic("ping ConversationMembership MongoDB: " + err.Error())
	}
	membershipMongoDatabase = membershipMongoClient.Database(
		fmt.Sprintf("chat_conversation_membership_%d", time.Now().UnixNano()),
	)
	membershipStore = membershippersistence.NewMongoStore(membershipMongoDatabase)
	if err := membershipStore.EnsureIndexes(startupContext); err != nil {
		panic("ensure ConversationMembership indexes: " + err.Error())
	}
	cancelStartup()

	exitCode := suite.Run()
	cleanupContext, cancelCleanup := context.WithTimeout(context.Background(), 30*time.Second)
	_ = membershipMongoDatabase.Drop(cleanupContext)
	_ = membershipMongoClient.Disconnect(cleanupContext)
	if membershipMongoContainer != nil {
		_ = membershipMongoContainer.Terminate(cleanupContext)
	}
	cancelCleanup()
	os.Exit(exitCode)
}

func startMongo(ctx context.Context) (container *mongomod.MongoDBContainer, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("testcontainers panic: %v", recovered)
		}
	}()
	return mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
}

func TestMongoStoreOwnsMembershipIdentityPaginationAndTerminalDelete(t *testing.T) {
	if _, err := membershipMongoDatabase.Collection("conversation_memberships").DeleteMany(context.Background(), bson.M{}); err != nil {
		t.Fatal(err)
	}
	joinedAt := time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC)
	for _, member := range []membershipmodel.Member{
		{ID: "membership-1", ConversationId: "conversation-1", UserId: "persona-1", DisplayName: "Alice", MemberType: "user", Role: "owner", JoinedAt: joinedAt},
		{ID: "membership-2", ConversationId: "conversation-1", UserId: "persona-2", DisplayName: "Bob", MemberType: "user", Role: "member", JoinedAt: joinedAt.Add(time.Second)},
	} {
		copy := member
		if err := membershipStore.CreateMember(context.Background(), &copy); err != nil {
			t.Fatal(err)
		}
	}
	duplicate := membershipmodel.Member{
		ID: "membership-3", ConversationId: "conversation-1", UserId: "persona-2",
		MemberType: "user", Role: "member", JoinedAt: joinedAt,
	}
	if err := membershipStore.CreateMember(context.Background(), &duplicate); !mongo.IsDuplicateKeyError(err) {
		t.Fatalf("duplicate business identity must fail, got %v", err)
	}

	page, err := membershipStore.ListMembers(context.Background(), "conversation-1", membershipmodel.ListQuery{
		Limit: 1, Sort: membershipmodel.ListSortJoinedAsc,
	})
	if err != nil || len(page) != 1 || page[0].UserId != "persona-1" {
		t.Fatalf("first page=%+v err=%v", page, err)
	}
	second, err := membershipStore.ListMembers(context.Background(), "conversation-1", membershipmodel.ListQuery{
		Limit: 1, Sort: membershipmodel.ListSortJoinedAsc,
		Cursor: membershipmodel.EncodeJoinedCursor(page[0].JoinedAt, page[0].ID),
	})
	if err != nil || len(second) != 1 || second[0].UserId != "persona-2" {
		t.Fatalf("second page=%+v err=%v", second, err)
	}
	if err := membershipStore.DeleteMember(context.Background(), "conversation-1", "persona-2"); err != nil {
		t.Fatal(err)
	}
	if _, err := membershipStore.FindMember(context.Background(), "conversation-1", "persona-2"); !errors.Is(err, membershipmodel.ErrNotFound) {
		t.Fatalf("terminal delete must remove the active row, got %v", err)
	}
}
