// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/homepage-claim-request-and-review/spec.md#gwt-001
package local_contract

import (
	"testing"

	"quwoquan_service/internal/platform/testinfra"
)

// homepage_claim_request_outbox 是 entity.homepage_claim_request 声明的事务性发布 seam：
// 认领请求状态与投递事件必须原子提交，不允许存在事务外的第二条追加路径。
func TestHomepageClaimRequestCommitAppendsOutboxInsideAggregateTransaction(t *testing.T) {
	testinfra.AssertTransactionalOutboxAppend(t, testinfra.TransactionalOutboxRule{
		SourcePath: "quwoquan_service/services/entity-service/internal/entity_homepage/" +
			"homepage_claim_request/infrastructure/persistence/mongo_store.go",
		CommitFunctions:      []string{"Commit"},
		OutboxField:          "outbox",
		ForbiddenIdentifiers: []string{"supportsTxn", "commitBody", "commitWithoutTransaction"},
	})
}
