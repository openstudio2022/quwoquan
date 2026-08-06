package local_contract

import (
	"testing"

	"quwoquan_service/internal/platform/testinfra"
)

// notification_delivery_jobs_outbox 是 notification.notification_delivery_job 声明的事务性
// 发布 seam：投递任务落库与 NotificationDeliveryJobCreated 事件行必须由同一个事务句柄提交，
// 这样上游 AppMessage 的同事务创建才能真正得到「状态与事件同生共死」的保证。
func TestNotificationDeliveryJobCreateAppendsOutboxInsideJobTransaction(t *testing.T) {
	testinfra.AssertTransactionalOutboxAppend(t, testinfra.TransactionalOutboxRule{
		SourcePath: "quwoquan_service/services/notification-service/internal/notification_delivery/" +
			"notification_delivery_job/infrastructure/persistence/mongo_store.go",
		CommitFunctions: []string{"CreateNotification"},
		OutboxField:     "outbox",
		StateDelegates:  []string{"CreateNotification"},
	})
}
