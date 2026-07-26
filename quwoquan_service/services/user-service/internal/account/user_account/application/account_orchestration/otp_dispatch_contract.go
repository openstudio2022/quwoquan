package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"time"
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
	CallbackURL    string
	ExpiresAt      time.Time
}

type ExternalInteractionAccepted struct {
	RequestID string
	Status    string
}

func hashOTPPhone(phone string) string {
	sum := sha256.Sum256([]byte(normalizePhoneCredentialKey(phone)))
	return hex.EncodeToString(sum[:])
}
