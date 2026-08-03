package ports

import (
	"context"
	"time"

	"quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/domain/model"
)

type Reader interface {
	Get(context.Context, string, string) (model.Authorization, error)
	GetByID(context.Context, string) (model.Authorization, error)
}

type Store interface {
	Reader
	Replay(context.Context, string, string, string, string) (model.MutationResult, bool, error)
	Start(context.Context, model.StartCommand) (model.MutationResult, error)
	Verify(context.Context, model.VerifyCommand) (model.MutationResult, error)
}

// GrantConsumer 由 ConnectorConnection 的同一 Mongo transaction 调用，保证
// connection、authorization consumed 状态、grant receipt 与 outbox 不会分叉。
type GrantConsumer interface {
	Consume(
		context.Context,
		string,
		string,
		string,
		string,
		string,
		time.Time,
	) error
	Revoke(
		context.Context,
		string,
		string,
		string,
		time.Time,
	) error
}
