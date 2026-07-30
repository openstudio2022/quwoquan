package local_contract

import (
	"context"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	behavior "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

func validOccurredAt() string {
	return time.Now().UTC().Format(time.RFC3339Nano)
}

type fakeIntersectionFeedbackSink struct {
	calls []intersectionFeedbackCall
	err   error
}

type intersectionFeedbackCall struct {
	userID       string
	subjectID    string
	feedbackKind string
}

func (f *fakeIntersectionFeedbackSink) ReportNegativeFeedback(_ context.Context, userID, subjectID, feedbackKind string) error {
	f.calls = append(f.calls, intersectionFeedbackCall{userID: userID, subjectID: subjectID, feedbackKind: feedbackKind})
	return f.err
}

type fakeSignalProcessor struct {
	batches [][]rtrec.BehaviorSignal
}

type fakeWishlistStore struct {
	events []ports.WishlistEvent
}

func (f *fakeSignalProcessor) ProcessSignal(_ context.Context, signal rtrec.BehaviorSignal) error {
	f.batches = append(f.batches, []rtrec.BehaviorSignal{signal})
	return nil
}

func (f *fakeSignalProcessor) ProcessSignalBatch(_ context.Context, signals []rtrec.BehaviorSignal) error {
	f.batches = append(f.batches, signals)
	return nil
}

func (f *fakeWishlistStore) UpsertWishlistEvent(_ context.Context, event ports.WishlistEvent) error {
	f.events = append(f.events, event)
	return nil
}

func newFeedbackRoutingService(sink behavior.IntersectionFeedbackSink) *behavior.BehaviorService {
	processor := &fakeSignalProcessor{}
	store := persistence.NewPostStore([]postmodel.Post{})
	return behavior.NewBehaviorService(processor, store, behavior.WithIntersectionFeedbackSink(sink))
}

func TestProcessBatchRoutesIntersectionFeedbackToSink(t *testing.T) {
	sink := &fakeIntersectionFeedbackSink{}
	svc := newFeedbackRoutingService(sink)

	err := svc.ProcessBatch(context.Background(), []behavior.BehaviorEventInput{
		{
			ClientEventID:         "evt-intersection-feedback-001",
			OccurredAt:            validOccurredAt(),
			UserID:                "user-300",
			Action:                "intersection_feedback",
			SubjectID:             "subj-1",
			FeedbackKind:          "notInterested",
			IntersectionID:        "ix-1",
			IntersectionDimension: "relationship",
			IntersectionClass:     "fact",
		},
	})
	if err != nil {
		t.Fatalf("ProcessBatch: %v", err)
	}
	if len(sink.calls) != 1 {
		t.Fatalf("want 1 sink call, got %d", len(sink.calls))
	}
	got := sink.calls[0]
	if got.userID != "user-300" || got.subjectID != "subj-1" || got.feedbackKind != "notInterested" {
		t.Fatalf("unexpected sink call: %+v", got)
	}
}

func TestProcessBatchDoesNotRouteNonIntersectionFeedback(t *testing.T) {
	sink := &fakeIntersectionFeedbackSink{}
	svc := newFeedbackRoutingService(sink)

	err := svc.ProcessBatch(context.Background(), []behavior.BehaviorEventInput{
		{
			ClientEventID: "evt-dislike-001",
			OccurredAt:    validOccurredAt(),
			UserID:        "user-301",
			Action:        "dislike",
			ContentID:     "post-1",
		},
	})
	if err != nil {
		t.Fatalf("ProcessBatch: %v", err)
	}
	if len(sink.calls) != 0 {
		t.Fatalf("non-intersection feedback must not route to sink, got %d", len(sink.calls))
	}
}

func TestProcessBatchRejectsInvalidIntersectionFeedback(t *testing.T) {
	sink := &fakeIntersectionFeedbackSink{}
	svc := newFeedbackRoutingService(sink)

	if err := svc.ProcessBatch(context.Background(), []behavior.BehaviorEventInput{
		{UserID: "user-302", Action: "intersection_feedback", FeedbackKind: "notInterested"},
	}); err == nil {
		t.Fatalf("missing subjectId must be rejected")
	}
	if err := svc.ProcessBatch(context.Background(), []behavior.BehaviorEventInput{
		{UserID: "user-302", Action: "intersection_feedback", SubjectID: "subj-1", FeedbackKind: "bogus_kind"},
	}); err == nil {
		t.Fatalf("invalid feedbackKind must be rejected")
	}
	if len(sink.calls) != 0 {
		t.Fatalf("rejected events must not write cooldown, got %d", len(sink.calls))
	}
}

func TestProcessBatchProjectsWishlistAddAndRemove(t *testing.T) {
	wishlist := &fakeWishlistStore{}
	processor := &fakeSignalProcessor{}
	svc := behavior.NewBehaviorService(
		processor,
		persistence.NewPostStore([]postmodel.Post{}),
		behavior.WithWishlistEventStore(wishlist),
	)

	err := svc.ProcessBatch(context.Background(), []behavior.BehaviorEventInput{
		{
			OccurredAt:     validOccurredAt(),
			UserID:         "user-wish-1",
			SessionID:      "sess-wish-1",
			ClientEventID:  "evt-wish-add-1",
			Action:         "wishlist_add",
			ObjectID:       "homepage_west_lake",
			ObjectKind:     "homepage",
			DisplayName:    "西湖日落机位",
			SourceSurface:  "object_homepage",
			ReferralSource: "entity_page",
			FeedRequestID:  "frq_wish_1",
		},
		{
			UserID:        "user-wish-1",
			SessionID:     "sess-wish-1",
			ClientEventID: "evt-wish-remove-1",
			OccurredAt:    validOccurredAt(),
			Action:        "wishlist_remove",
			ObjectID:      "homepage_west_lake",
			ObjectKind:    "homepage",
		},
	})
	if err != nil {
		t.Fatalf("ProcessBatch: %v", err)
	}
	if len(wishlist.events) != 2 {
		t.Fatalf("want 2 wishlist projections, got %d", len(wishlist.events))
	}
	add := wishlist.events[0]
	if add.UserID != "user-wish-1" || add.EntityID != "homepage_west_lake" || add.ObjectType != "homepage" {
		t.Fatalf("unexpected add projection identity: %+v", add)
	}
	if add.Status != "active" || add.DisplayName != "西湖日落机位" || add.SourceSurface != "object_homepage" || add.FeedRequestID != "frq_wish_1" {
		t.Fatalf("unexpected add projection payload: %+v", add)
	}
	remove := wishlist.events[1]
	if remove.Status != "removed" || remove.EntityID != "homepage_west_lake" {
		t.Fatalf("unexpected remove projection: %+v", remove)
	}
	if len(processor.batches) == 0 || len(processor.batches[0]) != 2 {
		t.Fatalf("wishlist events must still enter behavior signal batch, got %+v", processor.batches)
	}
}

func TestProcessBatchRejectsInvalidWishlistEvent(t *testing.T) {
	wishlist := &fakeWishlistStore{}
	svc := behavior.NewBehaviorService(
		&fakeSignalProcessor{},
		persistence.NewPostStore([]postmodel.Post{}),
		behavior.WithWishlistEventStore(wishlist),
	)
	if err := svc.ProcessBatch(context.Background(), []behavior.BehaviorEventInput{
		{UserID: "user-wish-2", Action: "wishlist_add", ObjectKind: "homepage"},
	}); err == nil {
		t.Fatalf("missing objectId must be rejected")
	}
	if err := svc.ProcessBatch(context.Background(), []behavior.BehaviorEventInput{
		{UserID: "user-wish-2", Action: "wishlist_add", ObjectID: "homepage_west_lake"},
	}); err == nil {
		t.Fatalf("missing objectKind must be rejected")
	}
	if len(wishlist.events) != 0 {
		t.Fatalf("rejected wishlist events must not project, got %d", len(wishlist.events))
	}
}
