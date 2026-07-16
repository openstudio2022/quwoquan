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
	db            *mongo.Database
	outboxes      *mongo.Collection
	tasks         *mongo.Collection
	notifications *mongo.Collection
	ledgers       *mongo.Collection
	attempts      *mongo.Collection
	leases        *mongo.Collection
}

var (
	_ reliabletask.Store                      = (*Store)(nil)
	_ reliabletask.ProviderAttemptLedgerStore = (*Store)(nil)
	_ reliabletask.DLQRecoveryStore           = (*Store)(nil)
	_ reliabletask.RetentionCleanupStore      = (*Store)(nil)
	_ reliabletask.MetricsStore               = (*Store)(nil)
)

// New 创建 MongoDB 可靠任务存储适配器。
func New(db *mongo.Database) *Store {
	return newStore(db, "notification_outbox", "notification_delivery_ledger")
}

// NewNotificationDeliveryJobs 为 notification-service 提供对象专属的
// NotificationDeliveryJob 权威集合。其他服务继续使用各自的可靠任务集合，
// 不得借此构造跨限界上下文共享的通知仓库。
func NewNotificationDeliveryJobs(db *mongo.Database) *Store {
	return newStore(db, "notification_delivery_jobs", "notification_delivery_job_recipients")
}

func newStore(db *mongo.Database, notificationCollection, ledgerCollection string) *Store {
	return &Store{
		db:            db,
		outboxes:      db.Collection("reliable_task_outbox"),
		tasks:         db.Collection("reliable_async_task"),
		notifications: db.Collection(notificationCollection),
		ledgers:       db.Collection(ledgerCollection),
		attempts:      db.Collection("external_provider_attempt_ledger"),
		leases:        db.Collection("reliable_task_leases"),
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
	_, err = s.attempts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "requestId", Value: 1}, {Key: "createdAt", Value: 1}}},
		{Keys: bson.D{{Key: "operation", Value: 1}, {Key: "provider", Value: 1}, {Key: "status", Value: 1}}},
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
