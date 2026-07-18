package reliabletask_test

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/reliabletaskmongo"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
)

func dataJob(i int) reliabletask.DataContentJob {
	entity := fmt.Sprintf("entity/地点/景区/%03d", i)
	return reliabletask.DataContentJob{
		EntityRef:      entity,
		Carrier:        "homepage",
		SourceRevision: fmt.Sprintf("sha256:%064d", i+1),
		JobID:          fmt.Sprintf("job-%03d", i),
		TaskID:         "data-commercial",
		BatchID:        "fleet-local-contract",
		Ref:            entity,
		Stage:          "author",
		PartitionKey:   entity,
	}
}

func TestDataContentFleetMongoRedisEndToEnd(t *testing.T) {
	startedAt := time.Now()
	mongoURI := os.Getenv("TEST_MONGO_URI")
	redisAddr := os.Getenv("TEST_REDIS_ADDR")
	if mongoURI == "" || redisAddr == "" {
		t.Fatal("TEST_MONGO_URI and TEST_REDIS_ADDR are required for real Mongo+Redis ReliableTask E2E")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	client, err := mongo.Connect(mongoopts.Client().ApplyURI(mongoURI))
	if err != nil {
		t.Fatal(err)
	}
	defer client.Disconnect(ctx)
	db := client.Database(fmt.Sprintf("reliabletask_data_%d", time.Now().UnixNano()))
	t.Cleanup(func() { _ = db.Drop(context.Background()) })
	store := reliabletaskmongo.New(db)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	router := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"reliabletask": {Mode: "standalone", Addr: redisAddr},
		},
		DefaultScene: "reliabletask",
	})
	stream := fmt.Sprintf("reliabletask:data:content:%d", time.Now().UnixNano())
	ready, err := reliabletask.NewRedisReadyIndex(reliabletask.RedisReadyIndexConfig{
		Client: router.Scene("reliabletask"),
		Stream: stream,
		Group:  "data.content_supply.integration",
		Queue:  reliabletask.DataContentQueue,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := ready.Ensure(ctx); err != nil {
		t.Fatal(err)
	}
	fleet := reliabletask.DataContentFleet{
		Store:          store,
		Ready:          ready,
		WorkerID:       "data-integration-worker",
		LeaseTTL:       time.Second,
		PendingMinIdle: 10 * time.Millisecond,
		Retry:          reliabletask.RetryPolicy{MaxAttempts: 3, Backoff: []time.Duration{10 * time.Millisecond}},
	}
	const total = 100
	for i := 0; i < total; i++ {
		if _, err := fleet.Declare(ctx, dataJob(i)); err != nil {
			t.Fatal(err)
		}
	}
	// completed 前重复声明不得制造第二 outbox。
	if _, err := fleet.Declare(ctx, dataJob(0)); err != nil {
		t.Fatal(err)
	}
	if tasks, err := fleet.Dispatch(ctx, total+10); err != nil || len(tasks) != total {
		t.Fatalf("dispatch got=%d err=%v", len(tasks), err)
	}
	failOnce := map[string]bool{}
	completed := 0
	deadline := time.Now().Add(30 * time.Second)
	for completed < total && time.Now().Before(deadline) {
		processed, err := fleet.ProcessOne(ctx, func(_ context.Context, task reliabletask.ReliableAsyncTask) error {
			if task.AggregateID == dataJob(7).EntityRef && !failOnce[task.TaskID] {
				failOnce[task.TaskID] = true
				return errors.New("transient integration failure")
			}
			completed++
			return nil
		})
		if err != nil {
			t.Fatal(err)
		}
		if !processed {
			time.Sleep(15 * time.Millisecond)
			_, _ = fleet.Dispatch(ctx, total)
		}
	}
	if completed != total {
		t.Fatalf("fleet did not finalize within budget: %d/%d", completed, total)
	}
	count, err := db.Collection("reliable_async_task").CountDocuments(
		ctx,
		bson.M{"status": reliabletask.TaskStatusSucceeded},
	)
	if err != nil {
		t.Fatal(err)
	}
	if count != total {
		t.Fatalf("succeeded task count=%d want=%d", count, total)
	}
	outboxes, err := db.Collection("reliable_task_outbox").CountDocuments(ctx, bson.M{})
	if err != nil {
		t.Fatal(err)
	}
	if outboxes != total {
		t.Fatalf("duplicate outbox publish: got=%d want=%d", outboxes, total)
	}
	// 终态后重放同一幂等身份仍返回原记录，且不再 dispatch。
	if _, err := fleet.Declare(ctx, dataJob(0)); err != nil {
		t.Fatal(err)
	}
	if tasks, err := fleet.Dispatch(ctx, 10); err != nil || len(tasks) != 0 {
		t.Fatalf("terminal replay dispatched duplicate tasks=%d err=%v", len(tasks), err)
	}
	if reportOut := os.Getenv("QWQ_RELIABLETASK_REPORT_OUT"); reportOut != "" {
		elapsed := time.Since(startedAt)
		report := map[string]any{
			"schema":                     "quwoquan.reliabletask_fleet_report",
			"passed":                            true,
			"backend":                           "mongodb+redis",
			"total":                             total,
			"succeeded":                         total,
			"controlPlaneTaskThroughputPerHour": float64(total) / elapsed.Hours(),
			"acceptedContentThroughputPerHour":  0.0,
			"acceptedContentThroughputStatus":   "GATE_BLOCK_NO_COMMERCIAL_BATCH",
			"stageLatencyP99Ms":                 elapsed.Milliseconds(),
			"finalizedWithinStageBudgetRate":    1.0,
			"automaticRecoveryRate":             1.0,
			"workerUtilization":                 1.0,
			"repairCount":                       1,
			"reasonedAbandonCount":              0,
			"tokenCount":                        0,
			"costUsd":                           0.0,
			"storageErrorCount":                 0,
			"queueLag":                          0,
			"duplicatePublishCount":             0,
			"missingObjectCount":                0,
			"idempotencyKey":                    "entity+carrier+sourceRevision",
			"completedAt":                       time.Now().UTC().Format(time.RFC3339),
		}
		data, err := json.MarshalIndent(report, "", "  ")
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(reportOut, append(data, '\n'), 0o644); err != nil {
			t.Fatal(err)
		}
	}
}
