package api_integration

import (
	"context"
	"fmt"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

func TestMongoMediaProjectionCheckpointIsMonotonicAcrossReplicas(t *testing.T) {
	consumer := fmt.Sprintf("media-processing-monotonic-%d", time.Now().UnixNano())
	collection := mongoDB.Collection("media_projection_checkpoints")
	t.Cleanup(func() {
		_, _ = collection.DeleteOne(context.Background(), bson.M{"_id": consumer})
	})

	replicaA := persistence.NewMongoMediaStore(mongoDB)
	replicaB := persistence.NewMongoMediaStore(mongoDB)
	base := time.Date(2032, time.April, 5, 6, 7, 8, 123456789, time.UTC)
	checkpoints := make([]string, 32)
	for index := range checkpoints {
		checkpoints[index] = mediaCheckpointForTest(
			base.Add(time.Duration(index)*time.Nanosecond),
			fmt.Sprintf("evt-%03d", index),
		)
	}

	start := make(chan struct{})
	errs := make(chan error, len(checkpoints))
	var wait sync.WaitGroup
	for index, checkpoint := range checkpoints {
		wait.Add(1)
		go func(index int, checkpoint string) {
			defer wait.Done()
			<-start
			store := replicaA
			if index%2 == 1 {
				store = replicaB
			}
			errs <- store.SaveCheckpoint(context.Background(), consumer, checkpoint)
		}(index, checkpoint)
	}
	close(start)
	wait.Wait()
	close(errs)
	for err := range errs {
		if err != nil {
			t.Fatalf("concurrent checkpoint save: %v", err)
		}
	}

	want := checkpoints[len(checkpoints)-1]
	got, err := replicaA.LoadCheckpoint(context.Background(), consumer)
	if err != nil {
		t.Fatalf("load concurrent checkpoint: %v", err)
	}
	if got != want {
		t.Fatalf("checkpoint regressed after concurrent saves: got=%q want=%q", got, want)
	}

	if err := replicaB.SaveCheckpoint(context.Background(), consumer, checkpoints[0]); err != nil {
		t.Fatalf("save stale checkpoint: %v", err)
	}
	got, err = replicaB.LoadCheckpoint(context.Background(), consumer)
	if err != nil {
		t.Fatalf("reload after stale save: %v", err)
	}
	if got != want {
		t.Fatalf("late replica moved checkpoint backwards: got=%q want=%q", got, want)
	}
}

func TestMongoMediaProcessingLeaseHasSingleOwnerAndRejectsStaleCheckpointWrite(t *testing.T) {
	consumer := fmt.Sprintf("media-processing-lease-%d", time.Now().UnixNano())
	collection := mongoDB.Collection("media_projection_checkpoints")
	t.Cleanup(func() {
		_, _ = collection.DeleteOne(context.Background(), bson.M{"_id": consumer})
	})

	replicaA := persistence.NewMongoMediaStore(mongoDB)
	replicaB := persistence.NewMongoMediaStore(mongoDB)
	now := time.Date(2032, time.April, 5, 6, 7, 8, 0, time.UTC)
	ttl := 30 * time.Second

	acquired, err := replicaA.TryAcquireMediaProcessingLease(
		context.Background(),
		consumer,
		"replica-a",
		now,
		ttl,
	)
	if err != nil || !acquired {
		t.Fatalf("replica A acquire lease: acquired=%v err=%v", acquired, err)
	}
	acquired, err = replicaB.TryAcquireMediaProcessingLease(
		context.Background(),
		consumer,
		"replica-b",
		now.Add(time.Second),
		ttl,
	)
	if err != nil || acquired {
		t.Fatalf("replica B acquired active lease: acquired=%v err=%v", acquired, err)
	}

	first := mediaCheckpointForTest(now.Add(2*time.Second), "evt-001")
	advanced, err := replicaA.SaveMediaProcessingCheckpointWithLease(
		context.Background(),
		consumer,
		"replica-a",
		first,
		now.Add(2*time.Second),
		ttl,
	)
	if err != nil || !advanced {
		t.Fatalf("active owner advance checkpoint: advanced=%v err=%v", advanced, err)
	}

	takeoverAt := now.Add(33 * time.Second)
	acquired, err = replicaB.TryAcquireMediaProcessingLease(
		context.Background(),
		consumer,
		"replica-b",
		takeoverAt,
		ttl,
	)
	if err != nil || !acquired {
		t.Fatalf("replica B acquire expired lease: acquired=%v err=%v", acquired, err)
	}
	second := mediaCheckpointForTest(takeoverAt, "evt-002")
	advanced, err = replicaA.SaveMediaProcessingCheckpointWithLease(
		context.Background(),
		consumer,
		"replica-a",
		second,
		takeoverAt,
		ttl,
	)
	if err != nil || advanced {
		t.Fatalf("stale owner advanced checkpoint: advanced=%v err=%v", advanced, err)
	}
	advanced, err = replicaB.SaveMediaProcessingCheckpointWithLease(
		context.Background(),
		consumer,
		"replica-b",
		second,
		takeoverAt,
		ttl,
	)
	if err != nil || !advanced {
		t.Fatalf("takeover owner advance checkpoint: advanced=%v err=%v", advanced, err)
	}
	got, err := replicaA.LoadCheckpoint(context.Background(), consumer)
	if err != nil || got != second {
		t.Fatalf("checkpoint after lease takeover=%q err=%v want=%q", got, err, second)
	}
}

func mediaCheckpointForTest(occurredAt time.Time, eventID string) string {
	return occurredAt.UTC().Format(time.RFC3339Nano) + "|" + eventID
}
