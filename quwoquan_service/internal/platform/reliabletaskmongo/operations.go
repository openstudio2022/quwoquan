package reliabletaskmongo

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/reliabletask"
)

func (s *Store) ListDeadTasks(
	ctx context.Context,
	taskTypes []string,
	limit int,
) ([]reliabletask.DeadTaskRecord, error) {
	filter := bson.M{"status": reliabletask.TaskStatusDead}
	if len(taskTypes) > 0 {
		filter["taskType"] = bson.M{"$in": taskTypes}
	}
	opts := options.Find().SetSort(bson.D{{Key: "updatedAt", Value: 1}})
	if limit > 0 {
		opts.SetLimit(int64(limit))
	}
	cursor, err := s.tasks.Find(ctx, filter, opts)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var out []reliabletask.DeadTaskRecord
	for cursor.Next(ctx) {
		var task reliabletask.ReliableAsyncTask
		if err := cursor.Decode(&task); err != nil {
			return nil, err
		}
		out = append(out, reliabletask.DeadTaskRecord{
			TaskID:      task.TaskID,
			TaskType:    task.TaskType,
			AggregateID: task.AggregateID,
			Attempts:    task.Attempts,
			LastFailure: task.LastFailure,
			Payload:     reliabletask.CloneStringMap(task.Payload),
			UpdatedAt:   task.UpdatedAt,
		})
	}
	return out, cursor.Err()
}

// FindLatestTaskOutboxByAggregateID 返回聚合的最新任务 outbox 记录，
// 供外部交互请求状态查询派生归一化状态。
func (s *Store) FindLatestTaskOutboxByAggregateID(
	ctx context.Context,
	aggregateID string,
) (reliabletask.TaskOutboxRecord, bool, error) {
	var record reliabletask.TaskOutboxRecord
	err := s.outboxes.FindOne(
		ctx,
		bson.M{"aggregateId": strings.TrimSpace(aggregateID)},
		options.FindOne().SetSort(bson.D{{Key: "updatedAt", Value: -1}}),
	).Decode(&record)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return reliabletask.TaskOutboxRecord{}, false, nil
	}
	if err != nil {
		return reliabletask.TaskOutboxRecord{}, false, err
	}
	return record, true, nil
}

func (s *Store) RecoverDeadTask(ctx context.Context, taskID string, now time.Time) error {
	res, err := s.tasks.UpdateOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(taskID), "status": reliabletask.TaskStatusDead},
		bson.M{
			"$set": bson.M{
				"status":        reliabletask.TaskStatusReady,
				"nextAttemptAt": now.UTC(),
				"leaseOwner":    "",
				"leaseToken":    "",
				"leaseUntil":    time.Time{},
				"updatedAt":     now.UTC(),
			},
		},
	)
	if err != nil {
		return err
	}
	if res.MatchedCount == 0 {
		return reliabletask.ErrTaskNotFound
	}
	return nil
}

func (s *Store) ListDeadNotifications(
	ctx context.Context,
	eventTypes []string,
	limit int,
) ([]reliabletask.DeadNotificationRecord, error) {
	filter := bson.M{"status": reliabletask.NotificationStatusDead}
	if len(eventTypes) > 0 {
		filter["eventType"] = bson.M{"$in": eventTypes}
	}
	opts := options.Find().SetSort(bson.D{{Key: "updatedAt", Value: 1}})
	if limit > 0 {
		opts.SetLimit(int64(limit))
	}
	cursor, err := s.notifications.Find(ctx, filter, opts)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var out []reliabletask.DeadNotificationRecord
	for cursor.Next(ctx) {
		var notification reliabletask.NotificationOutboxRecord
		if err := cursor.Decode(&notification); err != nil {
			return nil, err
		}
		out = append(out, reliabletask.DeadNotificationRecord{
			NotificationID:        notification.NotificationID,
			SubjectNotificationID: notification.SubjectNotificationID,
			Channel:               notification.Channel,
			EventType:             notification.EventType,
			AggregateID:           notification.AggregateID,
			Attempts:              notification.Attempts,
			AttemptEpoch:          notification.AttemptEpoch,
			LastFailure:           notification.LastFailure,
			UpdatedAt:             notification.UpdatedAt,
		})
	}
	return out, cursor.Err()
}

func (s *Store) RecoverDeadNotification(
	ctx context.Context,
	notificationID string,
	now time.Time,
) error {
	res, err := s.notifications.UpdateOne(
		ctx,
		bson.M{
			"_id":    strings.TrimSpace(notificationID),
			"status": reliabletask.NotificationStatusDead,
		},
		bson.M{
			"$set": bson.M{
				"status":        reliabletask.NotificationStatusPending,
				"nextAttemptAt": now.UTC(),
				"leaseOwner":    "",
				"leaseToken":    "",
				"leaseUntil":    time.Time{},
				"updatedAt":     now.UTC(),
			},
		},
	)
	if err != nil {
		return err
	}
	if res.MatchedCount == 0 {
		return reliabletask.ErrNotificationNotFound
	}
	return nil
}

func (s *Store) CleanupReliableTaskRetention(
	ctx context.Context,
	policy reliabletask.RetentionPolicy,
	now time.Time,
) (reliabletask.RetentionCleanupResult, error) {
	var result reliabletask.RetentionCleanupResult
	if policy.Outbox.DispatchedTTL > 0 {
		res, err := s.outboxes.DeleteMany(ctx, bson.M{
			"status": reliabletask.TaskOutboxStatusDispatched,
			"updatedAt": bson.M{
				"$lt": now.Add(-policy.Outbox.DispatchedTTL),
			},
		})
		if err != nil {
			return result, err
		}
		result.OutboxesDeleted = res.DeletedCount
	}
	if policy.Task.DoneTTL > 0 || policy.Task.DeadTTL > 0 {
		ors := bson.A{}
		if policy.Task.DoneTTL > 0 {
			ors = append(ors, bson.M{
				"status": reliabletask.TaskStatusSucceeded,
				"updatedAt": bson.M{
					"$lt": now.Add(-policy.Task.DoneTTL),
				},
			})
		}
		if policy.Task.DeadTTL > 0 {
			ors = append(ors, bson.M{
				"status": reliabletask.TaskStatusDead,
				"updatedAt": bson.M{
					"$lt": now.Add(-policy.Task.DeadTTL),
				},
			})
		}
		res, err := s.tasks.DeleteMany(ctx, bson.M{"$or": ors})
		if err != nil {
			return result, err
		}
		result.TasksDeleted = res.DeletedCount
	}
	if policy.Notification.DoneTTL > 0 || policy.Notification.DeadTTL > 0 {
		ors := bson.A{}
		if policy.Notification.DoneTTL > 0 {
			ors = append(ors, bson.M{
				"status": reliabletask.NotificationStatusSucceeded,
				"updatedAt": bson.M{
					"$lt": now.Add(-policy.Notification.DoneTTL),
				},
			})
		}
		if policy.Notification.DeadTTL > 0 {
			ors = append(ors, bson.M{
				"status": reliabletask.NotificationStatusDead,
				"updatedAt": bson.M{
					"$lt": now.Add(-policy.Notification.DeadTTL),
				},
			})
		}
		res, err := s.notifications.DeleteMany(ctx, bson.M{"$or": ors})
		if err != nil {
			return result, err
		}
		result.NotificationsDeleted = res.DeletedCount
	}
	if policy.DeliveryLedger.DeliveredTTL > 0 {
		res, err := s.ledgers.DeleteMany(ctx, bson.M{
			"status": reliabletask.RecipientStatusDelivered,
			"updatedAt": bson.M{
				"$lt": now.Add(-policy.DeliveryLedger.DeliveredTTL),
			},
		})
		if err != nil {
			return result, err
		}
		result.LedgersDeleted = res.DeletedCount
		attemptRes, err := s.attempts.DeleteMany(ctx, bson.M{
			"createdAt": bson.M{
				"$lt": now.Add(-policy.DeliveryLedger.DeliveredTTL),
			},
		})
		if err != nil {
			return result, err
		}
		result.AttemptsDeleted = attemptRes.DeletedCount
	}
	return result, nil
}

func (s *Store) ReliableTaskMetrics(
	ctx context.Context,
) (reliabletask.MetricsSnapshot, error) {
	snapshot := reliabletask.MetricsSnapshot{
		TasksByStatus:         map[string]int64{},
		NotificationsByStatus: map[string]int64{},
		ProviderAttempts:      map[string]int64{},
		UpdatedAt:             time.Now().UTC(),
	}
	taskCursor, err := s.tasks.Aggregate(ctx, bson.A{
		bson.M{"$group": bson.M{"_id": "$status", "count": bson.M{"$sum": 1}}},
	})
	if err != nil {
		return snapshot, err
	}
	defer taskCursor.Close(ctx)
	for taskCursor.Next(ctx) {
		var row struct {
			ID    string `bson:"_id"`
			Count int64  `bson:"count"`
		}
		if err := taskCursor.Decode(&row); err != nil {
			return snapshot, err
		}
		snapshot.TasksByStatus[row.ID] = row.Count
		if row.ID == reliabletask.TaskStatusDead {
			snapshot.DeadTasks = row.Count
		}
	}
	notificationCursor, err := s.notifications.Aggregate(ctx, bson.A{
		bson.M{"$group": bson.M{"_id": "$status", "count": bson.M{"$sum": 1}}},
	})
	if err != nil {
		return snapshot, err
	}
	defer notificationCursor.Close(ctx)
	for notificationCursor.Next(ctx) {
		var row struct {
			ID    string `bson:"_id"`
			Count int64  `bson:"count"`
		}
		if err := notificationCursor.Decode(&row); err != nil {
			return snapshot, err
		}
		snapshot.NotificationsByStatus[row.ID] = row.Count
		if row.ID == reliabletask.NotificationStatusDead {
			snapshot.DeadNotifications = row.Count
		}
	}
	attemptCursor, err := s.attempts.Aggregate(ctx, bson.A{
		bson.M{
			"$group": bson.M{
				"_id": bson.M{
					"operation": "$operation",
					"provider":  "$provider",
					"status":    "$status",
				},
				"count": bson.M{"$sum": 1},
			},
		},
	})
	if err != nil {
		return snapshot, err
	}
	defer attemptCursor.Close(ctx)
	for attemptCursor.Next(ctx) {
		var row struct {
			ID struct {
				Operation string `bson:"operation"`
				Provider  string `bson:"provider"`
				Status    string `bson:"status"`
			} `bson:"_id"`
			Count int64 `bson:"count"`
		}
		if err := attemptCursor.Decode(&row); err != nil {
			return snapshot, err
		}
		key := row.ID.Operation + ":" + row.ID.Provider + ":" + row.ID.Status
		snapshot.ProviderAttempts[key] = row.Count
	}
	return snapshot, nil
}
