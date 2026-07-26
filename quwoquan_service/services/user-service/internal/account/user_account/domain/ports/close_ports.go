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
// 终态化（object.yaml「close 为终态」业务规则）：
//  1. user_profiles 进入 closed、推进 auth_epoch 并擦除 owner PII；
//  2. AccountSession 全部吊销并擦除 token/device material；
//  3. CredentialBinding 全部失效、擦除 key/label 并释放全局唯一键；
//  4. Persona 保留 id 归因、退役并擦除公开资料；
//  5. 账号私有设置、设备、二维码、发现、关系、请求和提案被删除或匿名化；
//  6. UserAccountClosed durable outbox 与上述终态原子提交。
type UserAccountCloseStore interface {
	CommitClose(ctx context.Context, accountID string, closedAt time.Time) (CloseResult, error)
}

// UserAccountOutboxEvent 是 UserAccount 生命周期 durable outbox 的强类型记录。
// UserAccountClosed 使用不可逆清理路径；UserSuspended/UserRestored 只能被可逆
// restriction projection 消费，三者共享同一投递与重试语义。
type UserAccountOutboxEvent struct {
	EventID         string
	AccountID       string
	AccountVersion  int64
	EventType       string
	PayloadJSON     []byte
	OccurredAt      time.Time
	DeliveryAttempt int
}

// UserAccountOutboxFailureCode 是 relay 内部使用的稳定失败分类，不是 transport
// error code，也不得承载动态上下文。
type UserAccountOutboxFailureCode string

const (
	UserAccountOutboxFailurePayloadDecode   UserAccountOutboxFailureCode = "payload_decode"
	UserAccountOutboxFailureUnsupportedType UserAccountOutboxFailureCode = "unsupported_event_type"
	UserAccountOutboxFailurePublish         UserAccountOutboxFailureCode = "stream_publish"
	UserAccountOutboxFailurePublishAck      UserAccountOutboxFailureCode = "publish_ack"
	UserAccountOutboxFailureRetryRecord     UserAccountOutboxFailureCode = "retry_record"
	UserAccountOutboxFailureTerminalRecord  UserAccountOutboxFailureCode = "terminal_record"
	UserAccountOutboxFailureClaim           UserAccountOutboxFailureCode = "claim"
	UserAccountOutboxFailureRetentionPrune  UserAccountOutboxFailureCode = "retention_prune"
	UserAccountOutboxFailureHealthStore     UserAccountOutboxFailureCode = "health_store"
	UserAccountOutboxFailureUnexpected      UserAccountOutboxFailureCode = "unexpected"
)

// UserAccountOutboxFailure 是可持久化、脱敏的 relay 失败摘要。Code 只能是上述
// 稳定分类；Digest 是原始失败原因的不可逆 SHA-256 摘要，绝不保存原始错误、
// 事件 payload 或账号标识。
type UserAccountOutboxFailure struct {
	Code   UserAccountOutboxFailureCode
	Digest string
}

// UserAccountOutboxTerminalFailure 是可查询/重放的终态失败记录。它刻意不带
// AccountID、PayloadJSON 或其他可识别主体字段；EventID 是重放原 durable
// outbox 记录所需的唯一、不透明坐标。
type UserAccountOutboxTerminalFailure struct {
	EventID         string
	EventType       string
	AccountVersion  int64
	DeliveryAttempt int
	Failure         UserAccountOutboxFailure
	FailedAt        time.Time
	ExpiresAt       time.Time
}

// UserAccountOutboxStore 为 UserAccount 生命周期事件提供带租约的至少一次投递端口。
type UserAccountOutboxStore interface {
	ClaimReady(
		ctx context.Context,
		owner string,
		now time.Time,
		lease time.Duration,
	) (UserAccountOutboxEvent, bool, error)
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
		failedAt time.Time,
		nextAttemptAt time.Time,
		failure UserAccountOutboxFailure,
	) error
	MarkTerminalFailure(
		ctx context.Context,
		eventID string,
		owner string,
		failedAt time.Time,
		expiresAt time.Time,
		failure UserAccountOutboxFailure,
	) error
	ListTerminalFailures(
		ctx context.Context,
		now time.Time,
		limit int,
	) ([]UserAccountOutboxTerminalFailure, error)
	ReplayTerminalFailure(
		ctx context.Context,
		eventID string,
		replayedAt time.Time,
	) error
	PruneExpiredTerminalFailures(
		ctx context.Context,
		now time.Time,
	) (int64, error)
	TerminalFailureCount(ctx context.Context) (int, error)
}
