package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/reliabletask"
	deliverydomain "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/domain"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/domain"
)

func (s *MongoNotificationDeliveryJobStore) appendIncomingCallEvent(
	ctx context.Context,
	job notification.IncomingCallDeliveryJob,
	eventType string,
	occurredAt time.Time,
) error {
	payload, err := incomingCallEventPayload(job, eventType)
	if err != nil {
		return err
	}
	eventID := fmt.Sprintf("%s:%020d:%s", job.ID, job.Version, eventType)
	_, err = s.outbox.UpdateOne(
		ctx,
		bson.M{"_id": eventID},
		bson.M{"$setOnInsert": notificationDeliveryJobEventDocument{
			ID:               eventID,
			AggregateID:      job.ID,
			AggregateVersion: job.Version,
			EventType:        eventType,
			Payload:          payload,
			Status:           reliabletask.TaskOutboxStatusPending,
			CreatedAt:        occurredAt.UTC(),
		}},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

func incomingCallEventPayload(
	job notification.IncomingCallDeliveryJob,
	eventType string,
) (map[string]string, error) {
	base := map[string]string{
		"id": job.ID, "callId": job.CallID, "deviceId": job.DeviceID, "deliveryKey": job.DeliveryKey,
	}
	requiredTime := func(field string, value *time.Time) error {
		if value == nil || value.IsZero() {
			return fmt.Errorf("%s requires %s", eventType, field)
		}
		base[field] = value.UTC().Format(time.RFC3339Nano)
		return nil
	}
	switch eventType {
	case "NotificationDeliveryJobCreated":
		return map[string]string{"id": job.ID}, nil
	case "IncomingCallRealtimeDispatched":
		base["targetPersonaId"] = job.TargetPersonaID
		if err := requiredTime("ackDeadlineAt", job.AckDeadlineAt); err != nil {
			return nil, err
		}
	case "IncomingCallRealtimePresented":
		if err := requiredTime("presentedAt", job.PresentedAt); err != nil {
			return nil, err
		}
	case "IncomingCallPushQueued":
		base["expiresAt"] = job.ExpiresAt.UTC().Format(time.RFC3339Nano)
	case "IncomingCallExternalInteractionAccepted":
		base["externalInteractionId"] = job.ExternalInteractionID
		if err := requiredTime("externalInteractionAcceptedAt", job.ExternalInteractionAcceptedAt); err != nil {
			return nil, err
		}
	case "IncomingCallDeliveryCancelled":
		base["status"] = job.Status
	case "IncomingCallCancellationPushSubmitted":
		base["cancellationExternalInteractionId"] = job.CancellationExternalInteractionID
		if err := requiredTime("cancellationPushSubmittedAt", job.CancellationPushSubmittedAt); err != nil {
			return nil, err
		}
	case "IncomingCallCancellationExternalInteractionAccepted":
		base["cancellationExternalInteractionId"] = job.CancellationExternalInteractionID
		if err := requiredTime("cancellationExternalInteractionAcceptedAt", job.CancellationExternalInteractionAcceptedAt); err != nil {
			return nil, err
		}
	case "IncomingCallCancellationRealtimeDispatched":
		base = map[string]string{
			"id": job.ID, "callId": job.CallID, "targetPersonaId": job.TargetPersonaID,
			"cancellationEventId": job.CancellationEventID,
		}
		if err := requiredTime("cancellationRealtimeDispatchedAt", job.CancellationRealtimeDispatchedAt); err != nil {
			return nil, err
		}
	default:
		return nil, fmt.Errorf("incoming call event type %q is not canonical", eventType)
	}
	return base, nil
}

func (s *MongoNotificationDeliveryJobStore) appendIncomingCallProviderResultEvent(
	ctx context.Context,
	job notification.IncomingCallDeliveryJob,
	result notification.ExternalInteractionResultEvent,
	eventType string,
	occurredAt time.Time,
) error {
	action := "ring"
	if job.CancellationExternalInteractionID == result.RequestID {
		action = "cancel"
	}
	eventID := fmt.Sprintf("%s:%020d:%s", job.ID, job.Version, eventType)
	_, err := s.outbox.UpdateOne(
		ctx,
		bson.M{"_id": eventID},
		bson.M{"$setOnInsert": notificationDeliveryJobEventDocument{
			ID:               eventID,
			AggregateID:      job.ID,
			AggregateVersion: job.Version,
			EventType:        eventType,
			Payload: map[string]string{
				"jobId":                 job.ID,
				"callId":                job.CallID,
				"deviceId":              job.DeviceID,
				"deliveryKey":           job.DeliveryKey,
				"action":                action,
				"attemptId":             result.AttemptID,
				"requestId":             result.RequestID,
				"operation":             result.Operation,
				"provider":              result.Provider,
				"providerRequestDigest": result.ProviderRequestDigest,
				"resultStatus":          result.Status,
				"recoveryAction":        result.RecoveryAction,
				"occurredAt":            result.OccurredAt.UTC().Format(time.RFC3339Nano),
				"jobStatus":             job.Status,
			},
			Status:    reliabletask.TaskOutboxStatusPending,
			CreatedAt: occurredAt.UTC(),
		}},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

func (s *MongoNotificationDeliveryJobStore) ReadIncomingCallDeliveryTimeline(
	ctx context.Context,
	callID string,
) (deliverydomain.IncomingCallDeliveryTimeline, error) {
	callID = strings.TrimSpace(callID)
	if callID == "" {
		return deliverydomain.IncomingCallDeliveryTimeline{}, errors.New("callId is required")
	}
	cursor, err := s.jobs.Find(ctx, bson.M{"callId": callID})
	if err != nil {
		return deliverydomain.IncomingCallDeliveryTimeline{}, err
	}
	defer cursor.Close(ctx)
	var jobs []notification.IncomingCallDeliveryJob
	if err := cursor.All(ctx, &jobs); err != nil {
		return deliverydomain.IncomingCallDeliveryTimeline{}, err
	}
	requestIDs := make([]string, 0, len(jobs)*2)
	for _, job := range jobs {
		if job.ExternalInteractionID != "" {
			requestIDs = append(requestIDs, job.ExternalInteractionID)
		}
		if job.CancellationExternalInteractionID != "" {
			requestIDs = append(requestIDs, job.CancellationExternalInteractionID)
		}
	}
	receiptsByRequest := map[string][]externalInteractionResultInboxDocument{}
	if len(requestIDs) > 0 {
		receiptCursor, err := s.resultInbox.Find(
			ctx,
			bson.M{"requestId": bson.M{"$in": requestIDs}},
		)
		if err != nil {
			return deliverydomain.IncomingCallDeliveryTimeline{}, err
		}
		defer receiptCursor.Close(ctx)
		var receipts []externalInteractionResultInboxDocument
		if err := receiptCursor.All(ctx, &receipts); err != nil {
			return deliverydomain.IncomingCallDeliveryTimeline{}, err
		}
		for _, receipt := range receipts {
			receiptsByRequest[receipt.RequestID] = append(
				receiptsByRequest[receipt.RequestID],
				receipt,
			)
		}
	}
	timeline := deliverydomain.IncomingCallDeliveryTimeline{
		CallDigest: incomingCallTimelineDigest(callID),
		Items:      make([]deliverydomain.IncomingCallDeliveryTimelineItem, 0, len(jobs)),
	}
	for _, job := range jobs {
		if job.UpdatedAt.After(timeline.UpdatedAt) {
			timeline.UpdatedAt = job.UpdatedAt.UTC()
		}
		item := deliverydomain.IncomingCallDeliveryTimelineItem{
			JobDigest:                      incomingCallTimelineDigest(job.ID),
			DeviceDigest:                   incomingCallTimelineDigest(job.DeviceID),
			DeliveryKeyDigest:              incomingCallTimelineDigest(job.DeliveryKey),
			Status:                         job.Status,
			ExternalInteractionAcceptedAt:  job.ExternalInteractionAcceptedAt,
			PresentedAt:                    job.PresentedAt,
			CancelledAt:                    job.CancelledAt,
			CancellationExternalAcceptedAt: job.CancellationExternalInteractionAcceptedAt,
			Receipts:                       []deliverydomain.IncomingCallProviderReceipt{},
		}
		for _, actionRequest := range []struct {
			action    string
			requestID string
		}{
			{action: "ring", requestID: job.ExternalInteractionID},
			{action: "cancel", requestID: job.CancellationExternalInteractionID},
		} {
			for _, receipt := range receiptsByRequest[actionRequest.requestID] {
				if receipt.OccurredAt.After(timeline.UpdatedAt) {
					timeline.UpdatedAt = receipt.OccurredAt.UTC()
				}
				item.Receipts = append(item.Receipts, deliverydomain.IncomingCallProviderReceipt{
					AttemptDigest:         incomingCallTimelineDigest(receipt.AttemptID),
					Action:                actionRequest.action,
					Status:                receipt.Status,
					Provider:              receipt.Provider,
					ProviderRequestDigest: receipt.ProviderRequestDigest,
					RecoveryAction:        receipt.RecoveryAction,
					OccurredAt:            receipt.OccurredAt.UTC(),
				})
			}
		}
		sort.Slice(item.Receipts, func(left, right int) bool {
			return item.Receipts[left].OccurredAt.Before(item.Receipts[right].OccurredAt)
		})
		timeline.Items = append(timeline.Items, item)
	}
	sort.Slice(timeline.Items, func(left, right int) bool {
		return timeline.Items[left].DeviceDigest < timeline.Items[right].DeviceDigest
	})
	return timeline, nil
}

func incomingCallTimelineDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func incomingCallEndpointDedupeKey(
	deliveryKey string,
	endpointRef string,
) string {
	sum := sha256.Sum256([]byte(
		strings.TrimSpace(deliveryKey) + "\x00" +
			strings.TrimSpace(endpointRef),
	))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func activeIncomingCallStatuses() []string {
	return []string{
		reliabletask.NotificationStatusPending,
		notification.IncomingCallStatusRealtimeDispatched,
		notification.IncomingCallStatusRealtimePresented,
		notification.IncomingCallStatusPushQueued,
		incomingCallLeasedStatus,
		notification.IncomingCallStatusExternalAccepted,
		notification.IncomingCallStatusSentUnconfirmed,
	}
}
