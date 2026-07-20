// Package application 承载 realtime-gateway 的连接会话用例。
// Connection 是 runtime_session 对象：无聚合存储，只有一次性 ticket、
// 逐连接 lease + fencing token 与 presence 投影（契约见
// contracts/metadata/realtime/connection/**）。
package application

import (
	"context"
	"errors"
	"time"

	rtredis "quwoquan_service/runtime/redis"
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
	IssuedAt int64 `json:"issuedAt"`
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

type PresenceDevice struct {
	AccountID       string    `json:"accountId"`
	PersonaID       string    `json:"personaId"`
	DeviceID        string    `json:"deviceId"`
	ConnectionID    string    `json:"connId"`
	NodeID          string    `json:"nodeId"`
	Transport       string    `json:"transport"`
	LastHeartbeatAt time.Time `json:"lastHeartbeatAt"`
}

type PresenceView struct {
	PersonaID string           `json:"personaId"`
	Devices   []PresenceDevice `json:"devices"`
}

// PresenceStore 维护 persona 设备级在线投影（redis presence:persona:* hash）。
type PresenceStore interface {
	Attach(ctx context.Context, identity TrustedIdentity, connID, nodeID, transport string) error
	Heartbeat(ctx context.Context, identity TrustedIdentity, connID, nodeID, transport string) error
	Detach(ctx context.Context, identity TrustedIdentity, connID string) error
}

// PresenceViewReader 是 notification-service 的 internal named reader。
// reader 按每个 hash field 的 heartbeat 单独清理陈旧设备。
type PresenceViewReader interface {
	ReadPresence(
		ctx context.Context,
		personaID string,
		now time.Time,
	) (PresenceView, error)
}

// EventSource 同时使用 account/persona 的明确语义：账号通道保留给账号级消息，
// RTC 只订阅 persona 通道，禁止 user/account alias。
type EventSource interface {
	SubscribeIdentity(
		ctx context.Context,
		identity TrustedIdentity,
	) (rtredis.Subscription, error)
}
