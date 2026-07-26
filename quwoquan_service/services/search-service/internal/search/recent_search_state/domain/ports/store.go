// Package ports 定义 RecentSearchState 对象专属持久化端口。
package ports

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/services/search-service/internal/search/recent_search_state/domain/model"
)

// ErrVersionConflict 由 Store 在 CAS 失败时返回；facade 据此有限重放。
var ErrVersionConflict = errors.New("recent search state version conflict")

// ErrIdempotencyConflict 表示同一 receipt key 携带了不同 command digest。
var ErrIdempotencyConflict = errors.New("recent search idempotency key reused with a different command")

// Receipt 是命令回执：同 key 重放返回首次结果。
type Receipt struct {
	ReceiptKey    string      `bson:"_id"`
	PersonaID     string      `bson:"personaId"`
	CommandDigest string      `bson:"commandDigest"`
	Entry         model.Entry `bson:"entry,omitempty"`
	StateVersion  int64       `bson:"stateVersion"`
	Replayed      bool        `bson:"-"`
	CreatedAt     time.Time   `bson:"createdAt"`
	ExpiresAt     time.Time   `bson:"expiresAt"`
}

// Commit 在同一事务提交 state（CAS）与 receipt。expectedVersion==0 表示首次创建。
type Commit struct {
	ExpectedVersion int64
	State           model.State
	Receipt         Receipt
}

// Store 是 RecentSearchState 对象专属 AggregateStore。
type Store interface {
	Load(ctx context.Context, personaID, scope string) (model.State, bool, error)
	ListByPersona(ctx context.Context, personaID string) ([]model.State, error)
	// FindEntryOwner 定位包含 entryId 的状态文档（delete 用）。
	FindEntryOwner(ctx context.Context, personaID, entryID string) (model.State, bool, error)
	FindReceipt(ctx context.Context, receiptKey, commandDigest string) (Receipt, bool, error)
	Commit(ctx context.Context, commit Commit) error
	// RecordNoopReceipt 持久化目标状态已满足的首个 no-op 回执；
	// 已存在同 key 回执时返回其原始结果（replayed）。
	RecordNoopReceipt(ctx context.Context, receipt Receipt) (Receipt, error)
}
