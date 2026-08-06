// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/product-control-plane-contract/spec.md#gwt-002
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/domain/ports"
)

// readiness_case: upsert-premium-pool-entry-local
// readiness_case: rollback-premium-pool-entry-local
// readiness_case: takedown-premium-pool-entry-local
func TestPremiumPoolEntryOwnsOneThreeStateLifecycle(t *testing.T) {
	now := time.Date(2026, 8, 2, 10, 0, 0, 0, time.UTC)
	active, err := model.Upsert(nil, model.UpsertInput{
		ContentID: "post-1", Scope: "global", QualityScore: 0.92,
		QualityAdmission: "approved", AuditID: "audit-1",
		ExpiresAt: now.Add(24 * time.Hour),
	}, now)
	if err != nil {
		t.Fatal(err)
	}
	if active.Status != model.StatusActive || active.Revision != 1 || !active.ActiveAt(now) {
		t.Fatalf("unexpected active aggregate: %+v", active)
	}
	rolledBack, err := active.Rollback(now.Add(time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	if rolledBack.Status != model.StatusRolledBack || rolledBack.Revision != 2 || rolledBack.TakedownEjected() {
		t.Fatalf("unexpected rollback aggregate: %+v", rolledBack)
	}
	if _, err := rolledBack.Takedown(now.Add(2 * time.Minute)); !errors.Is(err, model.ErrInvalidTransition) {
		t.Fatalf("rolled-back entry takedown error=%v, want ErrInvalidTransition", err)
	}

	reactivated, err := model.Upsert(&rolledBack, model.UpsertInput{
		ContentID: "post-1", Scope: "global", QualityScore: 0.95,
		QualityAdmission: "approved", AuditID: "audit-2",
		ExpiresAt: now.Add(48 * time.Hour),
	}, now.Add(3*time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	ejected, err := reactivated.Takedown(now.Add(4 * time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	if ejected.Status != model.StatusTakedownEjected || !ejected.TakedownEjected() || ejected.Revision != 4 {
		t.Fatalf("unexpected takedown aggregate: %+v", ejected)
	}
}

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/product-control-plane-contract/spec.md#gwt-002
// readiness_case: list-premium-pool-entries-local
func TestPremiumPoolListUsesTheObjectOwnedStoreAndActiveFilter(t *testing.T) {
	now := time.Now().UTC()
	active, err := model.Upsert(nil, model.UpsertInput{
		ContentID: "post-list-active", Scope: "global", QualityScore: 0.92,
		QualityAdmission: "approved", AuditID: "audit-list-active",
		ExpiresAt: now.Add(time.Hour),
	}, now)
	if err != nil {
		t.Fatal(err)
	}
	expired := active
	expired.ContentID = "post-list-expired"
	expired.ExpiresAt = now.Add(-time.Hour)
	service := application.NewService(&readinessPremiumStore{
		entries: []model.Entry{expired, active},
	})
	items, err := service.List(context.Background(), true)
	if err != nil || len(items) != 1 || items[0].ContentID != active.ContentID {
		t.Fatalf("List(activeOnly) = %+v, %v", items, err)
	}
}

type readinessPremiumStore struct {
	entries []model.Entry
}

func (store *readinessPremiumStore) List(context.Context) ([]model.Entry, error) {
	return append([]model.Entry(nil), store.entries...), nil
}

func (*readinessPremiumStore) Load(context.Context, string) (model.Entry, bool, error) {
	return model.Entry{}, false, errors.New("unexpected Load")
}

func (*readinessPremiumStore) Replay(
	context.Context,
	string,
	string,
) (ports.CommitReceipt, bool, error) {
	return ports.CommitReceipt{}, false, errors.New("unexpected Replay")
}

func (*readinessPremiumStore) Commit(
	context.Context,
	ports.ChangeSet,
) (ports.CommitReceipt, error) {
	return ports.CommitReceipt{}, errors.New("unexpected Commit")
}

func (*readinessPremiumStore) RecordApproval(context.Context, ports.Approval) error {
	return errors.New("unexpected RecordApproval")
}

func (*readinessPremiumStore) ListApprovals(
	context.Context,
	string,
	string,
	string,
	int64,
) ([]ports.Approval, error) {
	return nil, errors.New("unexpected ListApprovals")
}

var _ ports.Store = (*readinessPremiumStore)(nil)

func TestPremiumPoolEntryRejectsInvalidAdmissionAndExpiredWindow(t *testing.T) {
	now := time.Date(2026, 8, 2, 10, 0, 0, 0, time.UTC)
	for name, input := range map[string]model.UpsertInput{
		"low quality": {
			ContentID: "post-1", Scope: "global", QualityScore: 0.74,
			QualityAdmission: "approved", AuditID: "audit-1", ExpiresAt: now.Add(time.Hour),
		},
		"unapproved": {
			ContentID: "post-1", Scope: "global", QualityScore: 0.92,
			QualityAdmission: "pending", AuditID: "audit-1", ExpiresAt: now.Add(time.Hour),
		},
		"expired": {
			ContentID: "post-1", Scope: "global", QualityScore: 0.92,
			QualityAdmission: "approved", AuditID: "audit-1", ExpiresAt: now,
		},
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := model.Upsert(nil, input, now); !errors.Is(err, model.ErrInvalidArgument) {
				t.Fatalf("error=%v, want ErrInvalidArgument", err)
			}
		})
	}
}
