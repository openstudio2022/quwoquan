// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/interaction-notification-inbox/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification/domain"
)

// Notification（AppMessage）自身没有发布 seam：跨边界推送的可靠性由同事务创建的
// NotificationDeliveryJob 承担。这批用例把「同事务原子提交」钉成可失败的契约——
// 聚合写入与投递任务追加必须落在同一个事务边界内，任一步失败两者一起回滚。

type atomicityTxKey struct{}

type stagedNotificationJournal struct {
	mu                sync.Mutex
	committedMessages []notification.AppMessage
	committedJobs     []reliabletask.NotificationOutboxRecord
	pendingMessages   []notification.AppMessage
	pendingJobs       []reliabletask.NotificationOutboxRecord
}

func (journal *stagedNotificationJournal) RunInTransaction(
	ctx context.Context,
	fn func(context.Context) error,
) error {
	err := fn(context.WithValue(ctx, atomicityTxKey{}, true))
	journal.mu.Lock()
	defer journal.mu.Unlock()
	if err != nil {
		journal.pendingMessages = nil
		journal.pendingJobs = nil
		return err
	}
	journal.committedMessages = append(journal.committedMessages, journal.pendingMessages...)
	journal.committedJobs = append(journal.committedJobs, journal.pendingJobs...)
	journal.pendingMessages = nil
	journal.pendingJobs = nil
	return nil
}

var errWriteOutsideTransaction = errors.New("write escaped the commit transaction boundary")

func inAtomicityTransaction(ctx context.Context) bool {
	marked, _ := ctx.Value(atomicityTxKey{}).(bool)
	return marked
}

type stagedAppMessageStore struct {
	journal *stagedNotificationJournal
}

func (store stagedAppMessageStore) Create(
	ctx context.Context,
	message notification.AppMessage,
) (notification.AppMessage, bool, error) {
	if !inAtomicityTransaction(ctx) {
		return notification.AppMessage{}, false, errWriteOutsideTransaction
	}
	store.journal.mu.Lock()
	defer store.journal.mu.Unlock()
	store.journal.pendingMessages = append(store.journal.pendingMessages, message)
	return message, true, nil
}

func (store stagedAppMessageStore) FindByIdempotencyKey(
	_ context.Context,
	key string,
) (notification.AppMessage, bool, error) {
	store.journal.mu.Lock()
	defer store.journal.mu.Unlock()
	for _, message := range store.journal.committedMessages {
		if message.IdempotencyKey == key {
			return message, true, nil
		}
	}
	return notification.AppMessage{}, false, nil
}

func (stagedAppMessageStore) Acknowledge(
	context.Context, string, string, time.Time,
) (notification.AppMessage, error) {
	return notification.AppMessage{}, errors.New("acknowledge is not part of this contract")
}

func (stagedAppMessageStore) MarkRead(
	context.Context, string, string, time.Time,
) (notification.AppMessage, error) {
	return notification.AppMessage{}, errors.New("mark read is not part of this contract")
}

type stagedDeliveryJobOutbox struct {
	journal *stagedNotificationJournal
	failure error
}

func (outbox *stagedDeliveryJobOutbox) CreateNotification(
	ctx context.Context,
	record reliabletask.NotificationOutboxRecord,
) (reliabletask.NotificationOutboxRecord, error) {
	if !inAtomicityTransaction(ctx) {
		return reliabletask.NotificationOutboxRecord{}, errWriteOutsideTransaction
	}
	if outbox.failure != nil {
		return reliabletask.NotificationOutboxRecord{}, outbox.failure
	}
	outbox.journal.mu.Lock()
	defer outbox.journal.mu.Unlock()
	outbox.journal.pendingJobs = append(outbox.journal.pendingJobs, record)
	return record, nil
}

func newAtomicityCommandFacade(
	t *testing.T,
	outboxFailure error,
) (*application.AppMessageCommandFacade, *stagedNotificationJournal) {
	t.Helper()
	journal := &stagedNotificationJournal{}
	facade, err := application.NewAppMessageCommandFacade(
		stagedAppMessageStore{journal: journal},
		journal,
		&stagedDeliveryJobOutbox{journal: journal, failure: outboxFailure},
	)
	if err != nil {
		t.Fatalf("new AppMessage command facade: %v", err)
	}
	return facade, journal
}

func atomicityCreateCommand(idempotencyKey string) application.CreateAppMessageCommand {
	return application.CreateAppMessageCommand{
		IdempotencyKey: idempotencyKey,
		UserID:         "user-atomicity-1",
		MessageType:    "system",
		Source:         "content-service",
		SourceID:       "post-atomicity-1",
		Title:          "新的互动通知",
		Summary:        "有人评论了你的内容",
		Target: notification.AppMessageTarget{
			TargetType: "post",
			TargetID:   "post-atomicity-1",
		},
	}
}

func TestAppMessageCreateCommitsAggregateAndDeliveryJobInOneTransaction(t *testing.T) {
	facade, journal := newAtomicityCommandFacade(t, nil)

	created, err := facade.Create(context.Background(), atomicityCreateCommand("idem-atomicity-ok"))
	if err != nil {
		t.Fatalf("create app message: %v", err)
	}

	if len(journal.committedMessages) != 1 {
		t.Fatalf("committed app messages=%d want=1", len(journal.committedMessages))
	}
	if len(journal.committedJobs) != 1 {
		t.Fatalf("committed delivery jobs=%d want=1", len(journal.committedJobs))
	}
	if len(journal.pendingMessages) != 0 || len(journal.pendingJobs) != 0 {
		t.Fatalf(
			"staged writes survived the commit: messages=%d jobs=%d",
			len(journal.pendingMessages),
			len(journal.pendingJobs),
		)
	}
	job := journal.committedJobs[0]
	if job.SubjectNotificationID != created.MessageID {
		t.Fatalf(
			"delivery job subject=%q does not bind the committed message=%q",
			job.SubjectNotificationID,
			created.MessageID,
		)
	}
	if job.DedupeKey != "app-message:idem-atomicity-ok" {
		t.Fatalf("delivery job dedupeKey=%q want app-message:idem-atomicity-ok", job.DedupeKey)
	}
	if job.Status != reliabletask.NotificationStatusPending {
		t.Fatalf("delivery job status=%q want pending", job.Status)
	}
}

func TestAppMessageCreateRollsBackAggregateWhenDeliveryJobAppendFails(t *testing.T) {
	appendFailure := errors.New("delivery job outbox append failed")
	facade, journal := newAtomicityCommandFacade(t, appendFailure)

	if _, err := facade.Create(
		context.Background(),
		atomicityCreateCommand("idem-atomicity-rollback"),
	); err == nil {
		t.Fatal("create app message succeeded while the delivery job append failed")
	}

	if len(journal.committedMessages) != 0 {
		t.Fatalf(
			"app message survived a failed delivery job append: %d committed",
			len(journal.committedMessages),
		)
	}
	if len(journal.committedJobs) != 0 {
		t.Fatalf("delivery job committed despite append failure: %d", len(journal.committedJobs))
	}
	if len(journal.pendingMessages) != 0 || len(journal.pendingJobs) != 0 {
		t.Fatalf(
			"staged writes survived the rollback: messages=%d jobs=%d",
			len(journal.pendingMessages),
			len(journal.pendingJobs),
		)
	}

	// 回滚后重放同一个 idempotency key 必须重新走完整提交路径，而不是命中半提交状态。
	replayFacade, replayJournal := newAtomicityCommandFacade(t, nil)
	if _, err := replayFacade.Create(
		context.Background(),
		atomicityCreateCommand("idem-atomicity-rollback"),
	); err != nil {
		t.Fatalf("replay create after rollback: %v", err)
	}
	if len(replayJournal.committedMessages) != 1 || len(replayJournal.committedJobs) != 1 {
		t.Fatalf(
			"replay did not commit both sides: messages=%d jobs=%d",
			len(replayJournal.committedMessages),
			len(replayJournal.committedJobs),
		)
	}
}
