// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/homepage-offline-report-and-history-retention/spec.md#gwt-001
package local_contract

import (
	"testing"

	"quwoquan_service/internal/platform/testinfra"
)

// homepage_status_report_outbox 是 entity.homepage_status_report 声明的事务性发布 seam：
// 状态上报聚合与事件行必须原子提交，事务不可用时整笔失败而不是降级为无事务写入。
func TestHomepageStatusReportCommitAppendsOutboxInsideAggregateTransaction(t *testing.T) {
	testinfra.AssertTransactionalOutboxAppend(t, testinfra.TransactionalOutboxRule{
		SourcePath: "quwoquan_service/services/entity-service/internal/entity_homepage/" +
			"homepage_status_report/infrastructure/persistence/mongo_store.go",
		CommitFunctions:      []string{"Commit"},
		OutboxField:          "outbox",
		ForbiddenIdentifiers: []string{"supportsTxn", "commitBody", "commitWithoutTransaction"},
	})
}
