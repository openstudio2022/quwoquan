// Package user_account 提供 UserAccount 账号生命周期的对象专属 command Facet。
package user_account

import (
	"context"
	"errors"
	"log/slog"
	"strings"
	"time"

	accountports "quwoquan_service/services/user-service/internal/domain/account/user_account/ports"
	"quwoquan_service/services/user-service/internal/generated"
)

// UserAccountClosedEventName 是 metadata events.yaml 声明的注销终态事件。
const UserAccountClosedEventName = "UserAccountClosed"

// ClosedAccountCacheInvalidator 清理账号与已释放手机号关联的短期派生缓存。
// PostgreSQL 已提交的安全终态不依赖缓存成功，参数不得进入日志。
type ClosedAccountCacheInvalidator interface {
	InvalidateClosedAccount(
		ctx context.Context,
		accountID string,
		phoneCredentialKeys []string,
	) error
}

// CloseCommand 是 CloseAccount 的强类型命令。
type CloseCommand struct {
	AccountID string
}

// CloseOutcome 对应 metadata CloseAccountResultWire。
type CloseOutcome struct {
	AccountState     string
	ClosedAt         time.Time
	IdempotentReplay bool
}

// CloseAccountFacade 是 CloseAccount 命令的唯一 application 入口。
// CommitClose 原子提交账号、会话、凭证、Persona、私有数据与 durable
// outbox 的安全终态；提交后只执行不影响终态的缓存失效。
type CloseAccountFacade struct {
	store accountports.UserAccountCloseStore
	cache ClosedAccountCacheInvalidator
}

func NewCloseAccountFacade(
	store accountports.UserAccountCloseStore,
	cache ClosedAccountCacheInvalidator,
) *CloseAccountFacade {
	if store == nil {
		panic("CloseAccountFacade requires the UserAccount close store")
	}
	return &CloseAccountFacade{
		store: store,
		cache: cache,
	}
}

func (facade *CloseAccountFacade) CloseAccount(
	ctx context.Context,
	command CloseCommand,
) (CloseOutcome, error) {
	accountID := strings.TrimSpace(command.AccountID)
	if accountID == "" {
		return CloseOutcome{}, generated.AppErrorFromInvalidArgument(
			"close account requires the authenticated account id",
		)
	}
	now := time.Now().UTC()
	committed, err := facade.store.CommitClose(ctx, accountID, now)
	if errors.Is(err, accountports.ErrAccountNotFound) {
		return CloseOutcome{}, generated.AppErrorFromUserNotFound(
			"account not found for close",
		)
	}
	if err != nil {
		slog.ErrorContext(
			ctx,
			"user account close transaction failed",
			"err",
			err,
		)
		return CloseOutcome{}, generated.AppErrorFromInternalError(
			"account close transaction failed",
		)
	}
	if facade.cache != nil {
		if err := facade.cache.InvalidateClosedAccount(
			ctx,
			accountID,
			committed.PhoneCredentialKeys,
		); err != nil {
			slog.WarnContext(
				ctx,
				"user account closed cache invalidation failed",
				"err",
				err,
			)
		}
	}
	return CloseOutcome{
		AccountState:     "closed",
		ClosedAt:         committed.ClosedAt,
		IdempotentReplay: committed.AlreadyClosed,
	}, nil
}
