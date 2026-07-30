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

type SMSOTPDispatchRequest struct {
	RequestID      string
	ChallengeID    string
	PhoneHash      string
	MaskedPhone    string
	CodeRef        string
	IdempotencyKey string
	ExpiresAt      time.Time
}

type ExternalInteractionAccepted struct {
	RequestID string
	Status    string
}

func hashOTPPhone(phone string) string {
	return challengeapp.SMSDestinationHash(normalizePhoneCredentialKey(phone))
}
