package otpseal

import (
	"context"
	"errors"
	"time"
)

var ErrReferenceNotFound = errors.New("otp code reference is unavailable")

type StoredReference struct {
	RequestID   string
	ChallengeID string
	CodeRef     string
	ExpiresAt   time.Time
}

// ReferenceStore 将密封 codeRef 与可靠任务 outbox 分离；实现必须具备 TTL 清理。
type ReferenceStore interface {
	Put(ctx context.Context, reference StoredReference) error
	Get(ctx context.Context, requestID, challengeID string) (StoredReference, error)
	Delete(ctx context.Context, requestID, challengeID string) error
}
