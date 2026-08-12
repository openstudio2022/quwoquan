package application

import (
	"context"
	"time"

	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
)

type ExternalInteractionClient interface {
	SubmitSMSOTP(
		ctx context.Context,
		req SMSOTPDispatchRequest,
	) (ExternalInteractionAccepted, error)
}

// SMSOTPReadinessChecker is deliberately separate from the delivery command
// port. Existing command doubles cannot accidentally claim delivery readiness;
// only the production integration client (or an explicit readiness double)
// may satisfy this read-only capability.
type SMSOTPReadinessChecker interface {
	CheckSMSOTPReadiness(ctx context.Context) error
}

type SMSOTPDispatchRequest struct {
	RequestID      string
	ChallengeID    string
	PhoneHash      string
	MaskedPhone    string
	CodeRef        string
	IdempotencyKey string
	ExpiresAt      time.Time
	Platform       string
	RequestRef     string
}

type ExternalInteractionAccepted struct {
	RequestID string
	Status    string
}

type OtpDeliveryReadiness struct {
	Availability      string `json:"availability"`
	RetryAfterSeconds int    `json:"retryAfterSeconds"`
}

func hashOTPPhone(phone string) string {
	return challengeapp.SMSDestinationHash(normalizePhoneCredentialKey(phone))
}
