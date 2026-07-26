// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/spec.md#sit-003
package api_integration

import (
	"context"
	"net/http"
	"testing"
	"time"

	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
)

func TestAPIAccountSecurityClosureRejectsPendingJoinAndPersistsTerminalState(
	t *testing.T,
) {
	t.Cleanup(func() { cleanAll(t) })

	const (
		initiatorID = "user-security-initiator"
		targetID    = "user-security-pending-target"
	)
	created := doPost(
		t,
		"/rtc/calls",
		`{"callType":"audio","inviteeIds":["user-security-pending-target"]}`,
		initiatorID,
		http.StatusCreated,
	)
	callID := extractSessionID(t, created)

	result, err := testOrchestrator.ApplyAccountSecurityTerminalEvent(
		context.Background(),
		application.AccountSecurityTerminalEvent{
			EventID:      "user-account-closed-api-event",
			AccountID:    "account-security-target",
			PersonaIDs:   []string{targetID},
			AccountState: "closed",
			OccurredAt:   time.Date(2026, time.July, 23, 15, 0, 0, 0, time.UTC),
		},
	)
	if err != nil {
		t.Fatalf("ApplyAccountSecurityTerminalEvent() error = %v", err)
	}
	if result.TerminatedCalls != 1 {
		t.Fatalf("terminated calls = %d, want 1", result.TerminatedCalls)
	}

	status, _ := doPostAny(
		t,
		"/rtc/calls/"+callID+"/join",
		`{}`,
		targetID,
	)
	if status != http.StatusGone {
		t.Fatalf("pending join after account closure = %d, want %d", status, http.StatusGone)
	}
	_, persisted := doGet(t, "/rtc/calls/"+callID, initiatorID)
	if persisted["status"] != "ended" ||
		persisted["endReason"] != "account_closed" {
		t.Fatalf("persisted terminal call = %#v", persisted)
	}
}
