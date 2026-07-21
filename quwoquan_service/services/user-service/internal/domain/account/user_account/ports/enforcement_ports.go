// Package ports 定义 UserAccount 处置持久化边界。
package ports

import (
	"context"
	"errors"
	"time"
)

var (
	// ErrEnforcementDecisionInvalid 拒绝格式错误或互相矛盾的受信决策，
	// 不记录不透明 case 引用或证据。
	ErrEnforcementDecisionInvalid = errors.New("account enforcement decision invalid")
	// ErrAccountStateConflict 阻止恢复 closed 账号，或在不兼容状态重放不同决策。
	ErrAccountStateConflict = errors.New("account enforcement state conflict")
)

type EnforcementAction string

const (
	EnforcementActionSuspend EnforcementAction = "suspend"
	EnforcementActionRestore EnforcementAction = "restore"
)

// EnforcementDecision 是执行账号状态迁移所需的最小受信决策材料。Product Ops 保留
// 审批人和证据事实；UserAccount 只持久化不透明、可审计的引用。
type EnforcementDecision struct {
	DecisionID     string
	CaseRef        string
	DecisionDigest string
	ApprovedAt     time.Time
}

type EnforcementCommitResult struct {
	AccountState     string
	AuthEpoch        int64
	DecisionID       string
	IdempotentReplay bool
	OccurredAt       time.Time
}

// AccountSecuritySnapshot 是由 UserAccount 权威状态派生的最小鉴权快照。
// 除 accountState 和 authEpoch 外不携带任何资料、case 或审核事实。
type AccountSecuritySnapshot struct {
	AccountState string
	AuthEpoch    int64
}

// AccountSecurityReader 为认证后的请求提供账号状态与安全代次检查。读取失败必须由
// 调用方 fail-closed，避免账号处置期间把无法核验的凭证当作有效凭证。
type AccountSecurityReader interface {
	ReadAccountSecurity(
		ctx context.Context,
		accountID string,
	) (AccountSecuritySnapshot, error)
}

// UserAccountEnforcementStore 在同一 PostgreSQL transaction 内提交 Suspend/Restore。
// 提交必须锁定 UserAccount、校验合法迁移、撤销既有 refresh session、递增 authEpoch，
// 并原子写入决策回执和对应 durable outbox。
type UserAccountEnforcementStore interface {
	CommitEnforcement(
		ctx context.Context,
		accountID string,
		action EnforcementAction,
		decision EnforcementDecision,
		occurredAt time.Time,
	) (EnforcementCommitResult, error)
}
