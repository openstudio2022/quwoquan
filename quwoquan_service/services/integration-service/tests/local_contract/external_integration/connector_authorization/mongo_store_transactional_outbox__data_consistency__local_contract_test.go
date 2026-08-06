// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
package connector_authorization

import (
	"testing"

	"quwoquan_service/internal/platform/testinfra"
)

// connector_authorization_outbox 是 integration.connector_authorization 声明的事务性发布
// seam。Start/Verify 自己开事务，Consume/Revoke 继承调用方事务；两条路径都不允许在事务外
// 追加事件，否则授权状态会在事件缺失的情况下提交。
func TestConnectorAuthorizationAppendsOutboxOnlyUnderTransactionHandle(t *testing.T) {
	testinfra.AssertTransactionalOutboxAppend(t, testinfra.TransactionalOutboxRule{
		SourcePath: "quwoquan_service/services/integration-service/internal/external_integration/" +
			"connector_authorization/infrastructure/persistence/mongo_store.go",
		CommitFunctions:         []string{"Start", "Verify"},
		OutboxField:             "outbox",
		OutboxDelegates:         []string{"insertOutbox"},
		SessionGuardedFunctions: []string{"Consume", "Revoke"},
		ForbiddenIdentifiers:    []string{"withTransaction"},
	})
}
