package authentication_challenge

import (
	"time"

	challengemodel "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/model"
)

type CreateChallengeCommand struct {
	ID                string
	AccountID         string
	Purpose           string
	Channel           string
	DestinationHash   string
	SecretRef         string
	BindingTicketRef  string
	DeliveryRequestID string
	DeliveryStatus    challengemodel.DeliveryStatus
	IdempotencyKey    string
	ExpiresAt         time.Time
}

// VerifyChallengeCommand 支持按 challengeId 精确验证，也支持调用方只持有
// purpose/channel/destinationHash 时查找最新 challenge。两种寻址方式不得混用。
// Credential 是明文瞬时输入，不得持久化、格式化或记录。
type VerifyChallengeCommand struct {
	ChallengeID     string
	Purpose         string
	Channel         string
	DestinationHash string
	Credential      []byte
}

type CancelChallengeCommand struct {
	ChallengeID string
}

type ReportDeliveryResultCommand struct {
	EventID    string
	RequestID  string
	Status     challengemodel.DeliveryStatus
	OccurredAt time.Time
}

type ChallengeCommandResult struct {
	Challenge        challengemodel.Snapshot
	IdempotentReplay bool
}
