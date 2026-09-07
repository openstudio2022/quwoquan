// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
// readiness_case: message-sequence-concurrency-api
package api_integration

import (
	"context"
	"fmt"
	"sort"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
	conversationapp "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
	messageports "quwoquan_service/services/chat-service/internal/chat/message/domain/ports"
)

func TestConcurrentDifferentMessagesReceiveStrictUniqueMonotonicSeq(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(
		ctx,
		testinfra.UniqueDatabaseName("chat_message_sequence_api_integration"),
	)
	if err != nil {
		t.Fatalf("start real MongoDB replica set: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := runtime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	database := runtime.Database
	store := persistence.NewMongoChatStore(database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure message indexes: %v", err)
	}

	const (
		conversationID = "conversation-sequence-concurrency"
		writers        = 32
	)
	start := make(chan struct{})
	type commitResult struct {
		seq int64
		err error
	}
	results := make(chan commitResult, writers)
	var ready sync.WaitGroup
	ready.Add(writers)
	for writer := 0; writer < writers; writer++ {
		writer := writer
		go func() {
			ready.Done()
			<-start
			now := time.Now().UTC()
			message := messagemodel.Message{
				ID:              fmt.Sprintf("message-%d", writer),
				ConversationID:  conversationID,
				ClientMessageID: fmt.Sprintf("client-message-%d", writer),
				SenderID:        fmt.Sprintf("persona-%d", writer),
				Type:            "text",
				Content:         fmt.Sprintf("concurrent message %d", writer),
				Status:          "sent",
				Timestamp:       now,
				Version:         1,
			}
			committed, commitErr := store.CommitMessage(ctx, conversationapp.MessageCommit{
				Message:       message,
				CommandDigest: fmt.Sprintf("digest-%d", writer),
				Events: []messageports.OutboxEvent{{
					EventID:        fmt.Sprintf("event-%d", writer),
					EventType:      "MessageSent",
					ConversationID: conversationID,
					ActorID:        message.SenderID,
					Payload:        map[string]any{"clientMsgId": message.ClientMessageID},
				}},
			})
			results <- commitResult{seq: committed.Message.Seq, err: commitErr}
		}()
	}
	ready.Wait()
	close(start)

	sequences := make([]int64, 0, writers)
	for writer := 0; writer < writers; writer++ {
		result := <-results
		if result.err != nil {
			t.Fatalf("concurrent message commit: %v", result.err)
		}
		sequences = append(sequences, result.seq)
	}
	sort.Slice(sequences, func(left, right int) bool { return sequences[left] < sequences[right] })
	for index, sequence := range sequences {
		want := int64(index + 1)
		if sequence != want {
			t.Fatalf("sorted concurrent seq[%d]=%d, want %d; all=%v", index, sequence, want, sequences)
		}
	}
	assertMongoCount(t, ctx, database, "messages", bson.M{"conversationId": conversationID}, writers)
	assertMongoCount(t, ctx, database, "messages_command_receipts", bson.M{}, writers)
	assertMongoCount(t, ctx, database, "messages_outbox", bson.M{"conversationId": conversationID}, writers)

	var counter struct {
		Seq int64 `bson:"seq"`
	}
	if err := database.Collection("messages_sequences").FindOne(
		ctx,
		bson.M{"_id": conversationID},
	).Decode(&counter); err != nil {
		t.Fatalf("read message sequence: %v", err)
	}
	if counter.Seq != writers {
		t.Fatalf("message sequence=%d, want %d", counter.Seq, writers)
	}
}

func assertMongoCount(
	t *testing.T,
	ctx context.Context,
	database *mongo.Database,
	collection string,
	filter bson.M,
	want int64,
) {
	t.Helper()
	got, err := database.Collection(collection).CountDocuments(ctx, filter)
	if err != nil {
		t.Fatalf("count %s: %v", collection, err)
	}
	if got != want {
		t.Fatalf("%s count=%d, want %d", collection, got, want)
	}
}
