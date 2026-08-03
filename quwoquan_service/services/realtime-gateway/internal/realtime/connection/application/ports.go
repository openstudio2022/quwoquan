// Package application 承载 realtime-gateway 的连接会话用例。
// Connection 是 runtime_session 对象：无聚合存储，只有一次性 ticket、
// 逐连接 lease + fencing token 与 presence 投影（契约见
// services/realtime-gateway/contracts/realtime/connection/**）。
package application

import (
	"context"
	"errors"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
)

// TrustedIdentity 是 realtime 的单轨可信身份：account 只承载安全主体，
// persona 承载 RTC 业务路由，device 承载 presence/ACK 设备 identity。
type TrustedIdentity struct {
	AccountID string `json:"accountId"`
	PersonaID string `json:"personaId"`
	DeviceID  string `json:"deviceId"`
}

// TicketClaims 是一次性连接凭据绑定的可信身份快照。
type TicketClaims struct {
	TrustedIdentity
	AuthEpoch int64 `json:"authEpoch"`
	IssuedAt  int64 `json:"issuedAt"`
}

// Ticket 消费的结构化负例；transport 层映射到 REALTIME.USER.* 错误码。
var (
	ErrTicketInvalid  = errors.New("realtime: ticket invalid")
	ErrTicketReplayed = errors.New("realtime: ticket replayed")
)

// TicketStore 管理短期一次性连接凭据（redis rt:ticket:*）。
type TicketStore interface {
	Issue(ctx context.Context, claims TicketClaims, ttl time.Duration) (string, error)
	// Consume 一次性消费 ticket：不存在返回 ErrTicketInvalid（含 TTL 过期），
	// 已被消费返回 ErrTicketReplayed。
	Consume(ctx context.Context, ticket string) (TicketClaims, error)
	// Revoke 清除尚未消费的一次性 ticket；账户安全栅栏在签发期间推进时用它
	// 收敛签发/终态事件竞态。
	Revoke(ctx context.Context, accountID, ticket string) error
}

// LeaseStore 维护逐连接租约与每 persona/device 单调 fencing token
// （redis rt:conn:lease:* / rt:conn:fence:*，RUNTIME-SESSION-010）。
type LeaseStore interface {
	Acquire(ctx context.Context, identity TrustedIdentity, connID string, ttl time.Duration) (int64, error)
	Renew(ctx context.Context, identity TrustedIdentity, connID string, ttl time.Duration) error
	Release(ctx context.Context, identity TrustedIdentity, connID string) error
	// CurrentFence 返回该 persona/device 当前最大 fencing token；持有更小 token 的
	// 旧连接不得再回写共享状态。
	CurrentFence(ctx context.Context, identity TrustedIdentity) (int64, error)
}

// PresenceProjector is the typed lifecycle port to the separately-owned
// PresenceView projection. The Connection fence is mandatory on every write.
type PresenceProjector interface {
	Attach(
		ctx context.Context,
		identity TrustedIdentity,
		connID string,
		nodeID string,
		transport string,
		sequence int64,
	) error
	Heartbeat(
		ctx context.Context,
		identity TrustedIdentity,
		connID string,
		nodeID string,
		transport string,
		sequence int64,
	) error
	Detach(
		ctx context.Context,
		identity TrustedIdentity,
		connID string,
		sequence int64,
	) error
}

// PresenceRevoker is used by the durable account-security consumer. It keeps
// Connection cleanup from directly reading or mutating PresenceView keys.
type PresenceRevoker interface {
	RemoveConnection(
		ctx context.Context,
		accountID string,
		personaID string,
		deviceID string,
		connectionID string,
	) error
	RemoveAccount(
		ctx context.Context,
		accountID string,
		personaIDs []string,
	) error
}

// EventSource 同时使用 account/persona 的明确语义：账号通道保留给账号级消息，
// RTC 只订阅 persona 通道，禁止 user/account alias。
type EventSource interface {
	SubscribeIdentity(
		ctx context.Context,
		identity TrustedIdentity,
	) (runtimemessaging.EphemeralSubscription, error)
}

type ResumableEvent struct {
	Cursor  string
	Payload []byte
}

// ResumableEventReader gives every authenticated account/device an independent
// cursor over the short-lived realtime stream. It does not ACK globally.
type ResumableEventReader interface {
	ReadAfter(
		ctx context.Context,
		identity TrustedIdentity,
		cursor string,
		count int64,
		block time.Duration,
	) ([]ResumableEvent, error)
}

// AccountSecurityEvent 是 UserAccountClosed、UserSuspended、UserRestored 在
// realtime-gateway 内部的最小安全终态投影。它不复制上游 payload；只携带会话
// 清理、admission fencing 和跨节点踢出所需字段。
type AccountSecurityEvent struct {
	EventID      string
	AccountID    string
	PersonaIDs   []string
	AccountState string
	AuthEpoch    int64
	OccurredAt   time.Time
}

type AccountSecurityApplyResult struct {
	Replayed bool
	Evict    bool
}

// AccountSecurityGate 把 durable 安全终态投影为 Redis 中的 admission fence
// 与账户会话索引。Attach 在登记本地连接前后都验证该 gate，避免终态事件与
// 重连并发时留下残余会话。
type AccountSecurityGate interface {
	Admit(
		ctx context.Context,
		identity TrustedIdentity,
		authEpoch int64,
	) error
	RegisterSession(
		ctx context.Context,
		identity TrustedIdentity,
		connID string,
	) error
	UnregisterSession(
		ctx context.Context,
		identity TrustedIdentity,
		connID string,
	) error
	ApplyAccountSecurityEvent(
		ctx context.Context,
		event AccountSecurityEvent,
	) (AccountSecurityApplyResult, error)
}

// AccountSecurityRelay 在所有 realtime 节点间广播已持久化的终态 gate。
// Redis 中的 gate 才是 admission 真相源；relay 只负责立即关闭各节点进程内
// 的 socket/long-poll。
type AccountSecurityRelay interface {
	PublishAccountSecurity(
		ctx context.Context,
		event AccountSecurityEvent,
	) error
	SubscribeAccountSecurity(
		ctx context.Context,
	) (AccountSecurityRelaySubscription, error)
}

type AccountSecurityRelaySubscription interface {
	Events() <-chan AccountSecurityEvent
	Close() error
}
