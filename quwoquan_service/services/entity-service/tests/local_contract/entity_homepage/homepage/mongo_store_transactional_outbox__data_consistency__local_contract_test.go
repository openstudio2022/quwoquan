package local_contract

import (
	"testing"

	"quwoquan_service/internal/platform/testinfra"
)

// homepage_outbox 是 entity.homepage 声明的事务性发布 seam。Commit 必须在同一个 Mongo
// 事务句柄下写聚合状态并追加事件；一旦回退到「事务不可用就直接写」的旁路，状态会在事件
// 丢失的情况下提交，这里的断言就会失败。
func TestHomepageCommitAppendsOutboxInsideAggregateTransaction(t *testing.T) {
	testinfra.AssertTransactionalOutboxAppend(t, testinfra.TransactionalOutboxRule{
		SourcePath: "quwoquan_service/services/entity-service/internal/entity_homepage/" +
			"homepage/infrastructure/persistence/mongo_homepage_store.go",
		CommitFunctions:      []string{"Commit"},
		OutboxField:          "outbox",
		ForbiddenIdentifiers: []string{"supportsTxn", "commitBody", "commitWithoutTransaction"},
	})
}
