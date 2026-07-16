package reliabletaskmongo

import (
	"context"
	"errors"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/runtime/reliabletask"
)

func (s *Store) CompleteTask(ctx context.Context, taskID string, leaseToken string) error {
	res, err := s.tasks.UpdateOne(ctx, bson.M{"_id": taskID, "leaseToken": leaseToken}, bson.M{
		"$set": bson.M{
			"status":     reliabletask.TaskStatusSucceeded,
			"leaseOwner": "",
			"leaseToken": "",
			"updatedAt":  time.Now().UTC(),
		},
	})
	if err != nil {
		return err
	}
	if res.MatchedCount == 0 {
		return reliabletask.ErrLeaseMismatch
	}
	return nil
}

func (s *Store) FailTask(
	ctx context.Context,
	taskID string,
	leaseToken string,
	failure reliabletask.RuntimeFailure,
	policy reliabletask.RetryPolicy,
	now time.Time,
) error {
	var task reliabletask.ReliableAsyncTask
	if err := s.tasks.FindOne(ctx, bson.M{"_id": taskID, "leaseToken": leaseToken}).Decode(&task); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return reliabletask.ErrLeaseMismatch
		}
		return err
	}
	task.Attempts++
	task.LastFailure = &failure
	task.LeaseOwner = ""
	task.LeaseToken = ""
	task.UpdatedAt = now.UTC()
	if delay, retry := policy.NextDelay(task.Attempts); retry {
		task.Status = reliabletask.TaskStatusRetryWait
		task.NextAttemptAt = now.Add(delay).UTC()
	} else {
		task.Status = reliabletask.TaskStatusDead
	}
	_, err := s.tasks.ReplaceOne(ctx, bson.M{"_id": taskID}, task)
	return err
}
