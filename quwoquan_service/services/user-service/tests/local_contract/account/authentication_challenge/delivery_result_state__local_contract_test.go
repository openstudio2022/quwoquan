// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-011.t1
// readiness_case: otp-delivery-result-state-local
package local_contract

import (
	"testing"
	"time"

	challengemodel "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/model"
)

// phoneDestinationHash is the hashed OTP destination fixture; sha256("phone").
const phoneDestinationHash = "sha256:45569da57f4b7bf472d7a864ef4781451cae6383fee9fb0ae40c59aa1ce475b7"

func TestAuthenticationChallengeDeliveryResultIsIdempotentAndMonotonic(t *testing.T) {
	t.Parallel()
	createdAt := time.Date(2026, 8, 10, 8, 0, 0, 0, time.UTC)
	challenge, err := challengemodel.New(challengemodel.CreateParams{
		ID:                "challenge-1",
		Purpose:           "login",
		Channel:           "sms",
		DestinationHash:   phoneDestinationHash,
		SecretRef:         "sealed:otp",
		DeliveryRequestID: "otp_req_123",
		DeliveryStatus:    challengemodel.DeliveryStatusQueued,
		ExpiresAt:         createdAt.Add(5 * time.Minute),
		CreatedAt:         createdAt,
	})
	if err != nil {
		t.Fatal(err)
	}

	sentAt := createdAt.Add(time.Second)
	sent, err := challenge.ApplyDeliveryResult(challengemodel.DeliveryResult{
		EventID:    "event-sent",
		RequestID:  "otp_req_123",
		Status:     challengemodel.DeliveryStatusSentUnconfirmed,
		OccurredAt: sentAt,
	})
	if err != nil || !sent.Changed {
		t.Fatalf("sent transition = %+v, %v", sent, err)
	}

	duplicate, err := sent.Aggregate.ApplyDeliveryResult(challengemodel.DeliveryResult{
		EventID:    "event-sent",
		RequestID:  "otp_req_123",
		Status:     challengemodel.DeliveryStatusSentUnconfirmed,
		OccurredAt: sentAt,
	})
	if err != nil || duplicate.Changed {
		t.Fatalf("duplicate transition = %+v, %v", duplicate, err)
	}
	outOfOrder, err := sent.Aggregate.ApplyDeliveryResult(challengemodel.DeliveryResult{
		EventID:    "event-old-queued",
		RequestID:  "otp_req_123",
		Status:     challengemodel.DeliveryStatusQueued,
		OccurredAt: createdAt.Add(500 * time.Millisecond),
	})
	if err != nil || outOfOrder.Changed {
		t.Fatalf("out-of-order transition = %+v, %v", outOfOrder, err)
	}

	deliveredAt := createdAt.Add(2 * time.Second)
	delivered, err := sent.Aggregate.ApplyDeliveryResult(challengemodel.DeliveryResult{
		EventID:    "event-delivered",
		RequestID:  "otp_req_123",
		Status:     challengemodel.DeliveryStatusDelivered,
		OccurredAt: deliveredAt,
	})
	if err != nil || !delivered.Changed ||
		delivered.Aggregate.Snapshot().DeliveryStatus != challengemodel.DeliveryStatusDelivered {
		t.Fatalf("delivered transition = %+v, %v", delivered, err)
	}
	terminalRegression, err := delivered.Aggregate.ApplyDeliveryResult(challengemodel.DeliveryResult{
		EventID:    "event-late-failed",
		RequestID:  "otp_req_123",
		Status:     challengemodel.DeliveryStatusFailed,
		OccurredAt: deliveredAt.Add(time.Second),
	})
	if err != nil || terminalRegression.Changed ||
		terminalRegression.Aggregate.Snapshot().DeliveryStatus != challengemodel.DeliveryStatusDelivered {
		t.Fatalf("terminal regression = %+v, %v", terminalRegression, err)
	}
}

func TestAuthenticationChallengeDeliveryFailureCancelsPendingChallenge(t *testing.T) {
	t.Parallel()
	createdAt := time.Date(2026, 8, 10, 8, 0, 0, 0, time.UTC)
	challenge, err := challengemodel.New(challengemodel.CreateParams{
		ID:                "challenge-failed",
		Purpose:           "login",
		Channel:           "sms",
		DestinationHash:   phoneDestinationHash,
		SecretRef:         "sealed:otp",
		DeliveryRequestID: "otp_req_failed",
		DeliveryStatus:    challengemodel.DeliveryStatusQueued,
		ExpiresAt:         createdAt.Add(5 * time.Minute),
		CreatedAt:         createdAt,
	})
	if err != nil {
		t.Fatal(err)
	}
	failed, err := challenge.ApplyDeliveryResult(challengemodel.DeliveryResult{
		EventID:    "event-dead-letter",
		RequestID:  "otp_req_failed",
		Status:     challengemodel.DeliveryStatusFailed,
		OccurredAt: createdAt.Add(time.Second),
	})
	if err != nil || !failed.Changed {
		t.Fatalf("failed transition = %+v, %v", failed, err)
	}
	snapshot := failed.Aggregate.Snapshot()
	if snapshot.DeliveryStatus != challengemodel.DeliveryStatusFailed ||
		snapshot.Status != challengemodel.StatusCancelled {
		t.Fatalf("failed snapshot = %+v", snapshot)
	}
}
