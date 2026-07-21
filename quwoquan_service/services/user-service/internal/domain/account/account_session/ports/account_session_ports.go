package ports

import (
	"context"
	"errors"
	"time"
)

// AccountSession 事件类型：与 contracts/metadata/user/account_session/events.yaml 对齐。
const (
	AccountSessionAuthenticatedEvent = "AccountSessionAuthenticated"
	AccountSessionRevokedEvent       = "AccountSessionRevoked"
)

// 会话吊销原因（进入 outbox payload 与审计）。
const (
	RevokeReasonLogout       = "logout"
	RevokeReasonReplay       = "refresh_replay"
	RevokeReasonExpired      = "expired"
	RevokeReasonSecuritySalt = "security_revoke"
)

var (
	// ErrSessionNotFound 表示 refresh token hash 无对应会话。
	ErrSessionNotFound = errors.New("account session not found")
	// ErrSessionExpired 表示会话已过期。
	ErrSessionExpired = errors.New("account session expired")
	// ErrSessionReplayed 表示旧 refresh token 被重放，整条 lineage 已吊销。
	ErrSessionReplayed = errors.New("account session refresh token replayed")
	// ErrSessionRevoked 表示会话已被吊销。
	ErrSessionRevoked = errors.New("account session revoked")
	// ErrSessionAccountSuspended 表示 refresh session 因账号封禁而被原子吊销。
	// 这是客户端获得结构化 account_suspended 恢复语义的唯一会话层信号；
	// restore 后同一旧会话仍只返回 ErrSessionRevoked。
	ErrSessionAccountSuspended = errors.New("account session revoked by suspension")
)

// IssuedSession 是签发/轮换后的会话快照。
type IssuedSession struct {
	SessionID string
	AccountID string
	DeviceID  string
	LineageID string
	ExpiresAt time.Time
}

// AccountSessionStore 是 AccountSession 聚合的对象专属端口。
// 权威状态只保存 refreshTokenHash 与 rotation lineage，明文 token 不落库；
// 会话状态变更与 account_sessions_outbox 在同一事务提交。
type AccountSessionStore interface {
	// IssueSession 登录成功后签发新会话（新 lineage）。
	IssueSession(
		ctx context.Context,
		accountID string,
		deviceID string,
		authenticationSubject string,
		identityOrigin string,
		refreshTokenHash string,
		expiresAt time.Time,
	) (IssuedSession, error)
	// RotateSession 单次轮换：active 会话换发新 hash（同 lineage）；
	// 对已 rotated 的 hash 重放立即吊销整条 lineage 并返回 ErrSessionReplayed。
	RotateSession(
		ctx context.Context,
		currentTokenHash string,
		nextTokenHash string,
		expiresAt time.Time,
	) (IssuedSession, error)
	// RevokeByTokenHash 吊销单个会话（logout）；对已吊销会话幂等 no-op。
	RevokeByTokenHash(ctx context.Context, refreshTokenHash string, reason string) error
	// RevokeAllForAccount 吊销账号全部 active 会话（登出所有设备/安全事件）。
	RevokeAllForAccount(ctx context.Context, accountID string, reason string) error
}
