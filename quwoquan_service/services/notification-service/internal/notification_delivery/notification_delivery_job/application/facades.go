package application

import (
	"context"
	"errors"
	"fmt"
	"reflect"
	"strings"
	"time"

	"quwoquan_service/runtime/reliabletask"
	generated "quwoquan_service/services/notification-service/generated/notification_delivery/notification"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/domain"
)

const maxNotificationDeadLetterPageSize = 100

func isNilDependency(value any) bool {
	if value == nil {
		return true
	}
	v := reflect.ValueOf(value)
	switch v.Kind() {
	case reflect.Chan, reflect.Func, reflect.Interface, reflect.Map, reflect.Pointer, reflect.Slice:
		return v.IsNil()
	default:
		return false
	}
}

type NotificationDeliveryMetricsReader interface {
	ReadDeliveryJobMetrics(ctx context.Context) (notification.NotificationDeliveryJobMetricsSnapshot, error)
}

type NotificationDeadLetterReader interface {
	ListDeadDeliveryJobs(
		ctx context.Context,
		eventTypes []string,
		limit int,
	) ([]reliabletask.DeadNotificationRecord, error)
}

type IncomingCallDeliveryTimelineReader interface {
	ReadIncomingCallDeliveryTimeline(
		context.Context,
		string,
	) (notification.IncomingCallDeliveryTimeline, error)
}

type NotificationDeliveryJobRecoveryStore interface {
	RecoverDeliveryJob(
		ctx context.Context,
		jobID string,
		idempotencyKey string,
		now time.Time,
	) (notification.RecoverNotificationDeliveryJobResult, error)
}

type NotificationDeliveryJobQueryFacade struct {
	metricsReader    NotificationDeliveryMetricsReader
	deadLetterReader NotificationDeadLetterReader
	timelineReader   IncomingCallDeliveryTimelineReader
}

type NotificationDeliveryJobCommandFacade struct {
	recoveryStore NotificationDeliveryJobRecoveryStore
	now           func() time.Time
}

func NewNotificationDeliveryJobQueryFacade(
	metricsReader NotificationDeliveryMetricsReader,
	deadLetterReader NotificationDeadLetterReader,
	timelineReaders ...IncomingCallDeliveryTimelineReader,
) (*NotificationDeliveryJobQueryFacade, error) {
	if isNilDependency(metricsReader) {
		return nil, fmt.Errorf("notification delivery metrics reader is required")
	}
	if isNilDependency(deadLetterReader) {
		return nil, fmt.Errorf("notification dead-letter reader is required")
	}
	var timelineReader IncomingCallDeliveryTimelineReader
	if len(timelineReaders) > 0 {
		timelineReader = timelineReaders[0]
	}
	return &NotificationDeliveryJobQueryFacade{
		metricsReader:    metricsReader,
		deadLetterReader: deadLetterReader,
		timelineReader:   timelineReader,
	}, nil
}

func (f *NotificationDeliveryJobQueryFacade) GetIncomingCallTimeline(
	ctx context.Context,
	callID string,
) (notification.IncomingCallDeliveryTimeline, error) {
	callID = strings.TrimSpace(callID)
	if callID == "" {
		return notification.IncomingCallDeliveryTimeline{},
			generated.AppErrorFromInvalidArgument("callId is required")
	}
	if isNilDependency(f.timelineReader) {
		return notification.IncomingCallDeliveryTimeline{},
			generated.AppErrorFromStorageReadFailed("incoming call timeline reader is unavailable")
	}
	timeline, err := f.timelineReader.ReadIncomingCallDeliveryTimeline(ctx, callID)
	if err != nil {
		return notification.IncomingCallDeliveryTimeline{},
			generated.AppErrorFromStorageReadFailed(err.Error())
	}
	return timeline, nil
}

func NewNotificationDeliveryJobCommandFacade(
	recoveryStore NotificationDeliveryJobRecoveryStore,
) (*NotificationDeliveryJobCommandFacade, error) {
	if isNilDependency(recoveryStore) {
		return nil, fmt.Errorf("notification dead-letter recovery store is required")
	}
	return &NotificationDeliveryJobCommandFacade{
		recoveryStore: recoveryStore,
		now:           func() time.Time { return time.Now().UTC() },
	}, nil
}

func (f *NotificationDeliveryJobQueryFacade) GetMetrics(
	ctx context.Context,
) (notification.NotificationDeliveryJobMetricsSnapshot, error) {
	snapshot, err := f.metricsReader.ReadDeliveryJobMetrics(ctx)
	if err != nil {
		return notification.NotificationDeliveryJobMetricsSnapshot{},
			generated.AppErrorFromStorageReadFailed(err.Error())
	}
	snapshot.JobsByStatus = cloneCounts(snapshot.JobsByStatus)
	snapshot.UpdatedAt = snapshot.UpdatedAt.UTC()
	return snapshot, nil
}

func (f *NotificationDeliveryJobQueryFacade) ListDeadLetters(
	ctx context.Context,
	eventTypes []string,
	limit int,
) (notification.NotificationDeliveryJobDeadLetterSlice, error) {
	if limit <= 0 || limit > maxNotificationDeadLetterPageSize {
		return notification.NotificationDeliveryJobDeadLetterSlice{},
			generated.AppErrorFromInvalidArgument("limit must be between 1 and 100")
	}
	normalizedEventTypes := normalizeNonEmptyStrings(eventTypes)
	records, err := f.deadLetterReader.ListDeadDeliveryJobs(
		ctx,
		normalizedEventTypes,
		limit,
	)
	if err != nil {
		return notification.NotificationDeliveryJobDeadLetterSlice{},
			generated.AppErrorFromStorageReadFailed(err.Error())
	}
	items := make([]notification.NotificationDeliveryJobDeadLetter, 0, len(records))
	for _, record := range records {
		failureCode := ""
		if record.LastFailure != nil {
			failureCode = strings.TrimSpace(record.LastFailure.Code)
		}
		items = append(items, notification.NotificationDeliveryJobDeadLetter{
			JobID:          strings.TrimSpace(record.NotificationID),
			NotificationID: strings.TrimSpace(record.SubjectNotificationID),
			Channel:        strings.TrimSpace(record.Channel),
			EventType:      strings.TrimSpace(record.EventType),
			Attempts:       record.Attempts,
			AttemptEpoch:   record.AttemptEpoch,
			FailureCode:    failureCode,
			UpdatedAt:      record.UpdatedAt.UTC(),
		})
	}
	return notification.NotificationDeliveryJobDeadLetterSlice{Items: items}, nil
}

func (f *NotificationDeliveryJobCommandFacade) RecoverDeliveryJob(
	ctx context.Context,
	jobID string,
	idempotencyKey string,
) (notification.RecoverNotificationDeliveryJobResult, error) {
	jobID = strings.TrimSpace(jobID)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if jobID == "" {
		return notification.RecoverNotificationDeliveryJobResult{},
			generated.AppErrorFromInvalidArgument("jobId is required")
	}
	if idempotencyKey == "" {
		return notification.RecoverNotificationDeliveryJobResult{},
			generated.AppErrorFromInvalidArgument("Idempotency-Key is required")
	}
	result, err := f.recoveryStore.RecoverDeliveryJob(ctx, jobID, idempotencyKey, f.now().UTC())
	if err != nil {
		if errors.Is(err, notification.ErrDeliveryJobNotFound) {
			return notification.RecoverNotificationDeliveryJobResult{},
				generated.AppErrorFromDeliveryNotFound("notification delivery job was not found in dead-letter state")
		}
		if errors.Is(err, notification.ErrDeliveryJobIdempotencyConflict) {
			return notification.RecoverNotificationDeliveryJobResult{},
				generated.AppErrorFromIdempotencyConflict("idempotency key is already bound to another delivery job")
		}
		return notification.RecoverNotificationDeliveryJobResult{},
			generated.AppErrorFromStorageWriteFailed(err.Error())
	}
	return result, nil
}

func cloneCounts(source map[string]int64) map[string]int64 {
	cloned := make(map[string]int64, len(source))
	for key, value := range source {
		cloned[key] = value
	}
	return cloned
}

func normalizeNonEmptyStrings(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	normalized := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		normalized = append(normalized, value)
	}
	return normalized
}
