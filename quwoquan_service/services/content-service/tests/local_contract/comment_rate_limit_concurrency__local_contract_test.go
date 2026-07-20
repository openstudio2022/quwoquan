package local_contract

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/services/content-service/internal/application/commandmeta"
	commentapp "quwoquan_service/services/content-service/internal/application/comment"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
	"quwoquan_service/services/content-service/internal/testsupport"
	commenttestsupport "quwoquan_service/services/content-service/internal/testsupport/comment"
)

func TestCreateCommentRateLimitIsAtomicAcrossConcurrentCommands(t *testing.T) {
	t.Parallel()

	const concurrency = 8
	store := commenttestsupport.NewStore()
	store.SeedPost("post-rate-concurrency", "persona-post-owner")
	service := commentapp.NewCommentService(
		commentapp.BindDataPorts(
			store,
			store,
			testsupport.NewReactionStore(),
			store,
			store,
		),
		commentapp.WithRateLimitConfig(commentapp.RateLimitConfig{
			BurstWindow: time.Minute,
			BurstMax:    2,
			DailyWindow: 24 * time.Hour,
			DailyMax:    100,
		}),
	)

	start := make(chan struct{})
	results := make(chan error, concurrency)
	var workers sync.WaitGroup
	workers.Add(concurrency)
	for index := 0; index < concurrency; index++ {
		index := index
		go func() {
			defer workers.Done()
			<-start
			_, err := service.CreateComment(
				commandmeta.WithIdempotencyKey(
					context.Background(),
					fmt.Sprintf("concurrent-rate-%d", index),
				),
				commentapp.CreateCommentCommand{
					PostID:  "post-rate-concurrency",
					ActorID: "persona-rate-concurrency",
					Content: fmt.Sprintf("concurrent comment %d", index),
				},
			)
			results <- err
		}()
	}
	close(start)
	workers.Wait()
	close(results)

	successes := 0
	limited := 0
	for err := range results {
		switch {
		case err == nil:
			successes++
		case strings.Contains(
			err.Error(),
			contentgenerated.ErrCommentRateLimited.Error(),
		):
			limited++
		default:
			t.Fatalf("并发创建返回非预期错误：%v", err)
		}
	}
	if successes != 2 || limited != concurrency-2 {
		t.Fatalf(
			"并发频控结果 success=%d limited=%d，期望 success=2 limited=%d",
			successes,
			limited,
			concurrency-2,
		)
	}
}
