// Package ports 定义 UserAccount 账号生命周期终态命令的对象专属数据端口。
package ports

import (
	"context"
	"errors"
	"time"
)

// ErrAccountNotFound 表示账号不存在，无法进入 closed 终态。
var ErrAccountNotFound = errors.New("user account not found")

// CloseResult 描述一次 close 提交后的账号终态。
type CloseResult struct {
	// AlreadyClosed 表示提交前账号已处于 closed 终态（幂等重放）。
	AlreadyClosed bool
	// ClosedAt 是 closed 状态的生效时间（重放时返回首次生效时间）。
	ClosedAt time.Time
	// PhoneCredentialKeys 只用于事务提交后清理手机号维度的短期 Redis
	// challenge/rate-limit 键。该字段不得进入日志、事件或 transport。
	PhoneCredentialKeys []string
}

// UserAccountCloseStore 是 CloseAccount 命令的唯一权威数据端口。
//
// CommitClose 必须在同一个 PostgreSQL transaction 内完成账号名下数据的
// 终态化（aggregate.yaml「close 为终态」业务规则）：
//  1. user_profiles 进入 closed 并擦除 owner PII；
//  2. AccountSession 全部吊销并擦除 token/device material；
//  3. CredentialBinding 全部失效、擦除 key/label 并释放全局唯一键；
//  4. Persona 保留 id 归因、退役并擦除公开资料；
//  5. 账号私有设置、设备、二维码、发现、关系、请求和提案被删除或匿名化；
//  6. UserAccountClosed durable outbox 与上述终态原子提交。
type UserAccountCloseStore interface {
	CommitClose(ctx context.Context, accountID string, closedAt time.Time) (CloseResult, error)
}

// CloseOutboxEvent 是 UserAccountClosed durable outbox 的强类型记录。
type CloseOutboxEvent struct {
	EventID         string
	AccountID       string
	AccountVersion  int64
	EventType       string
	PayloadJSON     []byte
	OccurredAt      time.Time
	DeliveryAttempt int
}

// CloseOutboxStore 为 UserAccountClosed 提供带租约的至少一次投递端口。
type CloseOutboxStore interface {
	ClaimReady(
		ctx context.Context,
		owner string,
		now time.Time,
		lease time.Duration,
	) (CloseOutboxEvent, bool, error)
	MarkPublished(
		ctx context.Context,
		eventID string,
		owner string,
		publishedAt time.Time,
	) error
	MarkFailed(
		ctx context.Context,
		eventID string,
		owner string,
		nextAttemptAt time.Time,
		lastError string,
	) error
}
