package ports

import (
	"context"
	"time"

	"quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
)

type Reader interface {
	Get(context.Context, string, string) (model.Connection, error)
	List(context.Context, string, int) ([]model.Connection, error)
}

// PendingInvocationRevoker 是 ConnectorInvocation 暴露给连接撤权事务的对象级端口。
// 端口接收同一事务 context，不泄露 Mongo collection 或兄弟对象 infrastructure。
type PendingInvocationRevoker interface {
	RevokePendingForConnection(context.Context, string, string, time.Time) error
}

type Store interface {
	Reader
	Replay(context.Context, string, string, string, string) (model.MutationResult, bool, error)
	Create(context.Context, model.CreateCommand) (model.MutationResult, error)
	Revoke(context.Context, model.RevokeInput) (model.MutationResult, error)
}
