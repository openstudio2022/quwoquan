// Package ports 定义 CredentialBinding 对象专属 PostgreSQL Store 合同。
package ports

import (
	"context"
	"errors"
	"time"

	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
)

var (
	ErrCredentialConflict        = errors.New("credential binding conflicts with existing identity")
	ErrLastRecoverableCredential = errors.New(
		"credential binding is the last recoverable credential",
	)
	ErrCredentialBindingNotFound = errors.New("credential binding not found")
)

type BindResult struct {
	Aggregate bindingmodel.CredentialBinding
	Replayed  bool
}

// AggregateStore 是 CredentialBinding 的唯一权威数据端口。
//
// Bind 必须以 credentialType + credentialKey 全局唯一约束承载自然幂等：
// 同账号同凭证返回已有 active binding 且不追加 outbox；跨账号、同账号同类型
// 不同 key 或命中 revoked binding 均返回 ErrCredentialConflict。首次绑定必须把
// state 与 CredentialBound outbox 放在同一 PostgreSQL transaction。
//
// CommitRevoke 必须在一个 transaction 内锁定 owner 的绑定集合、验证至少剩余
// 一种 active 可恢复凭证、按 expectedVersion 做内部 CAS，并原子写入
// CredentialRevoked outbox。
type AggregateStore interface {
	Bind(
		ctx context.Context,
		change bindingmodel.ChangeSet,
	) (BindResult, error)
	LoadByOwnerAndType(
		ctx context.Context,
		ownerID string,
		credentialType bindingmodel.CredentialType,
	) (bindingmodel.CredentialBinding, bool, error)
	FindByTypeAndKey(
		ctx context.Context,
		credentialType bindingmodel.CredentialType,
		credentialKey string,
	) (bindingmodel.CredentialBinding, bool, error)
	MarkUsed(
		ctx context.Context,
		aggregateID string,
		usedAt time.Time,
	) error
	ListByOwner(
		ctx context.Context,
		ownerID string,
	) ([]bindingmodel.CredentialBinding, error)
	CommitRevoke(
		ctx context.Context,
		expectedVersion int64,
		change bindingmodel.ChangeSet,
	) error
}
