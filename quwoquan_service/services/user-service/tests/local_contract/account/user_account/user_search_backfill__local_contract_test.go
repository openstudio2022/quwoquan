package local_contract

import (
	"context"
	"testing"

	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/searchindex"
)

type profileSearchBackfillLister struct {
	profiles []model.UserProfile
}

func (l profileSearchBackfillLister) ListProfilesForIndex(
	_ context.Context,
	afterUserID string,
	limit int,
) ([]model.UserProfile, error) {
	start := 0
	for start < len(l.profiles) && l.profiles[start].UserID <= afterUserID {
		start++
	}
	end := start + limit
	if end > len(l.profiles) {
		end = len(l.profiles)
	}
	return l.profiles[start:end], nil
}

type profileSearchBackfillIndexer struct {
	ensured bool
	events  []es.ChangeEvent
}

func (i *profileSearchBackfillIndexer) EnsureIndex(context.Context) error {
	i.ensured = true
	return nil
}

func (i *profileSearchBackfillIndexer) Bulk(
	_ context.Context,
	_ string,
	events []es.ChangeEvent,
) error {
	i.events = append(i.events, events...)
	return nil
}

func TestUserSearchBackfillReconcilesEveryAccountState(t *testing.T) {
	lister := profileSearchBackfillLister{profiles: []model.UserProfile{
		{UserID: "active", AccountState: "active", Status: "active"},
		{UserID: "closed", AccountState: "closed", Status: "active"},
		{UserID: "suspended", AccountState: "active", Status: "suspended"},
	}}
	indexer := &profileSearchBackfillIndexer{}

	report, err := searchindex.Backfill(context.Background(), indexer, lister, 2)
	if err != nil {
		t.Fatalf("Backfill error: %v", err)
	}
	if !indexer.ensured {
		t.Fatal("backfill must ensure the index")
	}
	if report.TotalProfiles != 3 ||
		report.IndexedProfiles != 1 ||
		report.DeletedProfiles != 2 ||
		report.BatchesPushed != 2 {
		t.Fatalf("unexpected report: %#v", report)
	}
	got := map[string]es.ChangeOp{}
	for _, event := range indexer.events {
		got[event.Doc.ObjectID] = event.Op
	}
	if got["active"] != es.OpUpsert ||
		got["closed"] != es.OpDelete ||
		got["suspended"] != es.OpDelete {
		t.Fatalf("unexpected reconcile operations: %#v", got)
	}
}

func TestUserSearchBackfillMissingInputsFailFast(t *testing.T) {
	if _, err := searchindex.Backfill(
		context.Background(),
		nil,
		profileSearchBackfillLister{},
		1,
	); err == nil {
		t.Fatal("nil indexer must fail")
	}
	if _, err := searchindex.Backfill(
		context.Background(),
		&profileSearchBackfillIndexer{},
		nil,
		1,
	); err == nil {
		t.Fatal("nil lister must fail")
	}
}
