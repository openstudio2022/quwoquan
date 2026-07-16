package model

import (
	"errors"
	"strings"
	"testing"
	"time"

	personamodel "quwoquan_service/services/user-service/internal/domain/persona/model"
)

func TestProfileUpdateProposalStateMachineAndInvariants(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 7, 16, 8, 0, 0, 0, time.UTC)
	displayName := "新的公开身份"
	proposal, events, err := NewProfileUpdateProposal(
		"proposal-1",
		"persona-1",
		SourcePersona,
		personamodel.ProfileChangeSet{DisplayName: &displayName},
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

	applied, _, err := confirmed.MarkApplied(now.Add(2 * time.Minute))
	if err != nil {
		t.Fatalf("apply proposal: %v", err)
	}
	if applied.Status != StatusApplied || applied.Version != 3 || applied.ResolvedAt == nil {
		t.Fatalf("unexpected applied proposal: %#v", applied)
	}
	if _, _, err := applied.Reject("persona-1", now.Add(3*time.Minute)); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("terminal proposal accepted reject: %v", err)
	}
}

func TestProfileUpdateProposalRejectsInvalidTypedChangeSetAndState(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 7, 16, 8, 0, 0, 0, time.UTC)
	if _, _, err := NewProfileUpdateProposal("proposal-1", "persona-1", SourcePersona, personamodel.ProfileChangeSet{}, now); err == nil {
		t.Fatal("empty typed change set was accepted")
	}
	tooLongID := strings.Repeat("p", 65)
	displayName := "valid"
	if _, _, err := NewProfileUpdateProposal(tooLongID, "persona-1", SourcePersona, personamodel.ProfileChangeSet{DisplayName: &displayName}, now); err == nil {
		t.Fatal("proposal id beyond persistence limit was accepted")
	}
}
