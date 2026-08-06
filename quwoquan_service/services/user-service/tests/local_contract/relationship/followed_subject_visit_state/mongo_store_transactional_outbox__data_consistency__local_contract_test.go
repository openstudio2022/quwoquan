package local_contract

import (
	"testing"

	"quwoquan_service/internal/platform/testinfra"
)

// followed_subject_visit_outbox 是 user.followed_subject_visit_state 声明的事务性发布 seam：
// 访问水位与 FollowedSubjectVisited 事件行必须在同一个事务句柄下提交，否则关注红点会出现
// 「水位已推进、事件丢失」的中间态。
func TestFollowedSubjectVisitMarkVisitedAppendsOutboxInsideVisitTransaction(t *testing.T) {
	testinfra.AssertTransactionalOutboxAppend(t, testinfra.TransactionalOutboxRule{
		SourcePath: "quwoquan_service/services/user-service/internal/relationship/" +
			"followed_subject_visit_state/infrastructure/persistence/mongo_store.go",
		CommitFunctions: []string{"MarkVisited"},
		OutboxField:     "outbox",
	})
}
