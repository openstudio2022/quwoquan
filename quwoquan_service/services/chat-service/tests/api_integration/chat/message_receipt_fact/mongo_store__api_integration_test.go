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
	receiptapp "quwoquan_service/services/chat-service/internal/chat/message_receipt_fact/application"
	receiptmodel "quwoquan_service/services/chat-service/internal/chat/message_receipt_fact/domain/model"
	receiptpersistence "quwoquan_service/services/chat-service/internal/chat/message_receipt_fact/infrastructure/persistence"
)

var (
	receiptMongoClient    *mongo.Client
	receiptMongoDatabase  *mongo.Database
	receiptMongoContainer *mongomod.MongoDBContainer
	receiptAppender       *receiptapp.Appender
)

func TestMain(suite *testing.M) {
	testinfra.ConfigureLocalContainerRuntime()
	startupContext, cancelStartup := context.WithTimeout(context.Background(), 2*time.Minute)
	mongoURI := strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	if mongoURI == "" {
		container, err := startMongo(startupContext)
		if err != nil {
			panic("MessageReceiptFact api_integration requires MongoDB: " + err.Error())
		}
		receiptMongoContainer = container
		connectionString, err := container.ConnectionString(startupContext)
		if err != nil {
			panic("resolve MessageReceiptFact MongoDB URI: " + err.Error())
		}
		mongoURI = connectionString + "&directConnection=true"
	}
	var err error
	receiptMongoClient, err = mongo.Connect(options.Client().ApplyURI(mongoURI))
	if err != nil {
		panic("connect MessageReceiptFact MongoDB: " + err.Error())
	}
	if err := receiptMongoClient.Ping(startupContext, nil); err != nil {
		panic("ping MessageReceiptFact MongoDB: " + err.Error())
	}
	receiptMongoDatabase = receiptMongoClient.Database(
		fmt.Sprintf("chat_message_receipt_fact_%d", time.Now().UnixNano()),
	)
	store := receiptpersistence.NewMongoStore(receiptMongoDatabase)
	if err := store.EnsureIndexes(startupContext); err != nil {
		panic("ensure MessageReceiptFact indexes: " + err.Error())
	}
	receiptAppender = receiptapp.NewAppender(store)
	cancelStartup()

	status := suite.Run()
	cleanupContext, cancelCleanup := context.WithTimeout(context.Background(), 30*time.Second)
	_ = receiptMongoDatabase.Drop(cleanupContext)
	_ = receiptMongoClient.Disconnect(cleanupContext)
	if receiptMongoContainer != nil {
		_ = receiptMongoContainer.Terminate(cleanupContext)
	}
	cancelCleanup()
	os.Exit(status)
}

func startMongo(ctx context.Context) (container *mongomod.MongoDBContainer, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("testcontainers panic: %v", recovered)
		}
	}()
	return mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
}

func TestMongoStoreCommitsOneImmutableFactPerMessageAndPersona(t *testing.T) {
	if _, err := receiptMongoDatabase.Collection("message_receipts").DeleteMany(context.Background(), bson.M{}); err != nil {
		t.Fatal(err)
	}
	fact := receiptmodel.Fact{
		ID:             "receipt-mongo-1",
		MessageID:      "message-mongo-1",
		ConversationID: "conversation-mongo-1",
		UserID:         "persona-mongo-1",
		ReadAt:         time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC),
	}
	if _, replayed, err := receiptAppender.Append(context.Background(), fact); err != nil || replayed {
		t.Fatalf("first append replayed=%v err=%v", replayed, err)
	}
	if committed, replayed, err := receiptAppender.Append(context.Background(), fact); err != nil || !replayed || !committed.SameImmutableValue(fact) {
		t.Fatalf("exact replay committed=%+v replayed=%v err=%v", committed, replayed, err)
	}
	conflict := fact
	conflict.ConversationID = "conversation-mongo-other"
	if _, _, err := receiptAppender.Append(context.Background(), conflict); !errors.Is(err, receiptmodel.ErrIdentityConflict) {
		t.Fatalf("immutable identity conflict must fail, got %v", err)
	}

	count, err := receiptMongoDatabase.Collection("message_receipts").CountDocuments(context.Background(), bson.M{})
	if err != nil || count != 1 {
		t.Fatalf("fact count=%d err=%v", count, err)
	}
	items, err := receiptAppender.ListByMessage(context.Background(), fact.MessageID)
	if err != nil || len(items) != 1 || !items[0].SameImmutableValue(fact) {
		t.Fatalf("named reader items=%+v err=%v", items, err)
	}
}
