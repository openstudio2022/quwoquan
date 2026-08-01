package reliabletaskmongo

import (
	"context"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/reliabletask"
)

// Store 使用 MongoDB 持久化可靠任务事实、通知账本与租约。
type Store struct {
	db               *mongo.Database
	outboxes         *mongo.Collection
	tasks            *mongo.Collection
	notifications    *mongo.Collection
	ledgers          *mongo.Collection
	attempts         *mongo.Collection
	resultOutboxes   *mongo.Collection
	recoveryReceipts *mongo.Collection
	leases           *mongo.Collection
}

var (
	_ reliabletask.Store                            = (*Store)(nil)
	_ reliabletask.ProviderAttemptLedgerStore       = (*Store)(nil)
	_ reliabletask.ProviderAttemptResultOutboxStore = (*Store)(nil)
	_ reliabletask.DLQRecoveryStore                 = (*Store)(nil)
	_ reliabletask.IdempotentDLQRecoveryStore       = (*Store)(nil)
	_ reliabletask.RetentionCleanupStore            = (*Store)(nil)
	_ reliabletask.MetricsStore                     = (*Store)(nil)
)

// New 创建 MongoDB 可靠任务存储适配器。
func New(db *mongo.Database) *Store {
	return newStore(db, "notification_outbox", "notification_delivery_ledger")
}

// NewExternalInteraction adds the Integration-owned provider attempt ledger
// and result outbox to the generic reliable-task queue. Other services must
// not even initialize these collections in their own databases.
func NewExternalInteraction(db *mongo.Database) *Store {
	store := newStore(db, "notification_outbox", "notification_delivery_ledger")
	store.attempts = db.Collection("external_provider_attempt_ledger")
	store.resultOutboxes = db.Collection("external_interaction_result_outbox")
	return store
}

// NewNotificationDeliveryJobs 为 notification-service 提供对象专属的
// NotificationDeliveryJob 权威集合。其他服务继续使用各自的可靠任务集合，
// 不得借此构造跨限界上下文共享的通知仓库。
func NewNotificationDeliveryJobs(db *mongo.Database) *Store {
	return newStore(db, "notification_delivery_jobs", "notification_delivery_job_recipients")
}

func newStore(db *mongo.Database, notificationCollection, ledgerCollection string) *Store {
	return &Store{
		db:               db,
		outboxes:         db.Collection("reliable_task_outbox"),
		tasks:            db.Collection("reliable_async_task"),
		notifications:    db.Collection(notificationCollection),
		ledgers:          db.Collection(ledgerCollection),
		recoveryReceipts: db.Collection("reliable_task_recovery_receipts"),
		leases:           db.Collection("reliable_task_leases"),
	}
}

func (s *Store) RunInTransaction(ctx context.Context, fn func(context.Context) error) error {
	if mongo.SessionFromContext(ctx) != nil {
		return fn(ctx)
	}
	session, err := s.db.Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		return nil, fn(txCtx)
	})
	return err
}

func (s *Store) EnsureIndexes(ctx context.Context) error {
	_, err := s.outboxes.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "idempotencyKey", Value: 1}},
			Options: options.Index().
				SetUnique(true).
				SetPartialFilterExpression(bson.M{"idempotencyKey": bson.M{"$type": "string", "$gt": ""}}),
		},
		{
			Keys: bson.D{{Key: "dedupeKey", Value: 1}, {Key: "status", Value: 1}},
			Options: options.Index().
				SetUnique(true).
				SetPartialFilterExpression(bson.M{"status": reliabletask.TaskOutboxStatusPending}),
		},
		{Keys: bson.D{{Key: "startAt", Value: 1}, {Key: "status", Value: 1}}},
		{Keys: bson.D{{Key: "shardId", Value: 1}, {Key: "startAt", Value: 1}, {Key: "status", Value: 1}}},
	})
	if err != nil {
		return err
	}
	_, err = s.tasks.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "dedupeKey", Value: 1}, {Key: "status", Value: 1}},
			Options: options.Index().
				SetUnique(true).
				SetPartialFilterExpression(bson.M{"status": bson.M{"$in": bson.A{
					reliabletask.TaskStatusReady,
					reliabletask.TaskStatusProcessing,
					reliabletask.TaskStatusRetryWait,
				}}}),
		},
		{Keys: bson.D{{Key: "nextAttemptAt", Value: 1}, {Key: "status", Value: 1}}},
	})
	if err != nil {
		return err
	}
	_, err = s.notifications.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "dedupeKey", Value: 1}}, Options: options.Index().SetUnique(true)},
		{Keys: bson.D{{Key: "nextAttemptAt", Value: 1}, {Key: "status", Value: 1}}},
	})
	if err != nil {
		return err
	}
	_, err = s.ledgers.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "notificationId", Value: 1}, {Key: "recipientId", Value: 1}}, Options: options.Index().SetUnique(true)},
		{Keys: bson.D{{Key: "notificationId", Value: 1}, {Key: "status", Value: 1}}},
	})
	if err != nil {
		return err
	}
	if s.attempts != nil {
		_, err = s.attempts.Indexes().CreateMany(ctx, []mongo.IndexModel{
			{Keys: bson.D{{Key: "requestId", Value: 1}, {Key: "createdAt", Value: 1}}},
			{Keys: bson.D{{Key: "operation", Value: 1}, {Key: "provider", Value: 1}, {Key: "status", Value: 1}}},
			{
				Keys:    bson.D{{Key: "subjectDigest", Value: 1}},
				Options: options.Index().SetName("idx_ext_attempt_subject_cleanup"),
			},
		})
		if err != nil {
			return err
		}
	}
	if s.resultOutboxes != nil {
		_, err = s.resultOutboxes.Indexes().CreateMany(ctx, []mongo.IndexModel{
			{
				Keys: bson.D{
					{Key: "deliveryStatus", Value: 1},
					{Key: "leaseExpiresAt", Value: 1},
					{Key: "createdAt", Value: 1},
				},
				Options: options.Index().
					SetName("idx_ext_result_outbox_pending"),
			},
			{
				Keys:    bson.D{{Key: "subjectDigest", Value: 1}},
				Options: options.Index().SetName("idx_ext_result_outbox_subject_cleanup"),
			},
		})
		if err != nil {
			return err
		}
	}
	_, err = s.recoveryReceipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "taskId", Value: 1}},
			Options: options.Index().SetName("idx_reliable_task_recovery_receipt_task"),
		},
		{
			Keys: bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().
				SetName("idx_reliable_task_recovery_receipt_expiry").
				SetExpireAfterSeconds(0),
		},
	})
	if err != nil {
		return err
	}
	_, err = s.leases.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "env", Value: 1},
				{Key: "domain", Value: 1},
				{Key: "module", Value: 1},
				{Key: "shardId", Value: 1},
			},
			Options: options.Index().SetUnique(true),
		},
		{Keys: bson.D{{Key: "leaseUntil", Value: 1}}},
	})
	return err
}
