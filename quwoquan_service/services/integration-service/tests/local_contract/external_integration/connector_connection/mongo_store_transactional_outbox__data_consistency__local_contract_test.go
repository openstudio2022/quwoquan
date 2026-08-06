// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
package connector_connection

import (
	"testing"

	"quwoquan_service/internal/platform/testinfra"
)

// connector_connection_outbox 是 integration.connector_connection 声明的事务性发布 seam：
// 连接状态、幂等回执与事件行必须由同一个事务句柄提交。
func TestConnectorConnectionAppendsOutboxInsideConnectionTransaction(t *testing.T) {
	testinfra.AssertTransactionalOutboxAppend(t, testinfra.TransactionalOutboxRule{
		SourcePath: "quwoquan_service/services/integration-service/internal/external_integration/" +
			"connector_connection/infrastructure/persistence/mongo_store.go",
		CommitFunctions:      []string{"Create", "Revoke"},
		OutboxField:          "outbox",
		OutboxDelegates:      []string{"commitReceiptAndOutbox"},
		ForbiddenIdentifiers: []string{"withTransaction"},
	})
}
