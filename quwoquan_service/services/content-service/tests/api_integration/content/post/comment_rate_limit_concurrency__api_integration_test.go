package api_integration

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/runtime/commandmeta"
	contentgenerated "quwoquan_service/services/content-service/generated/content/comment"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
	commentpersistence "quwoquan_service/services/content-service/internal/content/comment/infrastructure/persistence"
)

type apiIntegrationCommentAttachmentReader struct{}

func (apiIntegrationCommentAttachmentReader) ValidateCommentAttachments(
	context.Context,
	string,
	[]string,
) error {
	return nil
}

func (apiIntegrationCommentAttachmentReader) ReadCommentAttachments(
	context.Context,
	[]string,
) (map[string]commentmodel.AttachmentProjection, error) {
	return map[string]commentmodel.AttachmentProjection{}, nil
}

func TestCommentMongoRateLimitIsAtomicAndDeletionCannotRestoreQuota(
	t *testing.T,
) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)

	const (
		authorID    = "comment-mongo-rate-author"
		concurrency = 8
	)
	postID := createCommentTestPost(t, "comment-mongo-rate-post-owner")
	store := newMongoCommentDataAdapter(t, requireMongoDB(t))
	viewerRelationships :=
		commentpersistence.NewCommentViewerRelationshipMongoProjection(requireMongoDB(t))
	service := commentapp.NewCommentService(
		commentapp.BindDataPorts(
			store,
			apiIntegrationCommentAttachmentReader{},
			testReactionStore,
			viewerRelationships,
			viewerRelationships,
		),
		commentapp.WithRateLimitConfig(commentapp.RateLimitConfig{
			BurstWindow: time.Hour,
			BurstMax:    2,
			DailyWindow: 24 * time.Hour,
			DailyMax:    100,
		}),
	)

	type createAttempt struct {
		command commentapp.CreateCommentCommand
		key     string
		result  commentapp.CommentCommandResult
		err     error
	}
	start := make(chan struct{})
	attempts := make(chan createAttempt, concurrency)
	var workers sync.WaitGroup
	workers.Add(concurrency)
	for index := 0; index < concurrency; index++ {
		index := index
		go func() {
			defer workers.Done()
			<-start
			command := commentapp.CreateCommentCommand{
				PostID:  postID,
				ActorID: authorID,
				Content: fmt.Sprintf("mongo concurrent comment %d", index),
			}
			key := fmt.Sprintf("comment-mongo-rate-%d", index)
			result, err := service.CreateComment(
				commandmeta.WithIdempotencyKey(context.Background(), key),
				command,
			)
			attempts <- createAttempt{
				command: command,
				key:     key,
				result:  result,
				err:     err,
			}
		}()
	}
	close(start)
	workers.Wait()
	close(attempts)

	accepted := make([]createAttempt, 0, 2)
	limited := 0
	for attempt := range attempts {
		switch {
		case attempt.err == nil:
			accepted = append(accepted, attempt)
		case strings.Contains(
			attempt.err.Error(),
			contentgenerated.ErrCommentRateLimited.Error(),
		):
			limited++
		default:
			t.Fatalf("concurrent Mongo Comment create returned unexpected error: %v", attempt.err)
		}
	}
	if len(accepted) != 2 || limited != concurrency-2 {
		t.Fatalf(
			"atomic Mongo rate limit accepted=%d limited=%d, want accepted=2 limited=%d",
			len(accepted),
			limited,
			concurrency-2,
		)
	}

	replayed, err := service.CreateComment(
		commandmeta.WithIdempotencyKey(context.Background(), accepted[0].key),
		accepted[0].command,
	)
	if err != nil || !replayed.Replayed || replayed.ID != accepted[0].result.ID {
		t.Fatalf("idempotent replay consumed quota or drifted: result=%+v err=%v", replayed, err)
	}

	_, err = service.DeleteComment(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			"comment-mongo-rate-delete",
		),
		commentapp.DeleteCommentCommand{
			PostID:    postID,
			CommentID: accepted[0].result.ID,
			ActorID:   authorID,
		},
	)
	if err != nil {
		t.Fatalf("delete accepted Comment before quota retry: %v", err)
	}
	_, err = service.CreateComment(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			"comment-mongo-rate-after-delete",
		),
		commentapp.CreateCommentCommand{
			PostID:  postID,
			ActorID: authorID,
			Content: "deletion must not restore quota",
		},
	)
	if err == nil || !strings.Contains(
		err.Error(),
		contentgenerated.ErrCommentRateLimited.Error(),
	) {
		t.Fatalf("deleting a Comment restored rate-limit quota: %v", err)
	}

	count, err := requireMongoDB(t).Collection("comments").CountDocuments(
		context.Background(),
		bson.M{"authorId": authorID},
	)
	if err != nil {
		t.Fatalf("count Mongo Comments after rate-limit test: %v", err)
	}
	if count != 2 {
		t.Fatalf("Mongo rate-limit persisted %d Comments, want 2", count)
	}
}
