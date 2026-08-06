// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/chat-offline-push-delivery/spec.md#gwt-002
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-003
// readiness_case: get-notification-delivery-job-metrics-local
// readiness_case: get-incoming-call-delivery-timeline-local
// readiness_case: list-notification-delivery-job-dead-letters-local
// readiness_case: recover-notification-delivery-job-local
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/reliabletask"
	notificationapp "quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	application "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/domain"
)

type deliveryOpsStoreStub struct {
	metrics       notification.NotificationDeliveryJobMetricsSnapshot
	timeline      notification.IncomingCallDeliveryTimeline
	deadLetters   []reliabletask.DeadNotificationRecord
	recoveryError error
	recoveredID   string
	recoveredKey  string
}

func (s *deliveryOpsStoreStub) ReadIncomingCallDeliveryTimeline(
	context.Context,
	string,
) (notification.IncomingCallDeliveryTimeline, error) {
	return s.timeline, nil
}

func (s *deliveryOpsStoreStub) ReadDeliveryJobMetrics(
	context.Context,
) (notification.NotificationDeliveryJobMetricsSnapshot, error) {
	return s.metrics, nil
}

func (s *deliveryOpsStoreStub) ListDeadDeliveryJobs(
	context.Context,
	[]string,
	int,
) ([]reliabletask.DeadNotificationRecord, error) {
	return append([]reliabletask.DeadNotificationRecord(nil), s.deadLetters...), nil
}

func (s *deliveryOpsStoreStub) RecoverDeliveryJob(
	_ context.Context,
	jobID string,
	idempotencyKey string,
	_ time.Time,
) (notification.RecoverNotificationDeliveryJobResult, error) {
	s.recoveredID = jobID
	s.recoveredKey = idempotencyKey
	return notification.RecoverNotificationDeliveryJobResult{
		JobID:          jobID,
		NotificationID: "msg_1",
		Version:        2,
		AttemptEpoch:   2,
	}, s.recoveryError
}

func TestNotificationDeliveryOpsFacadesRequireEveryProductionDependency(t *testing.T) {
	store := &deliveryOpsStoreStub{}
	if _, err := application.NewNotificationDeliveryJobQueryFacade(nil, store); err == nil {
		t.Fatal("missing metrics reader must fail construction")
	}
	if _, err := application.NewNotificationDeliveryJobQueryFacade(store, nil); err == nil {
		t.Fatal("missing dead-letter reader must fail construction")
	}
	if _, err := application.NewNotificationDeliveryJobCommandFacade(nil); err == nil {
		t.Fatal("missing recovery store must fail construction")
	}
}

func TestNotificationDeliveryOpsFacadesExposeTypedSlicesAndStableRecoveryFailure(t *testing.T) {
	now := time.Date(2026, 7, 14, 10, 0, 0, 0, time.UTC)
	store := &deliveryOpsStoreStub{
		metrics: notification.NotificationDeliveryJobMetricsSnapshot{
			JobsByStatus: map[string]int64{"dead": 1},
			DeadJobs:     1,
			UpdatedAt:    now,
		},
		timeline: notification.IncomingCallDeliveryTimeline{
			CallDigest: "sha256:255bc327edf456572cddd7dea860e7298497b3f96b7d13c075ce7e61a220e4c0",
			UpdatedAt:  now,
		},
		deadLetters: []reliabletask.DeadNotificationRecord{{
			NotificationID:        "ndj_dead_1",
			SubjectNotificationID: "msg_1",
			Channel:               "push",
			EventType:             notificationapp.NotificationPushRequestedEvent,
			AggregateID:           "msg_1",
			Attempts:              5,
			AttemptEpoch:          1,
			LastFailure: &reliabletask.RuntimeFailure{
				Code: "INTEGRATION.MIDDLEWARE.provider_rejected",
			},
			UpdatedAt: now,
		}},
	}
	queries, err := application.NewNotificationDeliveryJobQueryFacade(store, store, store)
	if err != nil {
		t.Fatalf("construct query facade: %v", err)
	}
	commands, err := application.NewNotificationDeliveryJobCommandFacade(store)
	if err != nil {
		t.Fatalf("construct command facade: %v", err)
	}

	metrics, err := queries.GetMetrics(context.Background())
	if err != nil {
		t.Fatalf("get metrics: %v", err)
	}
	if metrics.DeadJobs != 1 || metrics.JobsByStatus["dead"] != 1 {
		t.Fatalf("unexpected typed metrics: %+v", metrics)
	}
	timeline, err := queries.GetIncomingCallTimeline(context.Background(), "call_1")
	if err != nil || timeline.CallDigest != "sha256:255bc327edf456572cddd7dea860e7298497b3f96b7d13c075ce7e61a220e4c0" || !timeline.UpdatedAt.Equal(now) {
		t.Fatalf("unexpected typed incoming-call timeline: %+v err=%v", timeline, err)
	}
	store.metrics.JobsByStatus["dead"] = 9
	if metrics.JobsByStatus["dead"] != 1 {
		t.Fatal("metrics result must not alias store-owned maps")
	}

	deadLetters, err := queries.ListDeadLetters(
		context.Background(),
		[]string{notificationapp.NotificationPushRequestedEvent},
		20,
	)
	if err != nil {
		t.Fatalf("list dead letters: %v", err)
	}
	if len(deadLetters.Items) != 1 ||
		deadLetters.Items[0].FailureCode != "INTEGRATION.MIDDLEWARE.provider_rejected" {
		t.Fatalf("unexpected typed dead-letter slice: %+v", deadLetters)
	}

	if _, err := queries.ListDeadLetters(context.Background(), nil, 101); errorCode(err) != "NOTIFICATION.USER.delivery_job_invalid_argument" {
		t.Fatalf("invalid limit code=%q err=%v", errorCode(err), err)
	}
	if _, err := commands.RecoverDeliveryJob(context.Background(), "ndj_dead_1", ""); errorCode(err) != "NOTIFICATION.USER.delivery_job_invalid_argument" {
		t.Fatalf("missing idempotency key code=%q err=%v", errorCode(err), err)
	}
	store.recoveryError = notification.ErrDeliveryJobNotFound
	if _, err := commands.RecoverDeliveryJob(context.Background(), "ndj_dead_1", "recover-1"); errorCode(err) != "NOTIFICATION.USER.delivery_job_not_found" {
		t.Fatalf("missing dead-letter code=%q err=%v", errorCode(err), err)
	}
	store.recoveryError = notification.ErrDeliveryJobIdempotencyConflict
	if _, err := commands.RecoverDeliveryJob(context.Background(), "ndj_dead_1", "recover-1"); errorCode(err) != "NOTIFICATION.USER.delivery_job_idempotency_conflict" {
		t.Fatalf("idempotency conflict code=%q err=%v", errorCode(err), err)
	}
	store.recoveryError = errors.New("write failed")
	if _, err := commands.RecoverDeliveryJob(context.Background(), "ndj_dead_1", "recover-2"); errorCode(err) != "NOTIFICATION.SYSTEM.delivery_job_storage_write_failed" {
		t.Fatalf("storage failure code=%q err=%v", errorCode(err), err)
	}
}

func errorCode(err error) string {
	if err == nil {
		return ""
	}
	return rterr.NormalizeError(err).Code.String()
}
