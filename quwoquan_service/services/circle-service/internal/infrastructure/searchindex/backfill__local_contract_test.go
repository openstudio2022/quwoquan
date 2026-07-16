package searchindex

import (
	"context"
	"errors"
	"fmt"
	"testing"

	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/circle-service/internal/application"
	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
)

// recordingBulk captures backfill writes through the BulkIndexer contract.
type recordingBulk struct {
	ensured    bool
	events     []es.ChangeEvent
	failEnsure bool
	failBulk   bool
	bulkCalls  int
}

func (b *recordingBulk) EnsureIndex(_ context.Context) error {
	if b.failEnsure {
		return errors.New("ensure failed")
	}
	b.ensured = true
	return nil
}

func (b *recordingBulk) Bulk(_ context.Context, _ string, events []es.ChangeEvent) error {
	if b.failBulk {
		return errors.New("bulk failed")
	}
	b.bulkCalls++
	b.events = append(b.events, events...)
	return nil
}

// pagedLister is an in-memory CircleLister that serves circles in cursor pages of
// the requested limit, mirroring the store's pagination contract.
type pagedLister struct {
	circles []model.Circle
}

func (l pagedLister) List(_ context.Context, opts application.ListCirclesQuery) ([]model.Circle, string) {
	start := 0
	if opts.Cursor != "" {
		if _, err := fmt.Sscanf(opts.Cursor, "off:%d", &start); err != nil {
			start = 0
		}
	}
	limit := opts.Limit
	if limit <= 0 {
		limit = len(l.circles)
	}
	end := start + limit
	if end > len(l.circles) {
		end = len(l.circles)
	}
	page := l.circles[start:end]
	next := ""
	if end < len(l.circles) {
		next = fmt.Sprintf("off:%d", end)
	}
	return page, next
}

func mkCircle(id, status, visibility string) model.Circle {
	return model.Circle{
		ID: id, Name: id, Category: "outdoor",
		Status:     model.CircleStatus(status),
		Visibility: model.CircleVisibility(visibility),
	}
}

func TestBackfillIndexesEligibleOnly(t *testing.T) {
	lister := pagedLister{circles: []model.Circle{
		mkCircle("c_pub", "active", "public"),
		mkCircle("c_archived", "archived", "public"),
		mkCircle("c_priv", "active", "private"),
		mkCircle("c_pub2", "active", "public"),
	}}
	bulk := &recordingBulk{}

	report, err := Backfill(context.Background(), bulk, lister, 0)
	if err != nil {
		t.Fatalf("Backfill err=%v", err)
	}
	if !bulk.ensured {
		t.Fatalf("backfill must ensure the index first")
	}
	if report.TotalCircles != 4 || report.IndexedCircles != 2 || report.SkippedCircles != 2 {
		t.Fatalf("unexpected report: %#v", report)
	}
	if len(bulk.events) != 2 {
		t.Fatalf("expected 2 indexed events, got %d", len(bulk.events))
	}
	gotIDs := map[string]bool{}
	for _, ev := range bulk.events {
		if ev.Op != es.OpUpsert {
			t.Fatalf("backfill must upsert, got op=%s", ev.Op)
		}
		gotIDs[ev.Doc.ObjectID] = true
	}
	if !gotIDs["c_pub"] || !gotIDs["c_pub2"] {
		t.Fatalf("eligible circles missing from backfill: %#v", gotIDs)
	}
	if gotIDs["c_archived"] || gotIDs["c_priv"] {
		t.Fatalf("ineligible circles leaked into backfill: %#v", gotIDs)
	}
}

func TestBackfillPaginates(t *testing.T) {
	var circles []model.Circle
	for i := 0; i < 5; i++ {
		circles = append(circles, mkCircle(fmt.Sprintf("c%d", i), "active", "public"))
	}
	lister := pagedLister{circles: circles}
	bulk := &recordingBulk{}

	report, err := Backfill(context.Background(), bulk, lister, 2)
	if err != nil {
		t.Fatalf("Backfill err=%v", err)
	}
	if report.IndexedCircles != 5 || report.TotalCircles != 5 {
		t.Fatalf("expected 5 indexed/total, got %#v", report)
	}
	if bulk.bulkCalls != 3 { // pages of 2 + 2 + 1
		t.Fatalf("expected 3 bulk round trips for batchSize=2, got %d", bulk.bulkCalls)
	}
	if report.BatchesPushed != 3 {
		t.Fatalf("expected report.BatchesPushed=3, got %d", report.BatchesPushed)
	}
}

func TestBackfillEnsureIndexFailurePropagates(t *testing.T) {
	lister := pagedLister{circles: []model.Circle{mkCircle("c_pub", "active", "public")}}
	bulk := &recordingBulk{failEnsure: true}

	if _, err := Backfill(context.Background(), bulk, lister, 0); err == nil {
		t.Fatalf("expected EnsureIndex failure to propagate")
	}
	if len(bulk.events) != 0 {
		t.Fatalf("no docs should be written when EnsureIndex fails: %#v", bulk.events)
	}
}

func TestBackfillNilInputsNoOp(t *testing.T) {
	if _, err := Backfill(context.Background(), nil, pagedLister{}, 0); err != nil {
		t.Fatalf("nil indexer must be a no-op, got %v", err)
	}
	if _, err := Backfill(context.Background(), &recordingBulk{}, nil, 0); err != nil {
		t.Fatalf("nil lister must be a no-op, got %v", err)
	}
}
