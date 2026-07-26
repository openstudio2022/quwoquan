package user_account

import (
	"context"
	"errors"
	"log/slog"
	"strings"
	"time"

	"quwoquan_service/services/user-service/generated/account/user_account"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
)

const (
	// UserSuspendedEventName 与 metadata events.yaml 中的事件名保持同源。
	UserSuspendedEventName = "UserSuspended"
	// UserRestoredEventName 与 metadata events.yaml 中的事件名保持同源。
	UserRestoredEventName = "UserRestored"
)

// EnforcementCommand 是受信 Product Ops decision 到 UserAccount 的强类型边界。
type EnforcementCommand struct {
	AccountID string
	Action    accountports.EnforcementAction
	Decision  accountports.EnforcementDecision
}

// EnforcementOutcome 对应 AccountEnforcementResultWire。
type EnforcementOutcome struct {
	AccountState     string
	AuthEpoch        int64
	DecisionID       string
	IdempotentReplay bool
	OccurredAt       time.Time
}

// AccountEnforcementCommandFacade 是 SuspendAccount/RestoreAccount 的唯一 application
// 入口。调用方服务身份、scope 与审批链由 transport operation guard 验证；本 facade
// 只接受最小不透明 decision，并将状态、安全代次、session 撤销、回执和 outbox 交给同一
// 对象专属 Store 原子提交。
type AccountEnforcementCommandFacade struct {
	store accountports.UserAccountEnforcementStore
	now   func() time.Time
}

func NewAccountEnforcementCommandFacade(
	store accountports.UserAccountEnforcementStore,
) *AccountEnforcementCommandFacade {
	if store == nil {
		panic("AccountEnforcementCommandFacade requires an enforcement store")
	}
	return &AccountEnforcementCommandFacade{
		store: store,
		now:   time.Now,
	}
}

func (facade *AccountEnforcementCommandFacade) SuspendAccount(
	ctx context.Context,
	command EnforcementCommand,
) (EnforcementOutcome, error) {
	command.Action = accountports.EnforcementActionSuspend
	return facade.execute(ctx, command)
}

func (facade *AccountEnforcementCommandFacade) RestoreAccount(
	ctx context.Context,
	command EnforcementCommand,
) (EnforcementOutcome, error) {
	command.Action = accountports.EnforcementActionRestore
	return facade.execute(ctx, command)
}

func (facade *AccountEnforcementCommandFacade) execute(
	ctx context.Context,
	command EnforcementCommand,
) (EnforcementOutcome, error) {
	accountID := strings.TrimSpace(command.AccountID)
	decision := normalizeEnforcementDecision(command.Decision)
	if accountID == "" || !validEnforcementAction(command.Action) ||
		decision.DecisionID == "" || decision.CaseRef == "" ||
		decision.DecisionDigest == "" || decision.ApprovedAt.IsZero() {
		return EnforcementOutcome{}, generated.AppErrorFromAccountEnforcementDecisionInvalid(
			"account enforcement requires a complete trusted decision",
		)
	}

	committed, err := facade.store.CommitEnforcement(
		ctx,
		accountID,
		command.Action,
		decision,
		facade.now().UTC(),
	)
	if errors.Is(err, accountports.ErrAccountNotFound) {
		return EnforcementOutcome{}, generated.AppErrorFromUserNotFound(
			"account not found for enforcement",
		)
	}
	if errors.Is(err, accountports.ErrEnforcementDecisionInvalid) {
		return EnforcementOutcome{}, generated.AppErrorFromAccountEnforcementDecisionInvalid(
			"account enforcement decision validation failed",
		)
	}
	if errors.Is(err, accountports.ErrAccountStateConflict) {
		return EnforcementOutcome{}, generated.AppErrorFromAccountStateConflict(
			"account state does not permit enforcement action",
		)
	}
	if err != nil {
		slog.ErrorContext(
			ctx,
			"user account enforcement transaction failed",
			"action",
			command.Action,
			"err",
			err,
		)
		return EnforcementOutcome{}, generated.AppErrorFromInternalError(
			"account enforcement transaction failed",
		)
	}
	return EnforcementOutcome{
		AccountState:     committed.AccountState,
		AuthEpoch:        committed.AuthEpoch,
		DecisionID:       committed.DecisionID,
		IdempotentReplay: committed.IdempotentReplay,
		OccurredAt:       committed.OccurredAt,
	}, nil
}

func normalizeEnforcementDecision(
	decision accountports.EnforcementDecision,
) accountports.EnforcementDecision {
	decision.DecisionID = strings.TrimSpace(decision.DecisionID)
	decision.CaseRef = strings.TrimSpace(decision.CaseRef)
	decision.DecisionDigest = strings.TrimSpace(decision.DecisionDigest)
	decision.ApprovedAt = decision.ApprovedAt.UTC()
	return decision
}

func validEnforcementAction(action accountports.EnforcementAction) bool {
	return action == accountports.EnforcementActionSuspend ||
		action == accountports.EnforcementActionRestore
}
