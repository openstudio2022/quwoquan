package api_integration

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"

	controlplanepersistence "quwoquan_service/internal/platform/controlplane/persistence"
	"quwoquan_service/internal/platform/pgoutbox"
	"quwoquan_service/runtime/controlplane"
	runtimemessaging "quwoquan_service/runtime/messaging"
	experimentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/application"
	experimentmodel "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/model"
	experimentpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/infrastructure/persistence"
	assignmentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/application"
	assignmentpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/infrastructure/persistence"
)

func TestPostgresControlPlaneStorePersistsAndIsolatesScopes(t *testing.T) {
	if controlPlanePGPool == nil {
		t.Fatal("real PostgreSQL control-plane pool was not initialized")
	}
	scope := fmt.Sprintf("product-ops-api-%d", time.Now().UnixNano())
	store, err := controlplanepersistence.NewPostgresStore(controlPlanePGPool, scope)
	if err != nil {
		t.Fatalf("create postgres store: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	if err := store.EnsureSchema(ctx); err != nil {
		t.Fatalf("ensure postgres schema: %v", err)
	}

	first, inserted, err := store.PutDocumentIfAbsent(
		"experiment_assignment_facts",
		"assignment-1",
		controlplane.Document{"id": "assignment-1", "variant": "control"},
	)
	if err != nil || !inserted || first["variant"] != "control" {
		t.Fatalf("append assignment: inserted=%v document=%#v err=%v", inserted, first, err)
	}
	replayed, inserted, err := store.PutDocumentIfAbsent(
		"experiment_assignment_facts",
		"assignment-1",
		controlplane.Document{"id": "assignment-1", "variant": "treatment"},
	)
	if err != nil || inserted || replayed["variant"] != "control" {
		t.Fatalf("replay assignment: inserted=%v document=%#v err=%v", inserted, replayed, err)
	}

	if err := store.PutDocument("experiments", "exp-1", controlplane.Document{
		"id": "exp-1", "version": float64(1), "status": "active",
	}); err != nil {
		t.Fatalf("put experiment: %v", err)
	}
	if err := store.UpsertWorkflow(controlplane.WorkflowState{
		ObjectType: "experiment", ObjectID: "exp-1", WorkflowID: "rollout", State: "active",
	}); err != nil {
		t.Fatalf("upsert workflow: %v", err)
	}
	if err := store.AppendApproval(controlplane.ApprovalDecision{
		ObjectType: "experiment", ObjectID: "exp-1", Actor: "ops-1", Decision: "approved",
	}); err != nil {
		t.Fatalf("append approval: %v", err)
	}
	if err := store.AppendAudit(controlplane.AuditEvent{
		AuditID: "experiment_rollout_changed", ObjectType: "experiment", ObjectID: "exp-1",
		Action: "rollout", Actor: "ops-1", Environment: "gamma", RequestID: "req-1", TraceID: "trace-1",
	}); err != nil {
		t.Fatalf("append audit: %v", err)
	}

	reopened, err := controlplanepersistence.NewPostgresStore(controlPlanePGPool, scope)
	if err != nil {
		t.Fatalf("reopen postgres store: %v", err)
	}
	document, ok, err := reopened.GetDocument("experiments", "exp-1")
	if err != nil || !ok || document["status"] != "active" {
		t.Fatalf("reopen experiment: ok=%v document=%#v err=%v", ok, document, err)
	}
	workflow, ok, err := reopened.GetWorkflow("experiment", "exp-1")
	if err != nil || !ok || workflow.State != "active" {
		t.Fatalf("reopen workflow: ok=%v workflow=%#v err=%v", ok, workflow, err)
	}
	approvals, err := reopened.ListApprovals("experiment", "exp-1")
	if err != nil || len(approvals) != 1 {
		t.Fatalf("list approvals: approvals=%#v err=%v", approvals, err)
	}
	audits, err := reopened.ListAudits()
	if err != nil || len(audits) != 1 {
		t.Fatalf("list audits: audits=%#v err=%v", audits, err)
	}

	otherScope, err := controlplanepersistence.NewPostgresStore(controlPlanePGPool, scope+"-other")
	if err != nil {
		t.Fatalf("create isolated scope: %v", err)
	}
	if _, ok, err := otherScope.GetDocument("experiments", "exp-1"); err != nil || ok {
		t.Fatalf("scope isolation failed: ok=%v err=%v", ok, err)
	}
}

// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001
func TestExperimentAggregateAndAssignmentUseAtomicPostgresOutbox(t *testing.T) {
	if controlPlanePGPool == nil {
		t.Fatal("real PostgreSQL pool was not initialized")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	store, err := experimentpersistence.NewPostgresStore(controlPlanePGPool)
	if err != nil {
		t.Fatalf("create experiment store: %v", err)
	}
	if err := store.EnsureSchema(ctx); err != nil {
		t.Fatalf("ensure experiment schema: %v", err)
	}
	assignmentStore, err := assignmentpersistence.NewPostgresStore(controlPlanePGPool)
	if err != nil {
		t.Fatalf("create assignment fact store: %v", err)
	}
	if err := assignmentStore.EnsureSchema(ctx); err != nil {
		t.Fatalf("ensure assignment fact schema: %v", err)
	}
	experimentID := fmt.Sprintf("exp-%d", time.Now().UnixNano())
	now := time.Now().UTC().Truncate(time.Second)
	_, err = controlPlanePGPool.Exec(ctx, `
INSERT INTO experiments(
  id, key, version, status, variants, audience_rule, created_at, updated_at
) VALUES ($1,$2,1,'running',$3,$4,$5,$5)`,
		experimentID,
		experimentID,
		`[{"key":"control","allocationBasisPoints":2500},{"key":"treatment","allocationBasisPoints":7500}]`,
		`{"kind":"all"}`,
		now,
	)
	if err != nil {
		t.Fatalf("insert experiment fixture through postgres: %v", err)
	}
	facade, err := experimentapp.NewFacade(store, store)
	if err != nil {
		t.Fatalf("build experiment facade: %v", err)
	}
	assignmentFacade, err := assignmentapp.NewFacade(facade, assignmentStore, assignmentStore)
	if err != nil {
		t.Fatalf("build assignment facade: %v", err)
	}

	experiment, err := facade.Get(ctx, experimentID)
	if err != nil {
		t.Fatalf("load experiment for observed assignment: %v", err)
	}
	expected, err := experiment.Assign("persona-1", now)
	if err != nil {
		t.Fatalf("derive canonical assignment: %v", err)
	}
	observation := assignmentapp.AssignmentObservation{
		ExperimentID: experiment.ID, ExperimentRevision: experiment.Version,
		SubjectKey: expected.SubjectKey, Variant: expected.Variant, ObservedAt: now,
	}
	first, inserted, err := assignmentFacade.AppendObserved(ctx, observation)
	if err != nil || !inserted {
		t.Fatalf("append observed assignment: inserted=%v fact=%+v err=%v", inserted, first, err)
	}
	replayed, inserted, err := assignmentFacade.AppendObserved(ctx, observation)
	if err != nil || inserted || replayed.ID != first.ID || replayed.AssignedAt != first.AssignedAt {
		t.Fatalf("replay assignment: inserted=%v first=%+v replay=%+v err=%v", inserted, first, replayed, err)
	}

	receipt, err := facade.UpdateRollout(
		ctx,
		experimentID,
		1,
		"paused",
		[]experimentmodel.Variant{
			{Key: "control", AllocationBasisPoints: 2500},
			{Key: "treatment", AllocationBasisPoints: 7500},
		},
		"rollout-1",
	)
	if err != nil || receipt.Version != 2 || receipt.Replayed {
		t.Fatalf("commit rollout: receipt=%+v err=%v", receipt, err)
	}
	lateObservedAt := now.Add(time.Second)
	lateExpected, err := experiment.Assign("persona-late", lateObservedAt)
	if err != nil {
		t.Fatalf("derive delayed revision assignment: %v", err)
	}
	lateFact, inserted, err := assignmentFacade.AppendObserved(
		ctx,
		assignmentapp.AssignmentObservation{
			ExperimentID: experiment.ID, ExperimentRevision: experiment.Version,
			SubjectKey: lateExpected.SubjectKey, Variant: lateExpected.Variant,
			ObservedAt: lateObservedAt,
		},
	)
	if err != nil || !inserted || lateFact.ExperimentRevision != 1 {
		t.Fatalf("append delayed revision assignment: inserted=%v fact=%+v err=%v", inserted, lateFact, err)
	}
	replayedReceipt, err := facade.UpdateRollout(
		ctx,
		experimentID,
		1,
		"paused",
		[]experimentmodel.Variant{
			{Key: "control", AllocationBasisPoints: 2500},
			{Key: "treatment", AllocationBasisPoints: 7500},
		},
		"rollout-1",
	)
	if err != nil || !replayedReceipt.Replayed || replayedReceipt.Version != 2 {
		t.Fatalf("replay rollout: receipt=%+v err=%v", replayedReceipt, err)
	}
	_, err = facade.UpdateRollout(
		ctx,
		experimentID,
		2,
		"ended",
		[]experimentmodel.Variant{
			{Key: "control", AllocationBasisPoints: 2500},
			{Key: "treatment", AllocationBasisPoints: 7500},
		},
		"rollout-1",
	)
	if !errors.Is(err, experimentmodel.ErrIdempotencyConflict) {
		t.Fatalf("same idempotency key with another command error=%v, want ErrIdempotencyConflict", err)
	}

	var version int64
	if err := controlPlanePGPool.QueryRow(ctx, `SELECT version FROM experiments WHERE id=$1`, experimentID).Scan(&version); err != nil {
		t.Fatalf("read committed experiment: %v", err)
	}
	if version != 2 {
		t.Fatalf("experiment version=%d, want 2", version)
	}
	var factCount, outboxCount int
	if err := controlPlanePGPool.QueryRow(ctx, `
SELECT COUNT(*) FROM experiment_assignment_facts WHERE experiment_id=$1`, experimentID).Scan(&factCount); err != nil {
		t.Fatalf("count assignment facts: %v", err)
	}
	if err := controlPlanePGPool.QueryRow(ctx, `
SELECT COUNT(*) FROM product_ops_outbox WHERE aggregate_id IN ($1,$2)`, experimentID, first.ID).Scan(&outboxCount); err != nil {
		t.Fatalf("count outbox events: %v", err)
	}
	if factCount != 2 || outboxCount != 1 {
		t.Fatalf("atomic persistence mismatch: facts=%d outbox=%d", factCount, outboxCount)
	}
	publisher := &captureOutboxPublisher{}
	dispatcher, err := pgoutbox.NewDispatcher(controlPlanePGPool, publisher, "product_ops_outbox")
	if err != nil {
		t.Fatalf("create outbox dispatcher: %v", err)
	}
	dispatched, err := dispatcher.DispatchOnce(ctx)
	if err != nil || dispatched < 1 {
		t.Fatalf("dispatch outbox: dispatched=%d err=%v", dispatched, err)
	}
	var dispatchedCount int
	if err := controlPlanePGPool.QueryRow(ctx, `
SELECT COUNT(*) FROM product_ops_outbox
WHERE aggregate_id IN ($1,$2) AND dispatched_at IS NOT NULL`, experimentID, first.ID).Scan(&dispatchedCount); err != nil {
		t.Fatalf("count dispatched outbox events: %v", err)
	}
	if dispatchedCount != 1 || publisher.Count() < 1 {
		t.Fatalf("outbox dispatch mismatch: rows=%d published=%d", dispatchedCount, publisher.Count())
	}
}

// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001
func TestProductOpsOutboxFailureReleasesLeaseAndSchedulesRetry(t *testing.T) {
	if controlPlanePGPool == nil {
		t.Fatal("real PostgreSQL pool was not initialized")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	store, err := experimentpersistence.NewPostgresStore(controlPlanePGPool)
	if err != nil {
		t.Fatal(err)
	}
	if err := store.EnsureSchema(ctx); err != nil {
		t.Fatal(err)
	}
	eventID := fmt.Sprintf("outbox-retry-%d", time.Now().UnixNano())
	_, err = controlPlanePGPool.Exec(ctx, `
INSERT INTO product_ops_outbox(
  event_id, event_type, aggregate_type, aggregate_id, payload, occurred_at
) VALUES ($1,'ExperimentPolicyActivated','Experiment',$1,'{}',NOW())`, eventID)
	if err != nil {
		t.Fatalf("seed pending outbox: %v", err)
	}
	dispatcher, err := pgoutbox.NewDispatcher(
		controlPlanePGPool,
		failingOutboxPublisher{},
		"product_ops_outbox",
	)
	if err != nil {
		t.Fatal(err)
	}
	dispatched, err := dispatcher.DispatchOnce(ctx)
	if err != nil || dispatched != 0 {
		t.Fatalf("failed publish dispatch result=%d err=%v", dispatched, err)
	}
	var retryCount int
	var lastError, leaseOwner string
	var leasedUntil, dispatchedAt *time.Time
	var retryScheduled bool
	err = controlPlanePGPool.QueryRow(ctx, `
SELECT retry_count, last_error, COALESCE(lease_owner,''), leased_until, dispatched_at,
       next_attempt_at > NOW()
FROM product_ops_outbox WHERE event_id=$1`, eventID).
		Scan(&retryCount, &lastError, &leaseOwner, &leasedUntil, &dispatchedAt, &retryScheduled)
	if err != nil {
		t.Fatalf("inspect failed outbox: %v", err)
	}
	if retryCount != 1 || lastError == "" || leaseOwner != "" || leasedUntil != nil || dispatchedAt != nil || !retryScheduled {
		t.Fatalf(
			"failed outbox state retry=%d error=%q owner=%q lease=%v dispatched=%v scheduled=%v",
			retryCount, lastError, leaseOwner, leasedUntil, dispatchedAt, retryScheduled,
		)
	}
}

// spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/product-control-plane-contract/spec.md#gwt-002
func TestApprovedControlPlaneMutationIsAtomicIdempotentAndDispatchable(t *testing.T) {
	if controlPlanePGPool == nil {
		t.Fatal("real PostgreSQL pool was not initialized")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	store, err := controlplanepersistence.NewPostgresStore(controlPlanePGPool, "product-ops")
	if err != nil {
		t.Fatal(err)
	}
	if err := store.EnsureSchema(ctx); err != nil {
		t.Fatal(err)
	}
	suffix := fmt.Sprintf("%d", time.Now().UnixNano())
	objectID := "premium-" + suffix
	digest := fmt.Sprintf("%064d", time.Now().UnixNano())
	for _, actor := range []string{"operator-1", "operator-2"} {
		if err := store.AppendApproval(controlplane.ApprovalDecision{
			ObjectType: "premium_pool_entry", ObjectID: objectID,
			Actor: actor, Decision: "takedown", PayloadDigest: digest,
		}); err != nil {
			t.Fatal(err)
		}
	}
	eventID := "premium-takedown-" + suffix
	mutation := controlplane.ApprovedMutation{
		Namespace:        "premium_pool_entries",
		ObjectType:       "premium_pool_entry",
		ObjectID:         objectID,
		Intent:           "takedown",
		ApprovalDecision: "takedown",
		PayloadDigest:    digest,
		IdempotencyKey:   "idem-" + suffix,
		Document: controlplane.Document{
			"id": objectID, "status": "takedown_ejected",
		},
		Workflow: controlplane.WorkflowState{
			ObjectType: "premium_pool_entry", ObjectID: objectID,
			WorkflowID: "premium-takedown-" + suffix, State: "takedown_ejected",
		},
		Audit: controlplane.AuditEvent{
			AuditID: "audit-" + suffix, ObjectType: "premium_pool_entry",
			ObjectID: objectID, Action: "premium_pool.takedown",
		},
		OutboxEvents: []controlplane.MutationOutboxEvent{{
			EventID: eventID, EventType: "PremiumPoolEntryTakedownEjected",
			AggregateType: "PremiumPoolEntry", AggregateID: objectID,
			Payload: map[string]any{"id": objectID, "status": "takedown_ejected"},
		}},
	}
	receipt, err := store.CommitApprovedMutation(mutation)
	if err != nil || receipt.Replayed {
		t.Fatalf("commit receipt=%+v err=%v", receipt, err)
	}
	replayed, err := store.CommitApprovedMutation(mutation)
	if err != nil || !replayed.Replayed || replayed.CommittedAt != receipt.CommittedAt {
		t.Fatalf("replay receipt=%+v err=%v", replayed, err)
	}
	drifted := mutation
	drifted.PayloadDigest = strings.Repeat("f", 64)
	if _, err := store.CommitApprovedMutation(drifted); !errors.Is(err, controlplane.ErrMutationIdempotencyConflict) {
		t.Fatalf("idempotency drift error=%v", err)
	}

	var receiptCount, auditCount, outboxCount int
	if err := controlPlanePGPool.QueryRow(ctx, `
SELECT COUNT(*) FROM control_plane_mutation_receipts
WHERE scope='product-ops' AND object_type='premium_pool_entry' AND object_id=$1`, objectID).Scan(&receiptCount); err != nil {
		t.Fatal(err)
	}
	if err := controlPlanePGPool.QueryRow(ctx, `
SELECT COUNT(*) FROM control_plane_audits
WHERE scope='product-ops' AND object_type='premium_pool_entry' AND object_id=$1`, objectID).Scan(&auditCount); err != nil {
		t.Fatal(err)
	}
	if err := controlPlanePGPool.QueryRow(ctx, `
SELECT COUNT(*) FROM product_control_plane_outbox WHERE event_id=$1`, eventID).Scan(&outboxCount); err != nil {
		t.Fatal(err)
	}
	if receiptCount != 1 || auditCount != 1 || outboxCount != 1 {
		t.Fatalf("atomic counts receipt=%d audit=%d outbox=%d", receiptCount, auditCount, outboxCount)
	}

	publisher := &captureOutboxPublisher{}
	dispatcher, err := pgoutbox.NewDispatcher(controlPlanePGPool, publisher, "product_control_plane_outbox")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := dispatcher.DispatchOnce(ctx); err != nil {
		t.Fatal(err)
	}
	var dispatched bool
	if err := controlPlanePGPool.QueryRow(ctx, `
SELECT dispatched_at IS NOT NULL FROM product_control_plane_outbox WHERE event_id=$1`, eventID).Scan(&dispatched); err != nil {
		t.Fatal(err)
	}
	if !dispatched {
		t.Fatal("approved mutation outbox event was not dispatched")
	}

	failedObjectID := "premium-failed-" + suffix
	failedDigest := strings.Repeat("e", 64)
	for _, actor := range []string{"operator-1", "operator-2"} {
		if err := store.AppendApproval(controlplane.ApprovalDecision{
			ObjectType: "premium_pool_entry", ObjectID: failedObjectID,
			Actor: actor, Decision: "takedown", PayloadDigest: failedDigest,
		}); err != nil {
			t.Fatal(err)
		}
	}
	failedMutation := mutation
	failedMutation.ObjectID = failedObjectID
	failedMutation.PayloadDigest = failedDigest
	failedMutation.IdempotencyKey = "failed-" + suffix
	failedMutation.Document = controlplane.Document{"id": failedObjectID}
	failedMutation.Workflow.ObjectID = failedObjectID
	failedMutation.Audit = controlplane.AuditEvent{
		AuditID: "failed-audit-" + suffix, ObjectType: "premium_pool_entry",
		ObjectID: failedObjectID, Action: "premium_pool.takedown", At: "not-rfc3339",
	}
	failedMutation.OutboxEvents = []controlplane.MutationOutboxEvent{{
		EventID: "failed-outbox-" + suffix, EventType: "PremiumPoolEntryTakedownEjected",
		AggregateType: "PremiumPoolEntry", AggregateID: failedObjectID,
		Payload: map[string]any{"id": failedObjectID},
	}}
	if _, err := store.CommitApprovedMutation(failedMutation); err == nil {
		t.Fatal("invalid audit timestamp must roll back the approved mutation")
	}
	if _, found, err := store.GetMutationReceipt(
		"premium_pool_entry",
		failedObjectID,
		failedMutation.IdempotencyKey,
	); err != nil || found {
		t.Fatalf("failed mutation receipt found=%v err=%v", found, err)
	}
	if _, found, err := store.GetDocument("premium_pool_entries", failedObjectID); err != nil || found {
		t.Fatalf("failed mutation document found=%v err=%v", found, err)
	}
}

type captureOutboxPublisher struct {
	mu     sync.Mutex
	events []runtimemessaging.DomainEvent
}

func (p *captureOutboxPublisher) Publish(_ context.Context, event runtimemessaging.DomainEvent) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.events = append(p.events, event)
	return nil
}

func (p *captureOutboxPublisher) Count() int {
	p.mu.Lock()
	defer p.mu.Unlock()
	return len(p.events)
}

type failingOutboxPublisher struct{}

func (failingOutboxPublisher) Publish(context.Context, runtimemessaging.DomainEvent) error {
	return errors.New("broker unavailable")
}
