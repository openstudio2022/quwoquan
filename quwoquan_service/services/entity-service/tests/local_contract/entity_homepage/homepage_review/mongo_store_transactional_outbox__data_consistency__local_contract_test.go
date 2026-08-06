// spec_ref: specs/feature-tree/shared-homepage-network/homepage-review-and-content/homepage-review-read-and-score-summary/spec.md#gwt-001
package local_contract

import (
	"testing"

	"quwoquan_service/internal/platform/testinfra"
)

// homepage_review_outbox 是 entity.homepage_review 声明的事务性发布 seam：评价聚合、
// 幂等回执与事件行必须在同一个事务句柄下提交。
func TestHomepageReviewCommitAppendsOutboxInsideAggregateTransaction(t *testing.T) {
	testinfra.AssertTransactionalOutboxAppend(t, testinfra.TransactionalOutboxRule{
		SourcePath: "quwoquan_service/services/entity-service/internal/entity_homepage/" +
			"homepage_review/infrastructure/persistence/mongo_review_store.go",
		CommitFunctions:      []string{"Commit"},
		OutboxField:          "outbox",
		ForbiddenIdentifiers: []string{"supportsTxn", "commitBody", "commitWithoutTransaction"},
	})
}
