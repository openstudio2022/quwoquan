package local_contract

import (
	"context"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	behavior "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

func validOccurredAt() string {
	return time.Now().UTC().Format(time.RFC3339Nano)
}

type fakeIntersectionFeedbackSink struct {
	calls     []intersectionFeedbackCall
	exposures []exposureCall
	clears    []exposureCall
	err       error
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

func (f *fakeIntersectionFeedbackSink) ReportExposure(_ context.Context, userID string, intersectionIDs []string) error {
	f.exposures = append(f.exposures, exposureCall{userID: userID, intersectionIDs: intersectionIDs})
	return f.err
}

func (f *fakeIntersectionFeedbackSink) ClearExposure(_ context.Context, userID string, intersectionIDs []string) error {
	f.clears = append(f.clears, exposureCall{userID: userID, intersectionIDs: intersectionIDs})
	return f.err
}

type exposureCall struct {
	userID          string
	intersectionIDs []string
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

	_, err := svc.ProcessBatch(context.Background(), []behavior.BehaviorEventInput{
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

// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-004.t1
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-004.t3
// 曝光→点击→转化→清零全链：真实曝光（impression/impressed + intersectionId）写曝光冷却，
// 点击 / 展开 / 转化清零；无 intersectionId 的普通内容事件与 visible 弱曝光都不触达冷却集。
func TestProcessBatchRoutesIntersectionExposureAndClearToSink(t *testing.T) {
	sink := &fakeIntersectionFeedbackSink{}
	svc := newFeedbackRoutingService(sink)
	base := func(id, action string) behavior.BehaviorEventInput {
		return behavior.BehaviorEventInput{
			ClientEventID:         id,
			OccurredAt:            validOccurredAt(),
			UserID:                "user-310",
			Action:                action,
			ContentID:             "post-ix-1",
			IntersectionID:        "ix-310",
			IntersectionDimension: "relationship",
			IntersectionClass:     "fact",
			IntersectionSourceRef: "sharedFollowees",
			IntersectionCohort:    "sha256:policy-cohort",
		}
	}
	impressed := base("evt-ix-impressed", "impression")
	impressed.State = "impressed"
	visible := base("evt-ix-visible", "impression")
	visible.State = "visible"
	plainImpression := behavior.BehaviorEventInput{
		ClientEventID: "evt-plain-impressed",
		OccurredAt:    validOccurredAt(),
		UserID:        "user-310",
		Action:        "impression",
		State:         "impressed",
		ContentID:     "post-plain",
	}
	clicked := base("evt-ix-click", "click")
	expanded := base("evt-ix-expand", "intersection_expand")
	followed := base("evt-ix-follow", "follow")
	followed.AuthorID = "author-1"

	receipt, err := svc.ProcessBatch(context.Background(), []behavior.BehaviorEventInput{
		impressed, visible, plainImpression, clicked, expanded, followed,
	})
	if err != nil {
		t.Fatalf("ProcessBatch: %v", err)
	}
	if receipt.AcceptedCount != 6 {
		t.Fatalf("want 6 accepted, got %+v", receipt)
	}
	if len(sink.exposures) != 1 || sink.exposures[0].userID != "user-310" ||
		len(sink.exposures[0].intersectionIDs) != 1 || sink.exposures[0].intersectionIDs[0] != "ix-310" {
		t.Fatalf("only the impressed intersection exposure may enter cooldown, got %+v", sink.exposures)
	}
	if len(sink.clears) != 3 {
		t.Fatalf("click/expand/follow must each clear the exposure, got %+v", sink.clears)
	}
	for _, clear := range sink.clears {
		if clear.userID != "user-310" || len(clear.intersectionIDs) != 1 || clear.intersectionIDs[0] != "ix-310" {
			t.Fatalf("clear must target the same intersectionId, got %+v", clear)
		}
	}
	if len(sink.calls) != 0 {
		t.Fatalf("funnel steps must not be mistaken for negative feedback, got %+v", sink.calls)
	}
}

func TestProcessBatchDoesNotRouteNonIntersectionFeedback(t *testing.T) {
	sink := &fakeIntersectionFeedbackSink{}
	svc := newFeedbackRoutingService(sink)

	_, err := svc.ProcessBatch(context.Background(), []behavior.BehaviorEventInput{
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

	if _, err := svc.ProcessBatch(context.Background(), []behavior.BehaviorEventInput{
		{UserID: "user-302", Action: "intersection_feedback", FeedbackKind: "notInterested"},
	}); err == nil {
		t.Fatalf("missing subjectId must be rejected")
	}
	if _, err := svc.ProcessBatch(context.Background(), []behavior.BehaviorEventInput{
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

	_, err := svc.ProcessBatch(context.Background(), []behavior.BehaviorEventInput{
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
	if _, err := svc.ProcessBatch(context.Background(), []behavior.BehaviorEventInput{
		{UserID: "user-wish-2", Action: "wishlist_add", ObjectKind: "homepage"},
	}); err == nil {
		t.Fatalf("missing objectId must be rejected")
	}
	if _, err := svc.ProcessBatch(context.Background(), []behavior.BehaviorEventInput{
		{UserID: "user-wish-2", Action: "wishlist_add", ObjectID: "homepage_west_lake"},
	}); err == nil {
		t.Fatalf("missing objectKind must be rejected")
	}
	if len(wishlist.events) != 0 {
		t.Fatalf("rejected wishlist events must not project, got %d", len(wishlist.events))
	}
}
