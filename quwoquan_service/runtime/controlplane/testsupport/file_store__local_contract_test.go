package testsupport

import (
	"errors"
	"strings"
	"testing"

	"quwoquan_service/runtime/controlplane"
)

func TestFileStoreApprovedMutationRequiresDistinctPrincipalsAndCommitsOnce(t *testing.T) {
	store := NewFileStore(t.TempDir() + "/control-plane.json")
	digest := strings.Repeat("a", 64)
	mutation := approvedMutationFixture(digest, "apply-1")

	if err := store.AppendApproval(ApprovalDecision{
		ObjectType: "config_release", ObjectID: "content-service",
		Actor: "operator-1", Decision: "apply", PayloadDigest: digest,
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := store.CommitApprovedMutation(mutation); !errors.Is(err, controlplane.ErrDualApprovalRequired) {
		t.Fatalf("single principal error=%v, want ErrDualApprovalRequired", err)
	}
	if err := store.AppendApproval(ApprovalDecision{
		ObjectType: "config_release", ObjectID: "content-service",
		Actor: "operator-1", Decision: "apply", PayloadDigest: digest,
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := store.CommitApprovedMutation(mutation); !errors.Is(err, controlplane.ErrDualApprovalRequired) {
		t.Fatalf("same principal twice error=%v, want ErrDualApprovalRequired", err)
	}
	if err := store.AppendApproval(ApprovalDecision{
		ObjectType: "config_release", ObjectID: "content-service",
		Actor: "operator-2", Decision: "apply", PayloadDigest: digest,
	}); err != nil {
		t.Fatal(err)
	}

	receipt, err := store.CommitApprovedMutation(mutation)
	if err != nil {
		t.Fatalf("commit approved mutation: %v", err)
	}
	if receipt.Replayed || receipt.IdempotencyKey != "apply-1" || receipt.CommittedAt == "" {
		t.Fatalf("unexpected receipt: %+v", receipt)
	}
	replayed, err := store.CommitApprovedMutation(mutation)
	if err != nil || !replayed.Replayed || replayed.CommittedAt != receipt.CommittedAt {
		t.Fatalf("replay receipt=%+v err=%v", replayed, err)
	}

	state, err := store.read()
	if err != nil {
		t.Fatal(err)
	}
	if len(state.MutationReceipts) != 1 || len(state.MutationOutbox) != 1 || len(state.Audits) != 1 {
		t.Fatalf(
			"atomic facts receipts=%d outbox=%d audits=%d",
			len(state.MutationReceipts),
			len(state.MutationOutbox),
			len(state.Audits),
		)
	}
	document := state.Documents["config_releases"]["content-service"]
	if document["status"] != "execution_pending" {
		t.Fatalf("committed document=%+v", document)
	}
}

func TestFileStoreApprovedMutationRejectsIdempotencyDrift(t *testing.T) {
	store := NewFileStore(t.TempDir() + "/control-plane.json")
	digest := strings.Repeat("b", 64)
	for _, actor := range []string{"operator-1", "operator-2"} {
		if err := store.AppendApproval(ApprovalDecision{
			ObjectType: "config_release", ObjectID: "content-service",
			Actor: actor, Decision: "apply", PayloadDigest: digest,
		}); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := store.CommitApprovedMutation(approvedMutationFixture(digest, "apply-1")); err != nil {
		t.Fatal(err)
	}
	drifted := approvedMutationFixture(strings.Repeat("c", 64), "apply-1")
	if _, err := store.CommitApprovedMutation(drifted); !errors.Is(err, controlplane.ErrMutationIdempotencyConflict) {
		t.Fatalf("drift error=%v, want ErrMutationIdempotencyConflict", err)
	}
}

func approvedMutationFixture(digest, idempotencyKey string) controlplane.ApprovedMutation {
	return controlplane.ApprovedMutation{
		Namespace:        "config_releases",
		ObjectType:       "config_release",
		ObjectID:         "content-service",
		Intent:           "apply",
		ApprovalDecision: "apply",
		PayloadDigest:    digest,
		IdempotencyKey:   idempotencyKey,
		Document: controlplane.Document{
			"id": "content-service", "status": "execution_pending",
		},
		Workflow: controlplane.WorkflowState{
			ObjectType: "config_release", ObjectID: "content-service",
			WorkflowID: "release-content-service", State: "execution_pending",
		},
		Audit: controlplane.AuditEvent{
			AuditID: "audit-apply-1", ObjectType: "config_release",
			ObjectID: "content-service", Action: "release_apply_requested",
		},
		OutboxEvents: []controlplane.MutationOutboxEvent{{
			EventID: "outbox-apply-1", EventType: "ConfigReleaseApplyRequested",
			AggregateType: "ConfigRelease", AggregateID: "content-service",
			Payload: map[string]any{"service": "content-service"},
		}},
	}
}
