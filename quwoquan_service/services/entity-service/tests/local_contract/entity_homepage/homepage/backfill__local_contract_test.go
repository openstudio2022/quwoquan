package local_contract

import (
	"context"
	"errors"
	"fmt"
	. "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/searchindex"
	"strconv"
	"testing"

	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
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

// fakeLister is an in-memory HomepageLister for backfill tests.
type fakeLister struct {
	homepages []application.Homepage
}

func (l fakeLister) ScanHomepagesForIndex(
	_ context.Context,
	cursor string,
	limit int,
) ([]application.Homepage, string, error) {
	start := 0
	if cursor != "" {
		start, _ = strconv.Atoi(cursor)
	}
	if limit <= 0 {
		limit = len(l.homepages)
	}
	end := start + limit
	if end > len(l.homepages) {
		end = len(l.homepages)
	}
	next := ""
	if end < len(l.homepages) {
		next = strconv.Itoa(end)
	}
	return append([]application.Homepage(nil), l.homepages[start:end]...), next, nil
}

func mkHomepage(id, status string) application.Homepage {
	return application.Homepage{
		ID: id, Title: id, HomepageType: "sight",
		CanonicalEntityID: "entity:sight:" + id, Status: status,
	}
}

func TestBackfillIndexesEligibleOnly(t *testing.T) {
	lister := fakeLister{homepages: []application.Homepage{
		mkHomepage("hp_pub", "published"),
		mkHomepage("hp_draft", "candidate"),
		mkHomepage("hp_off", "offline"),
		mkHomepage("hp_pub2", "published"),
	}}
	bulk := &recordingBulk{}

	report, err := Backfill(context.Background(), bulk, lister, 0)
	if err != nil {
		t.Fatalf("Backfill err=%v", err)
	}
	if !bulk.ensured {
		t.Fatalf("backfill must ensure the index first")
	}
	if report.TotalHomepages != 4 ||
		report.IndexedHomepages != 2 ||
		report.DeletedHomepages != 2 {
		t.Fatalf("unexpected report: %#v", report)
	}
	if len(bulk.events) != 4 {
		t.Fatalf("expected 4 reconcile events, got %d", len(bulk.events))
	}
	gotIDs := map[string]bool{}
	for _, ev := range bulk.events {
		gotIDs[string(ev.Op)+":"+ev.Doc.ObjectID] = true
	}
	if !gotIDs["upsert:hp_pub"] || !gotIDs["upsert:hp_pub2"] {
		t.Fatalf("eligible homepages missing from backfill: %#v", gotIDs)
	}
	if !gotIDs["delete:hp_draft"] || !gotIDs["delete:hp_off"] {
		t.Fatalf("ineligible homepages were not deleted: %#v", gotIDs)
	}
}

func TestBackfillBatches(t *testing.T) {
	var homepages []application.Homepage
	for i := 0; i < 5; i++ {
		homepages = append(homepages, mkHomepage(fmt.Sprintf("hp%d", i), "published"))
	}
	lister := fakeLister{homepages: homepages}
	bulk := &recordingBulk{}

	report, err := Backfill(context.Background(), bulk, lister, 2)
	if err != nil {
		t.Fatalf("Backfill err=%v", err)
	}
	if report.IndexedHomepages != 5 {
		t.Fatalf("expected 5 indexed, got %d", report.IndexedHomepages)
	}
	if bulk.bulkCalls != 3 { // 2 + 2 + 1
		t.Fatalf("expected 3 bulk round trips for batchSize=2, got %d", bulk.bulkCalls)
	}
	if report.BatchesPushed != 3 {
		t.Fatalf("expected report.BatchesPushed=3, got %d", report.BatchesPushed)
	}
}

func TestBackfillEnsureIndexFailurePropagates(t *testing.T) {
	lister := fakeLister{homepages: []application.Homepage{mkHomepage("hp_pub", "published")}}
	bulk := &recordingBulk{failEnsure: true}

	if _, err := Backfill(context.Background(), bulk, lister, 0); err == nil {
		t.Fatalf("expected EnsureIndex failure to propagate")
	}
	if len(bulk.events) != 0 {
		t.Fatalf("no docs should be written when EnsureIndex fails: %#v", bulk.events)
	}
}

func TestBackfillMissingInputsFailFast(t *testing.T) {
	if _, err := Backfill(context.Background(), nil, fakeLister{}, 0); err == nil {
		t.Fatal("nil indexer must fail")
	}
	if _, err := Backfill(context.Background(), &recordingBulk{}, nil, 0); err == nil {
		t.Fatal("nil lister must fail")
	}
}
