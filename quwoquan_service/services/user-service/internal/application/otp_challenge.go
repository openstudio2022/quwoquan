package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"strings"
	"time"
)

const (
	OtpChallengeStatusPendingDispatch = "pending_dispatch"
	OtpChallengeStatusActive          = "active"
	OtpChallengeStatusFailed          = "failed"
	OtpChallengeStatusConsumed        = "consumed"
)

type OtpChallenge struct {
	ChallengeID    string
	RequestID      string
	Phone          string
	PhoneHash      string
	CodeHash       string
	Status         string
	IdempotencyKey string
	ExpiresAt      time.Time
	ConsumedAt     *time.Time
	CreatedAt      time.Time
	UpdatedAt      time.Time
}

type OtpChallengeStore interface {
	CreateChallenge(ctx context.Context, challenge OtpChallenge) (OtpChallenge, error)
	FindLatestChallenge(ctx context.Context, phone string, now time.Time) (*OtpChallenge, error)
	MarkChallengeDelivered(ctx context.Context, requestID string, status string) error
	MarkChallengeFailed(ctx context.Context, requestID string, reason string) error
	ConsumeChallenge(ctx context.Context, challengeID string, now time.Time) error
}

type ExternalInteractionClient interface {
	SubmitSMSOTP(ctx context.Context, req SMSOTPDispatchRequest) (ExternalInteractionAccepted, error)
}

type SMSOTPDispatchRequest struct {
	RequestID      string
	ChallengeID    string
	Phone          string
	PhoneHash      string
	MaskedPhone    string
	Code           string
	IdempotencyKey string
	CallbackURL    string
	ExpiresAt      time.Time
}

type ExternalInteractionAccepted struct {
	RequestID string
	Status    string
}

func hashOTPCode(challengeID string, phone string, code string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(challengeID) + ":" + normalizePhoneCredentialKey(phone) + ":" + strings.TrimSpace(code)))
	return hex.EncodeToString(sum[:])
}

func hashOTPPhone(phone string) string {
	sum := sha256.Sum256([]byte(normalizePhoneCredentialKey(phone)))
	return hex.EncodeToString(sum[:])
}
