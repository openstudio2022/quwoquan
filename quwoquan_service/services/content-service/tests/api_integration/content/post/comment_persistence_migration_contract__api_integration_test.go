package api_integration

import (
	"context"
	"fmt"
	"sync"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
)

func TestCommentAggregateMongoTransactionAndCAS(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	postID := createCommentTestPost(t, "mongo-comment-post-owner")
	ctx := commandmeta.WithIdempotencyKey(context.Background(), "comment-mongo-transaction-create")
	command := commentapp.CreateCommentCommand{
		PostID: postID, ActorID: "mongo-comment-author", Content: "transactional Comment",
	}

	created, err := testCommentService.CreateComment(ctx, command)
	if err != nil {
		t.Fatalf("create Comment aggregate: %v", err)
	}
	replayed, err := testCommentService.CreateComment(ctx, command)
	if err != nil {
		t.Fatalf("replay Comment aggregate: %v", err)
	}
	if !replayed.Replayed || replayed.ID != created.ID || replayed.Version != created.Version {
		t.Fatalf("idempotency replay mismatch: created=%+v replayed=%+v", created, replayed)
	}

	assertMongoDocumentCount(t, "comments", bson.M{"_id": created.ID, "version": int64(1)}, 1)
	assertMongoDocumentCount(t, "comment_command_receipts", bson.M{"aggregateId": created.ID}, 1)
	assertMongoDocumentCount(t, "comment_outbox", bson.M{
		"aggregateId": created.ID, "aggregateVersion": int64(1), "eventType": "CommentCreated",
	}, 1)

	conflicting := command
	conflicting.Content = "different command digest"
	if _, err := testCommentService.CreateComment(ctx, conflicting); err == nil {
		t.Fatal("reusing a Comment idempotency key with a different digest must fail")
	}
	deleteContext := commandmeta.WithIdempotencyKey(context.Background(), "comment-mongo-delete")
	deleted, err := testCommentService.DeleteComment(deleteContext, commentapp.DeleteCommentCommand{
		PostID: postID, CommentID: created.ID, ActorID: command.ActorID,
	})
	if err != nil {
		t.Fatalf("delete Comment aggregate: %v", err)
	}
	if deleted.Version != 2 || deleted.Status != "deleted" {
		t.Fatalf("unexpected deleted Comment receipt: %+v", deleted)
	}
	assertMongoDocumentCount(t, "comments", bson.M{
		"_id": created.ID, "version": int64(2), "status": "deleted",
	}, 1)
	assertMongoDocumentCount(t, "comment_outbox", bson.M{"aggregateId": created.ID}, 2)
}

func TestCommentStore_AuthoritativeCountsNoCache(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	postID := createCommentTestPost(t, "authoritative-comment-post-owner")
	for index := 0; index < 5; index++ {
		ctx := commandmeta.WithIdempotencyKey(
			context.Background(), fmt.Sprintf("authoritative-comment-%d", index),
		)
		if _, err := testCommentService.CreateComment(ctx, commentapp.CreateCommentCommand{
			PostID: postID, ActorID: fmt.Sprintf("comment-author-%d", index),
			Content: fmt.Sprintf("authoritative-%d", index),
		}); err != nil {
			t.Fatalf("create authoritative Comment %d: %v", index, err)
		}
	}
	if err := drainCommentOutboxForHarness(context.Background()); err != nil {
		t.Fatalf("drain Comment count projection: %v", err)
	}
	page, err := testCommentService.ListComments(context.Background(), commentapp.ListCommentsQuery{
		PostID: postID, Limit: 20,
	})
	if err != nil {
		t.Fatalf("list authoritative Comments: %v", err)
	}
	authoritative, err := mongoDB.Collection("comments").CountDocuments(context.Background(), bson.M{
		"postId": postID, "status": "active",
	})
	if err != nil {
		t.Fatalf("count authoritative Comments: %v", err)
	}
	counters, err := testPostService.GetCounters(context.Background(), postID)
	if err != nil {
		t.Fatalf("read Post Comment projection: %v", err)
	}
	if page.Total != authoritative || numberAsInt64(counters["comment"]) != authoritative {
		t.Fatalf("authoritative Comment count mismatch: mongo=%d page=%d counters=%+v", authoritative, page.Total, counters)
	}
	var feedProjection struct {
		CommentCount int64 `bson:"commentCount"`
	}
	if err := mongoDB.Collection("rm_discovery_feed").FindOne(
		context.Background(),
		bson.M{"postId": postID},
	).Decode(&feedProjection); err != nil {
		t.Fatalf("read DiscoveryFeed Comment count projection: %v", err)
	}
	if feedProjection.CommentCount != authoritative {
		t.Fatalf(
			"DiscoveryFeed Comment count stale: mongo=%d feed=%d",
			authoritative,
			feedProjection.CommentCount,
		)
	}
}

func TestCommentCountReconciliation_HighConcurrency(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	postID := createCommentTestPost(t, "concurrent-comment-post-owner")

	const count = 24
	results := make([]commentapp.CommentCommandResult, count)
	errorsByIndex := make([]error, count)
	var wait sync.WaitGroup
	for index := 0; index < count; index++ {
		wait.Add(1)
		go func(index int) {
			defer wait.Done()
			ctx := commandmeta.WithIdempotencyKey(
				context.Background(), fmt.Sprintf("concurrent-comment-create-%d", index),
			)
			results[index], errorsByIndex[index] = testCommentService.CreateComment(ctx, commentapp.CreateCommentCommand{
				PostID: postID, ActorID: "concurrent-comment-author",
				Content: fmt.Sprintf("concurrent-%d", index),
			})
		}(index)
	}
	wait.Wait()
	for index, err := range errorsByIndex {
		if err != nil {
			t.Fatalf("concurrent create %d: %v", index, err)
		}
	}

	for index, result := range results {
		if index%3 != 0 {
			continue
		}
		wait.Add(1)
		go func(index int, result commentapp.CommentCommandResult) {
			defer wait.Done()
			ctx := commandmeta.WithIdempotencyKey(
				context.Background(), fmt.Sprintf("concurrent-comment-delete-%d", index),
			)
			_, errorsByIndex[index] = testCommentService.DeleteComment(ctx, commentapp.DeleteCommentCommand{
				PostID: postID, CommentID: result.ID, ActorID: "concurrent-comment-author",
			})
		}(index, result)
	}
	wait.Wait()
	for index, err := range errorsByIndex {
		if err != nil {
			t.Fatalf("concurrent mutation %d: %v", index, err)
		}
	}
	if err := drainCommentOutboxForHarness(context.Background()); err != nil {
		t.Fatalf("drain concurrent Comment outbox: %v", err)
	}

	authoritative, err := mongoDB.Collection("comments").CountDocuments(context.Background(), bson.M{
		"postId": postID, "status": "active",
	})
	if err != nil {
		t.Fatalf("count concurrent Comments: %v", err)
	}
	page, err := testCommentService.ListComments(context.Background(), commentapp.ListCommentsQuery{
		PostID: postID, Limit: 100,
	})
	if err != nil {
		t.Fatalf("list concurrent Comments: %v", err)
	}
	counters, err := testPostService.GetCounters(context.Background(), postID)
	if err != nil {
		t.Fatalf("read concurrent Post projection: %v", err)
	}
	if page.Total != authoritative || numberAsInt64(counters["comment"]) != authoritative {
		t.Fatalf("concurrent Comment convergence mismatch: mongo=%d page=%d counters=%+v", authoritative, page.Total, counters)
	}
}

func assertMongoDocumentCount(t *testing.T, collection string, filter bson.M, expected int64) {
	t.Helper()
	count, err := mongoDB.Collection(collection).CountDocuments(context.Background(), filter)
	if err != nil {
		t.Fatalf("count %s: %v", collection, err)
	}
	if count != expected {
		t.Fatalf("%s count=%d want=%d filter=%+v", collection, count, expected, filter)
	}
}
