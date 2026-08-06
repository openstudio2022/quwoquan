// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/product-control-plane-contract/spec.md#gwt-002
// readiness_case: list-premium-pool-entries-api
// readiness_case: upsert-premium-pool-entry-api
// readiness_case: rollback-premium-pool-entry-api
// readiness_case: takedown-premium-pool-entry-api
package api_integration

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/domain/ports"
	persistence "quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/infrastructure/persistence"
)

func TestPremiumPoolCommandsCommitStateAuditReceiptAndOutboxAtomically(t *testing.T) {
	if premiumPoolPGPool == nil {
		t.Fatal("real PostgreSQL pool was not initialized")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	store, err := persistence.NewPostgresStore(premiumPoolPGPool)
	if err != nil {
		t.Fatal(err)
	}
	if err := store.EnsureSchema(ctx); err != nil {
		t.Fatal(err)
	}
	service := application.NewService(store)
	suffix := fmt.Sprintf("%d", time.Now().UnixNano())
	contentID := "post-premium-" + suffix
	expiresAt := time.Now().UTC().Add(24 * time.Hour).Truncate(time.Second)
	baseContext := ports.CommandContext{
		ActorID: "operator-1", Environment: "gamma", RequestID: "request-" + suffix,
		TraceID: "trace-" + suffix, IdempotencyKey: "upsert-" + suffix,
	}
	upsert := application.UpsertCommand{
		ContentID: contentID, Scope: "global", QualityScore: 0.92,
		QualityAdmission: "approved", SupplySource: "canonical-release",
		SourceTaskID: "task-" + suffix, AuditID: "admission-" + suffix,
		ExpiresAt: expiresAt, Context: baseContext,
	}
	created, err := service.Upsert(ctx, upsert)
	if err != nil {
		t.Fatal(err)
	}
	if created.Status != "active" || created.Revision != 1 {
		t.Fatalf("created=%+v", created)
	}
	listed, err := service.List(ctx, false)
	if err != nil {
		t.Fatal(err)
	}
	foundCreated := false
	for _, item := range listed {
		if item.ContentID == contentID && item.Revision == created.Revision {
			foundCreated = true
			break
		}
	}
	if !foundCreated {
		t.Fatalf("List() did not return created entry %q: %+v", contentID, listed)
	}
	replayed, err := service.Upsert(ctx, upsert)
	if err != nil || replayed.Revision != 1 || replayed.UpdatedAt != created.UpdatedAt {
		t.Fatalf("replayed=%+v err=%v", replayed, err)
	}
	drifted := upsert
	drifted.QualityScore = 0.97
	if _, err := service.Upsert(ctx, drifted); !errors.Is(err, model.ErrIdempotencyConflict) {
		t.Fatalf("drifted idempotency error=%v", err)
	}

	rollbackContext := baseContext
	rollbackContext.IdempotencyKey = "rollback-" + suffix
	rolledBack, err := service.Rollback(ctx, contentID, rollbackContext)
	if err != nil {
		t.Fatal(err)
	}
	if rolledBack.Status != "rolled_back" || rolledBack.Revision != 2 {
		t.Fatalf("rolledBack=%+v", rolledBack)
	}
	rollbackReplay, err := service.Rollback(ctx, contentID, rollbackContext)
	if err != nil || rollbackReplay.Revision != 2 || rollbackReplay.UpdatedAt != rolledBack.UpdatedAt {
		t.Fatalf("rollback replay=%+v err=%v", rollbackReplay, err)
	}

	reupsertContext := baseContext
	reupsertContext.IdempotencyKey = "reupsert-" + suffix
	reupsert := upsert
	reupsert.Context = reupsertContext
	reupsert.AuditID = "admission-reactivated-" + suffix
	reactivated, err := service.Upsert(ctx, reupsert)
	if err != nil || reactivated.Status != "active" || reactivated.Revision != 3 {
		t.Fatalf("reactivated=%+v err=%v", reactivated, err)
	}

	firstApprovalContext := baseContext
	firstApprovalContext.IdempotencyKey = "takedown-" + suffix
	pending, err := service.Takedown(ctx, contentID, firstApprovalContext)
	if err != nil || !pending.Pending || pending.ApprovalCount != 1 {
		t.Fatalf("pending=%+v err=%v", pending, err)
	}
	pendingReplay, err := service.Takedown(ctx, contentID, firstApprovalContext)
	if err != nil || !pendingReplay.Pending || pendingReplay.ApprovalCount != 1 {
		t.Fatalf("same actor replay=%+v err=%v", pendingReplay, err)
	}
	secondApprovalContext := firstApprovalContext
	secondApprovalContext.ActorID = "operator-2"
	approved, err := service.Takedown(ctx, contentID, secondApprovalContext)
	if err != nil || approved.Pending || approved.ApprovalCount != 2 || approved.Entry.Revision != 4 {
		t.Fatalf("approved=%+v err=%v", approved, err)
	}
	if approved.Receipt == nil || approved.Receipt.Replayed {
		t.Fatalf("approved receipt=%+v", approved.Receipt)
	}
	approvedReplay, err := service.Takedown(ctx, contentID, secondApprovalContext)
	if err != nil || approvedReplay.Pending || approvedReplay.Receipt == nil || !approvedReplay.Receipt.Replayed {
		t.Fatalf("approved replay=%+v err=%v", approvedReplay, err)
	}

	assertObjectRows(t, ctx, contentID, 4, 4, 4, 1)

	var duplicateEventID string
	if err := premiumPoolPGPool.QueryRow(ctx, `
SELECT event_id FROM premium_pool_entry_outbox
WHERE aggregate_id=$1 ORDER BY occurred_at LIMIT 1`, contentID).Scan(&duplicateEventID); err != nil {
		t.Fatal(err)
	}
	failedContentID := "post-premium-failed-" + suffix
	failedEntry, err := model.Upsert(nil, model.UpsertInput{
		ContentID: failedContentID, Scope: "global", QualityScore: 0.9,
		QualityAdmission: "approved", AuditID: "failed-audit-" + suffix,
		ExpiresAt: expiresAt,
	}, time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	_, err = store.Commit(ctx, ports.ChangeSet{
		Entry: failedEntry, ExpectedRevision: 0, Intent: application.IntentUpsert,
		CommandDigest: strings.Repeat("d", 64),
		Context: ports.CommandContext{
			ActorID: "operator-1", Environment: "gamma",
			RequestID: "failed-request-" + suffix, TraceID: "failed-trace-" + suffix,
			IdempotencyKey: "failed-command-" + suffix,
		},
		Event: ports.Event{
			ID: duplicateEventID, Type: application.EventUpserted,
			AggregateID: failedContentID, Payload: map[string]any{"contentId": failedContentID},
			OccurredAt: time.Now().UTC(),
		},
	})
	if err == nil {
		t.Fatal("duplicate outbox event must roll back the whole command")
	}
	if _, found, loadErr := store.Load(ctx, failedContentID); loadErr != nil || found {
		t.Fatalf("failed command entry found=%v err=%v", found, loadErr)
	}
	assertObjectRows(t, ctx, failedContentID, 0, 0, 0, 0)
}

func assertObjectRows(
	t *testing.T,
	ctx context.Context,
	contentID string,
	wantAudit int,
	wantOutbox int,
	wantReceipt int,
	wantWorkflow int,
) {
	t.Helper()
	queries := []struct {
		name  string
		query string
		want  int
	}{
		{"audit", `SELECT COUNT(*) FROM premium_pool_entry_audits WHERE content_id=$1`, wantAudit},
		{"outbox", `SELECT COUNT(*) FROM premium_pool_entry_outbox WHERE aggregate_id=$1`, wantOutbox},
		{"receipt", `SELECT COUNT(*) FROM premium_pool_entry_command_receipts WHERE content_id=$1`, wantReceipt},
		{"workflow", `SELECT COUNT(*) FROM premium_pool_entry_workflows WHERE content_id=$1`, wantWorkflow},
	}
	for _, item := range queries {
		var count int
		if err := premiumPoolPGPool.QueryRow(ctx, item.query, contentID).Scan(&count); err != nil {
			t.Fatalf("count %s: %v", item.name, err)
		}
		if count != item.want {
			t.Fatalf("%s count=%d want=%d", item.name, count, item.want)
		}
	}
}
