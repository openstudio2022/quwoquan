package api_integration

import (
	"context"
	"errors"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/internal/platform/testinfra"
	visitapp "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/application"
	visitmodel "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/domain/model"
	visitpersistence "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

const visitOutboxCollection = "followed_subject_visit_outbox"

type recordingVisitPublisher struct {
	delivered []visitmodel.OutboxEvent
	fail      bool
}

func (p *recordingVisitPublisher) PublishFollowedSubjectVisited(
	_ context.Context,
	event visitmodel.OutboxEvent,
) error {
	if p.fail {
		return errors.New("consumer unavailable")
	}
	p.delivered = append(p.delivered, event)
	return nil
}

func newVisitStore(
	ctx context.Context,
	t *testing.T,
	runtime *testinfra.RealMongo,
) *visitpersistence.MongoFollowedSubjectVisitStore {
	t.Helper()
	store := visitpersistence.NewMongoFollowedSubjectVisitStore(runtime.Database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure visit state indexes: %v", err)
	}
	return store
}

func countVisitOutbox(
	ctx context.Context,
	t *testing.T,
	runtime *testinfra.RealMongo,
	filter bson.M,
) int64 {
	t.Helper()
	total, err := runtime.Database.Collection(visitOutboxCollection).CountDocuments(ctx, filter)
	if err != nil {
		t.Fatalf("count visit outbox: %v", err)
	}
	return total
}

// 水位与 FollowedSubjectVisited 必须在同一个真实 Mongo 事务内提交，且重放
// 同一 clientRequestId 不产生第二条事件。
func TestFollowedSubjectVisitCommitsStateAndOutboxInOneTransaction(t *testing.T) {
	usersupport.WithUserMongo(t, func(ctx context.Context, runtime *testinfra.RealMongo) {
		store := newVisitStore(ctx, t, runtime)
		service := visitapp.NewVisitService(store)
		input := visitapp.MarkVisitedInput{
			PersonaID: "persona-viewer", SubjectType: "homepage", SubjectID: "homepage-1",
			VisitedAt: time.Now().UTC(), ClientRequestID: "visit-request-1",
		}
		if _, err := service.MarkVisited(ctx, input); err != nil {
			t.Fatalf("mark visited: %v", err)
		}
		if total := countVisitOutbox(ctx, t, runtime, bson.M{}); total != 1 {
			t.Fatalf("expected exactly one outbox event, got %d", total)
		}
		if _, err := service.MarkVisited(ctx, input); err != nil {
			t.Fatalf("replay mark visited: %v", err)
		}
		if total := countVisitOutbox(ctx, t, runtime, bson.M{}); total != 1 {
			t.Fatalf("replay must not append a second event, got %d", total)
		}

		second := input
		second.ClientRequestID = "visit-request-2"
		second.VisitedAt = input.VisitedAt.Add(time.Minute)
		if _, err := service.MarkVisited(ctx, second); err != nil {
			t.Fatalf("second mark visited: %v", err)
		}
		if total := countVisitOutbox(ctx, t, runtime, bson.M{}); total != 2 {
			t.Fatalf("expected two outbox events, got %d", total)
		}
	})
}

// outbox 写入失败必须连同已写入的水位一起回滚，不允许出现「状态已提交但
// 事件丢失」。这里用真实 Mongo 的集合校验器让事务内的 outbox 插入失败。
func TestFollowedSubjectVisitAbortLeavesNeitherStateNorEvent(t *testing.T) {
	usersupport.WithUserMongo(t, func(ctx context.Context, runtime *testinfra.RealMongo) {
		if err := runtime.Database.CreateCollection(
			ctx,
			visitOutboxCollection,
			options.CreateCollection().SetValidator(bson.M{
				"$jsonSchema": bson.M{
					"bsonType": "object",
					"required": []string{"neverWrittenField"},
				},
			}),
		); err != nil {
			t.Fatalf("create rejecting outbox collection: %v", err)
		}
		store := newVisitStore(ctx, t, runtime)
		service := visitapp.NewVisitService(store)
		if _, err := service.MarkVisited(ctx, visitapp.MarkVisitedInput{
			PersonaID: "persona-viewer", SubjectType: "homepage", SubjectID: "homepage-1",
			VisitedAt: time.Now().UTC(), ClientRequestID: "visit-request-1",
		}); err == nil {
			t.Fatal("expected the rejected outbox write to fail the command")
		}
		if total := countVisitOutbox(ctx, t, runtime, bson.M{}); total != 0 {
			t.Fatalf("aborted command must not leave an event, got %d", total)
		}
		states, err := runtime.Database.
			Collection("followed_subject_visit_states").
			CountDocuments(ctx, bson.M{})
		if err != nil {
			t.Fatalf("count visit states: %v", err)
		}
		if states != 0 {
			t.Fatalf("aborted command must not leave state, got %d", states)
		}
	})
}

// relay 必须在消费者确认后才标记已投递；消费失败时事件留在 outbox，
// 进程重启后仍能重放（至少一次），投影侧以幂等收敛。
func TestFollowedSubjectVisitOutboxSurvivesFailedDeliveryAndReplays(t *testing.T) {
	usersupport.WithUserMongo(t, func(ctx context.Context, runtime *testinfra.RealMongo) {
		store := newVisitStore(ctx, t, runtime)
		service := visitapp.NewVisitService(store)
		if _, err := service.MarkVisited(ctx, visitapp.MarkVisitedInput{
			PersonaID: "persona-viewer", SubjectType: "persona", SubjectID: "persona-target",
			VisitedAt: time.Now().UTC(), ClientRequestID: "visit-request-1",
		}); err != nil {
			t.Fatalf("mark visited: %v", err)
		}

		failing := &recordingVisitPublisher{fail: true}
		if _, err := visitapp.NewOutboxRelay(store, failing).Drain(ctx, 10); err == nil {
			t.Fatal("expected failing consumer to surface an error")
		}
		if total := countVisitOutbox(ctx, t, runtime, bson.M{"publishedAt": nil}); total != 1 {
			t.Fatalf("failed delivery must leave the event pending, got %d", total)
		}

		// 新的 relay 实例模拟进程重启：租约已释放，事件必须被重新认领。
		recovered := &recordingVisitPublisher{}
		drained, err := visitapp.NewOutboxRelay(store, recovered).Drain(ctx, 10)
		if err != nil || drained != 1 {
			t.Fatalf("replay drain: drained=%d err=%v", drained, err)
		}
		if len(recovered.delivered) != 1 {
			t.Fatalf("expected one replayed delivery, got %d", len(recovered.delivered))
		}
		delivered := recovered.delivered[0]
		if delivered.EventName != visitmodel.EventFollowedSubjectVisited ||
			delivered.Payload.PersonaID != "persona-viewer" ||
			delivered.Payload.SubjectID != "persona-target" {
			t.Fatalf("replayed payload drifted: %+v", delivered)
		}
		if total := countVisitOutbox(ctx, t, runtime, bson.M{"publishedAt": nil}); total != 0 {
			t.Fatalf("acknowledged event must not stay pending, got %d", total)
		}

		// 已确认的事件不得被再次认领，避免无界重复投递。
		again, err := visitapp.NewOutboxRelay(store, &recordingVisitPublisher{}).Drain(ctx, 10)
		if err != nil || again != 0 {
			t.Fatalf("published event must not be reclaimed: drained=%d err=%v", again, err)
		}
	})
}

// 租约被其它 relay 抢走后，原持有者不得确认投递，避免丢事件。
func TestFollowedSubjectVisitOutboxRejectsAcknowledgeFromLostLease(t *testing.T) {
	usersupport.WithUserMongo(t, func(ctx context.Context, runtime *testinfra.RealMongo) {
		store := newVisitStore(ctx, t, runtime)
		service := visitapp.NewVisitService(store)
		if _, err := service.MarkVisited(ctx, visitapp.MarkVisitedInput{
			PersonaID: "persona-viewer", SubjectType: "circle", SubjectID: "circle-1",
			VisitedAt: time.Now().UTC(), ClientRequestID: "visit-request-1",
		}); err != nil {
			t.Fatalf("mark visited: %v", err)
		}
		claimed, err := store.ClaimPendingOutbox(ctx, "owner-a", time.Minute, 10)
		if err != nil || len(claimed) != 1 {
			t.Fatalf("claim: claimed=%d err=%v", len(claimed), err)
		}
		if err := store.MarkOutboxPublished(ctx, claimed[0].EventID, "owner-b"); err == nil {
			t.Fatal("a non-owner must not acknowledge the event")
		}
		if err := store.MarkOutboxPublished(ctx, claimed[0].EventID, "owner-a"); err != nil {
			t.Fatalf("lease owner acknowledge: %v", err)
		}
	})
}
