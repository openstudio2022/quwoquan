package searchindex

import (
	"context"
	"errors"
	"fmt"
	"testing"

	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/user-service/internal/domain/user/model"
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

// keysetLister is an in-memory ProfileLister that serves profiles in ascending
// user_id pages, mirroring the store's keyset pagination contract. listErr forces
// the read to fail.
type keysetLister struct {
	profiles []model.UserProfile // assumed sorted by UserID ascending
	listErr  error
}

func (l keysetLister) ListProfilesForIndex(_ context.Context, afterUserID string, limit int) ([]model.UserProfile, error) {
	if l.listErr != nil {
		return nil, l.listErr
	}
	out := make([]model.UserProfile, 0, limit)
	for _, p := range l.profiles {
		if p.UserID <= afterUserID {
			continue
		}
		out = append(out, p)
		if len(out) >= limit {
			break
		}
	}
	return out, nil
}

func mkProfile(id, accountState, status string) model.UserProfile {
	return model.UserProfile{
		UserID: id, Nickname: id, AccountState: accountState, Status: status,
	}
}

func TestBackfillIndexesEligibleOnly(t *testing.T) {
	lister := keysetLister{profiles: []model.UserProfile{
		mkProfile("u01", "active", "active"),
		mkProfile("u02", "anonymous", "active"),
		mkProfile("u03", "active", "suspended"),
		mkProfile("u04", "active", "active"),
	}}
	bulk := &recordingBulk{}

	report, err := Backfill(context.Background(), bulk, lister, 0)
	if err != nil {
		t.Fatalf("Backfill err=%v", err)
	}
	if !bulk.ensured {
		t.Fatalf("backfill must ensure the index first")
	}
	if report.TotalProfiles != 4 || report.IndexedProfiles != 2 || report.SkippedProfiles != 2 {
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
	if !gotIDs["u01"] || !gotIDs["u04"] {
		t.Fatalf("eligible profiles missing from backfill: %#v", gotIDs)
	}
	if gotIDs["u02"] || gotIDs["u03"] {
		t.Fatalf("ineligible profiles leaked into backfill: %#v", gotIDs)
	}
}

func TestBackfillPaginates(t *testing.T) {
	var profiles []model.UserProfile
	for i := 0; i < 5; i++ {
		profiles = append(profiles, mkProfile(fmt.Sprintf("u%02d", i), "active", "active"))
	}
	lister := keysetLister{profiles: profiles}
	bulk := &recordingBulk{}

	report, err := Backfill(context.Background(), bulk, lister, 2)
	if err != nil {
		t.Fatalf("Backfill err=%v", err)
	}
	if report.IndexedProfiles != 5 || report.TotalProfiles != 5 {
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
	lister := keysetLister{profiles: []model.UserProfile{mkProfile("u01", "active", "active")}}
	bulk := &recordingBulk{failEnsure: true}

	if _, err := Backfill(context.Background(), bulk, lister, 0); err == nil {
		t.Fatalf("expected EnsureIndex failure to propagate")
	}
	if len(bulk.events) != 0 {
		t.Fatalf("no docs should be written when EnsureIndex fails: %#v", bulk.events)
	}
}

func TestBackfillListErrorPropagates(t *testing.T) {
	lister := keysetLister{listErr: errors.New("query failed")}
	bulk := &recordingBulk{}

	if _, err := Backfill(context.Background(), bulk, lister, 0); err == nil {
		t.Fatalf("expected list failure to propagate")
	}
}

func TestBackfillNilInputsNoOp(t *testing.T) {
	if _, err := Backfill(context.Background(), nil, keysetLister{}, 0); err != nil {
		t.Fatalf("nil indexer must be a no-op, got %v", err)
	}
	if _, err := Backfill(context.Background(), &recordingBulk{}, nil, 0); err != nil {
		t.Fatalf("nil lister must be a no-op, got %v", err)
	}
}
