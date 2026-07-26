// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-confirm-reject/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-create-review/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-apply-audit/spec.md#gwt-001
package local_contract

import (
	"errors"
	. "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/model"
	"strings"
	"testing"
	"time"

	personamodel "quwoquan_service/services/user-service/internal/persona_management/persona/domain/model"
)

func TestProfileUpdateProposalStateMachineAndInvariants(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 7, 16, 8, 0, 0, 0, time.UTC)
	displayName := "新的公开身份"
	creationContext, err := NewCommandAuditContext("persona-1", "request-create", "trace-create")
	if err != nil {
		t.Fatalf("create audit context: %v", err)
	}
	proposal, events, err := NewProfileUpdateProposal(
		"proposal-1",
		"persona-1",
		SourcePersona,
		personamodel.ProfileChangeSet{DisplayName: &displayName},
		"更新公开身份",
		[]string{"assistant-run:run-1"},
		[]string{"displayName"},
		creationContext,
		now,
	)
	if err != nil {
		t.Fatalf("create proposal: %v", err)
	}
	if proposal.Status != StatusPending || proposal.Version != 1 || len(events) != 1 {
		t.Fatalf("unexpected created proposal: %#v events=%#v", proposal, events)
	}
	if len(events[0].ID) > 96 {
		t.Fatalf("event id exceeds outbox schema: %d", len(events[0].ID))
	}

	confirmed, _, err := proposal.Confirm("persona-1", 7, now.Add(time.Minute))
	if err != nil {
		t.Fatalf("confirm proposal: %v", err)
	}
	if confirmed.Status != StatusConfirmed || confirmed.Version != 2 ||
		confirmed.TargetPersonaExpectedVersion == nil || *confirmed.TargetPersonaExpectedVersion != 7 {
		t.Fatalf("unexpected confirmed proposal: %#v", confirmed)
	}

	applyContext, err := NewCommandAuditContext("persona-1", "request-apply", "trace-apply")
	if err != nil {
		t.Fatalf("apply audit context: %v", err)
	}
	applying, _, err := confirmed.BeginApply(applyContext, now.Add(2*time.Minute))
	if err != nil || applying.Status != StatusApplying || applying.Version != 3 {
		t.Fatalf("begin apply proposal: proposal=%#v err=%v", applying, err)
	}
	appliedAt := now.Add(3 * time.Minute)
	applied, _, err := applying.MarkApplied(
		"apply-audit-1",
		appliedAt.Add(DefaultRollbackWindow),
		appliedAt,
	)
	if err != nil {
		t.Fatalf("apply proposal: %v", err)
	}
	if applied.Status != StatusApplied || applied.Version != 4 || applied.ResolvedAt == nil {
		t.Fatalf("unexpected applied proposal: %#v", applied)
	}
	if _, _, err := applied.Reject("persona-1", now.Add(4*time.Minute)); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("terminal proposal accepted reject: %v", err)
	}
	rollbackContext, err := NewCommandAuditContext("persona-1", "request-rollback", "trace-rollback")
	if err != nil {
		t.Fatalf("rollback audit context: %v", err)
	}
	if _, _, err := applied.BeginRollback(
		rollbackContext,
		applied.RollbackDeadline.Add(time.Second),
	); !errors.Is(err, ErrRollbackExpired) {
		t.Fatalf("expired rollback window was accepted: %v", err)
	}
	rollingBack, _, err := applied.BeginRollback(rollbackContext, now.Add(4*time.Minute))
	if err != nil || rollingBack.Status != StatusRollingBack || rollingBack.Version != 5 {
		t.Fatalf("begin rollback: proposal=%#v err=%v", rollingBack, err)
	}
	rolledBack, _, err := rollingBack.MarkRolledBack("rollback-audit-1", now.Add(5*time.Minute))
	if err != nil || rolledBack.Status != StatusRolledBack || rolledBack.Version != 6 {
		t.Fatalf("mark rolled back: proposal=%#v err=%v", rolledBack, err)
	}
}

func TestProfileUpdateProposalRejectsInvalidTypedChangeSetAndState(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 7, 16, 8, 0, 0, 0, time.UTC)
	context, err := NewCommandAuditContext("persona-1", "request-create", "trace-create")
	if err != nil {
		t.Fatalf("create audit context: %v", err)
	}
	if _, _, err := NewProfileUpdateProposal(
		"proposal-1", "persona-1", SourcePersona, personamodel.ProfileChangeSet{},
		"reason", []string{"assistant-run:run-1"}, []string{"displayName"}, context, now,
	); err == nil {
		t.Fatal("empty typed change set was accepted")
	}
	tooLongID := strings.Repeat("p", 65)
	displayName := "valid"
	if _, _, err := NewProfileUpdateProposal(
		tooLongID, "persona-1", SourcePersona,
		personamodel.ProfileChangeSet{DisplayName: &displayName},
		"reason", []string{"assistant-run:run-1"}, []string{"displayName"}, context, now,
	); err == nil {
		t.Fatal("proposal id beyond persistence limit was accepted")
	}
}
