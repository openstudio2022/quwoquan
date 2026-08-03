package runtimeadapter

import (
	"context"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/runtime/reliabletask"
	deadletterapp "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/application"
	deadletterdomain "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/domain"
)

type Delegate interface {
	reliabletask.Store
	reliabletask.ProviderAttemptResultOutboxStore
	reliabletask.IdempotentDLQRecoveryStore
	reliabletask.RetentionCleanupStore
	reliabletask.MetricsStore
	ListDeadTasks(context.Context, []string, int) ([]reliabletask.DeadTaskRecord, error)
	FindLatestTaskOutboxByAggregateID(context.Context, string) (reliabletask.TaskOutboxRecord, bool, error)
}

// RuntimeStore 把 generic task 的 dead 终态转换成对象自有的不可变事实；任务更新
// 与事实追加共享 Delegate 的事务上下文，禁止出现“任务已死但审计事实缺失”。
type RuntimeStore struct {
	Delegate
	deadLetters *deadletterapp.Appender
}

func NewRuntimeStore(delegate Delegate, repository deadletterapp.Repository) *RuntimeStore {
	return &RuntimeStore{
		Delegate:    delegate,
		deadLetters: deadletterapp.NewAppender(repository),
	}
}

func (store *RuntimeStore) FailTask(
	ctx context.Context,
	taskID string,
	leaseToken string,
	failure reliabletask.RuntimeFailure,
	policy reliabletask.RetryPolicy,
	now time.Time,
) error {
	return store.Delegate.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := store.Delegate.FailTask(
			txCtx,
			taskID,
			leaseToken,
			failure,
			policy,
			now,
		); err != nil {
			return err
		}
		deadTask, found, err := store.findDeadTask(txCtx, taskID)
		if err != nil || !found {
			return err
		}
		attempt, found, err := store.latestAttempt(txCtx, deadTask.AggregateID, taskID)
		if err != nil {
			return err
		}
		if !found {
			return fmt.Errorf(
				"dead external interaction task %s has no provider attempt fact",
				taskID,
			)
		}
		finalError := strings.TrimSpace(failure.Message)
		if deadTask.LastFailure != nil && strings.TrimSpace(deadTask.LastFailure.Message) != "" {
			finalError = strings.TrimSpace(deadTask.LastFailure.Message)
		}
		if finalError == "" {
			finalError = "external interaction retry budget exhausted"
		}
		recoveryAction := strings.TrimSpace(attempt.RecoveryAction)
		if recoveryAction == "" || recoveryAction == "none" || recoveryAction == "retry" {
			recoveryAction = "manual_recover"
		}
		_, err = store.deadLetters.Append(txCtx, deadletterdomain.Fact{
			DeadLetterID: "dead-letter-" + deadTask.TaskID,
			TaskID:       deadTask.TaskID,
			RequestID:    deadTask.AggregateID,
			Operation: strings.TrimPrefix(
				deadTask.TaskType,
				reliabletask.ExternalInteractionTaskPrefix,
			),
			Provider:       attempt.Provider,
			FinalError:     finalError,
			Retryable:      false,
			RecoveryAction: recoveryAction,
			CreatedAt:      deadTask.UpdatedAt,
		})
		return err
	})
}

func (store *RuntimeStore) ListExternalInteractionDeadLetterFacts(
	ctx context.Context,
	requestID string,
) ([]deadletterdomain.Fact, error) {
	return store.deadLetters.ListByRequest(ctx, requestID)
}

func (store *RuntimeStore) findDeadTask(
	ctx context.Context,
	taskID string,
) (reliabletask.DeadTaskRecord, bool, error) {
	tasks, err := store.Delegate.ListDeadTasks(ctx, nil, 0)
	if err != nil {
		return reliabletask.DeadTaskRecord{}, false, err
	}
	for _, task := range tasks {
		if task.TaskID == taskID {
			return task, true, nil
		}
	}
	return reliabletask.DeadTaskRecord{}, false, nil
}

func (store *RuntimeStore) latestAttempt(
	ctx context.Context,
	requestID string,
	taskID string,
) (reliabletask.ProviderAttemptRecord, bool, error) {
	attempts, err := store.Delegate.ListProviderAttempts(ctx, requestID)
	if err != nil {
		return reliabletask.ProviderAttemptRecord{}, false, err
	}
	var latest reliabletask.ProviderAttemptRecord
	found := false
	for _, attempt := range attempts {
		if attempt.TaskID != taskID {
			continue
		}
		if !found || attempt.CreatedAt.After(latest.CreatedAt) {
			latest = attempt
			found = true
		}
	}
	return latest, found, nil
}
