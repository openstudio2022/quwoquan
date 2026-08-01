package external_interaction_attempt_fact_test

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/reliabletask"
)

func TestExternalInteractionSubjectDigestIsDeterministicAndOpaque(t *testing.T) {
	t.Parallel()
	payload := map[string]string{
		"targetPersonaId": "persona-private-001",
		"recipientId":     "ignored-lower-priority",
	}
	digest := reliabletask.ExternalInteractionSubjectDigest(payload)
	if digest == "" || len(digest) != 64 {
		t.Fatalf("subject digest must be one SHA-256 hex value, got %q", digest)
	}
	if digest != reliabletask.ExternalInteractionSubjectDigest(payload) {
		t.Fatal("same canonical subject must produce the same cleanup locator")
	}
	if strings.Contains(digest, payload["targetPersonaId"]) {
		t.Fatalf("subject digest leaked raw persona identity: %q", digest)
	}
	if digest == reliabletask.ExternalInteractionSubjectDigest(map[string]string{
		"targetPersonaId": "persona-private-002",
	}) {
		t.Fatal("different subjects must not share a cleanup locator")
	}
}

func TestExternalInteractionTaskAndAttemptKeepOneNonWirePrivacyLocator(t *testing.T) {
	t.Parallel()
	request := reliabletask.ExternalInteractionRequest{
		RequestID:      "request-001",
		Operation:      reliabletask.ExternalInteractionOperationPush,
		IdempotencyKey: "request-001",
		ExpiresAt:      time.Now().UTC().Add(time.Minute),
		Payload: map[string]string{
			"targetPersonaId": "persona-private-001",
		},
	}
	taskPayload := request.TaskPayload()
	want := reliabletask.ExternalInteractionSubjectDigest(request.Payload)
	if taskPayload["subjectDigest"] != want {
		t.Fatalf("task privacy locator = %q, want %q", taskPayload["subjectDigest"], want)
	}
	attempt := reliabletask.ProviderAttemptRecord{
		AttemptID:     "attempt-001",
		RequestID:     request.RequestID,
		TaskID:        "task-001",
		SubjectDigest: want,
	}
	wire, err := json.Marshal(attempt)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(wire), "subjectDigest") || strings.Contains(string(wire), want) {
		t.Fatalf("privacy locator must not enter operator/API wire: %s", wire)
	}
}

func TestExternalInteractionSubjectDigestIsAbsentWithoutOwnedSubject(t *testing.T) {
	t.Parallel()
	if got := reliabletask.ExternalInteractionSubjectDigest(map[string]string{
		"phoneHash": "opaque-pre-auth-destination",
	}); got != "" {
		t.Fatalf("pre-auth phone hash must not be treated as account ownership: %q", got)
	}
}
