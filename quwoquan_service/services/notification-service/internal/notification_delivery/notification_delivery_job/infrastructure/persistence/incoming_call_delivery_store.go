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
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/reliabletask"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification/domain"
	deliverydomain "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/domain"
)

const (
	incomingCallLeasedStatus  = "leased"
	incomingCallPushLeaseTime = 30 * time.Second
)

type externalInteractionResultInboxDocument struct {
	AttemptID             string    `bson:"_id"`
	RequestID             string    `bson:"requestId"`
	Operation             string    `bson:"operation"`
	Status                string    `bson:"status"`
	Provider              string    `bson:"provider"`
	ProviderRequestDigest string    `bson:"providerRequestDigest"`
	NormalizedError       string    `bson:"normalizedError,omitempty"`
	RecoveryAction        string    `bson:"recoveryAction"`
	OccurredAt            time.Time `bson:"occurredAt"`
}

func (s *MongoNotificationDeliveryJobStore) EnsureIncomingCallJob(
	ctx context.Context,
	event notification.IncomingCallRingingEvent,
	destination notification.PushDestinationRef,
	now time.Time,
) (
	notification.IncomingCallDeliveryJob,
	bool,
	error,
) {
	dedupeKey := incomingCallEndpointDedupeKey(
		event.DeliveryKey,
		destination.EndpointRef,
	)
	jobID := "incoming-call-" + strings.TrimPrefix(dedupeKey, "sha256:")[:32]
	job := notification.IncomingCallDeliveryJob{
		ID:              jobID,
		NotificationID:  event.EventID,
		DedupeKey:       dedupeKey,
		EventID:         event.EventID,
		CallID:          event.CallID,
		TargetPersonaID: event.TargetPersonaID,
		DeviceID:        strings.TrimSpace(destination.DeviceID),
		DestinationRef:  strings.TrimSpace(destination.EndpointRef),
		DeliveryKey:     event.DeliveryKey,
		CallType:        event.CallType,
		CallerName:      event.CallerName,
		CallerAvatarURL: event.CallerAvatarURL,
		SourceLabel:     event.SourceLabel,
		TrustRelation:   event.TrustRelation,
		Status:          reliabletask.NotificationStatusPending,
		ExpiresAt:       event.ExpiresAt.UTC(),
		Version:         1,
		CreatedAt:       now.UTC(),
		UpdatedAt:       now.UTC(),
	}
	var (
		created bool
		stored  notification.IncomingCallDeliveryJob
	)
	err := s.RunInTransaction(ctx, func(txCtx context.Context) error {
		result, err := s.jobs.UpdateOne(
			txCtx,
			bson.M{"_id": job.ID},
			bson.M{"$setOnInsert": job},
			options.UpdateOne().SetUpsert(true),
		)
		if err != nil {
			if !mongo.IsDuplicateKeyError(err) {
				return err
			}
			if err := s.jobs.FindOne(
				txCtx,
				bson.M{"dedupeKey": dedupeKey},
			).Decode(&stored); err != nil {
				return err
			}
			return nil
		}
		created = result.UpsertedCount == 1
		if err := s.jobs.FindOne(
			txCtx,
			bson.M{"_id": job.ID},
		).Decode(&stored); err != nil {
			return err
		}
		if created {
			return s.appendIncomingCallEvent(
				txCtx,
				stored,
				"NotificationDeliveryJobCreated",
				now,
			)
		}
		return nil
	})
	return stored, created, err
}

func (s *MongoNotificationDeliveryJobStore) MarkIncomingCallRealtimeDispatched(
	ctx context.Context,
	jobID string,
	expectedVersion int64,
	dispatchedAt time.Time,
	ackDeadlineAt time.Time,
) (
	notification.IncomingCallDeliveryJob,
	bool,
	error,
) {
	var job notification.IncomingCallDeliveryJob
	transitioned := false
	err := s.RunInTransaction(ctx, func(txCtx context.Context) error {
		err := s.jobs.FindOneAndUpdate(
			txCtx,
			bson.M{
				"_id":       strings.TrimSpace(jobID),
				"version":   expectedVersion,
				"status":    reliabletask.NotificationStatusPending,
				"expiresAt": bson.M{"$gt": dispatchedAt.UTC()},
			},
			bson.M{
				"$set": bson.M{
					"status":               notification.IncomingCallStatusRealtimeDispatched,
					"realtimeDispatchedAt": dispatchedAt.UTC(),
					"ackDeadlineAt":        ackDeadlineAt.UTC(),
					"updatedAt":            dispatchedAt.UTC(),
				},
				"$inc": bson.M{"version": 1},
			},
			options.FindOneAndUpdate().SetReturnDocument(options.After),
		).Decode(&job)
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil
		}
		if err != nil {
			return err
		}
		transitioned = true
		return s.appendIncomingCallEvent(
			txCtx,
			job,
			"IncomingCallRealtimeDispatched",
			dispatchedAt,
		)
	})
	return job, transitioned, err
}

func (s *MongoNotificationDeliveryJobStore) QueueIncomingCallPush(
	ctx context.Context,
	jobID string,
	expectedStatuses []string,
	now time.Time,
) (bool, error) {
	var job notification.IncomingCallDeliveryJob
	transitioned := false
	err := s.RunInTransaction(ctx, func(txCtx context.Context) error {
		err := s.jobs.FindOneAndUpdate(
			txCtx,
			bson.M{
				"_id":       strings.TrimSpace(jobID),
				"status":    bson.M{"$in": expectedStatuses},
				"expiresAt": bson.M{"$gt": now.UTC()},
			},
			bson.M{
				"$set": bson.M{
					"status":       notification.IncomingCallStatusPushQueued,
					"pushQueuedAt": now.UTC(),
					"updatedAt":    now.UTC(),
				},
				"$unset": bson.M{"ackDeadlineAt": ""},
				"$inc":   bson.M{"version": 1},
			},
			options.FindOneAndUpdate().SetReturnDocument(options.After),
		).Decode(&job)
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil
		}
		if err != nil {
			return err
		}
		transitioned = true
		return s.appendIncomingCallEvent(
			txCtx,
			job,
			"IncomingCallPushQueued",
			now,
		)
	})
	return transitioned, err
}

func (s *MongoNotificationDeliveryJobStore) QueueExpiredRealtimeDispatches(
	ctx context.Context,
	now time.Time,
) (int64, error) {
	cursor, err := s.jobs.Find(
		ctx,
		bson.M{
			"status":        notification.IncomingCallStatusRealtimeDispatched,
			"ackDeadlineAt": bson.M{"$lte": now.UTC()},
			"expiresAt":     bson.M{"$gt": now.UTC()},
		},
		options.Find().SetProjection(bson.M{"_id": 1}),
	)
	if err != nil {
		return 0, err
	}
	defer cursor.Close(ctx)
	var candidates []struct {
		ID string `bson:"_id"`
	}
	if err := cursor.All(ctx, &candidates); err != nil {
		return 0, err
	}
	var transitioned int64
	for _, candidate := range candidates {
		changed, err := s.QueueIncomingCallPush(
			ctx,
			candidate.ID,
			[]string{notification.IncomingCallStatusRealtimeDispatched},
			now,
		)
		if err != nil {
			return transitioned, err
		}
		if changed {
			transitioned++
		}
	}
	return transitioned, nil
}

func (s *MongoNotificationDeliveryJobStore) ExpireIncomingCallJobs(
	ctx context.Context,
	now time.Time,
) (int64, error) {
	result, err := s.jobs.UpdateMany(
		ctx,
		bson.M{
			"callId":    bson.M{"$exists": true},
			"expiresAt": bson.M{"$lte": now.UTC()},
			"status": bson.M{"$in": []string{
				reliabletask.NotificationStatusPending,
				notification.IncomingCallStatusRealtimeDispatched,
				notification.IncomingCallStatusRealtimePresented,
				notification.IncomingCallStatusPushQueued,
				incomingCallLeasedStatus,
			}},
		},
		bson.M{
			"$set": bson.M{
				"status":    notification.IncomingCallStatusExpired,
				"updatedAt": now.UTC(),
			},
			"$inc": bson.M{"version": 1},
		},
	)
	if err != nil {
		return 0, err
	}
	return result.ModifiedCount, nil
}

func (s *MongoNotificationDeliveryJobStore) ClaimIncomingCallPush(
	ctx context.Context,
	now time.Time,
) (*notification.IncomingCallDeliveryJob, error) {
	var job notification.IncomingCallDeliveryJob
	err := s.jobs.FindOneAndUpdate(
		ctx,
		bson.M{
			"expiresAt": bson.M{"$gt": now.UTC()},
			"$or": bson.A{
				bson.M{
					"status": notification.IncomingCallStatusPushQueued,
				},
				bson.M{
					"status": incomingCallLeasedStatus,
					"updatedAt": bson.M{
						"$lte": now.Add(-incomingCallPushLeaseTime).UTC(),
					},
				},
			},
		},
		bson.M{
			"$set": bson.M{
				"status":    incomingCallLeasedStatus,
				"updatedAt": now.UTC(),
			},
			"$inc": bson.M{"version": 1},
		},
		options.FindOneAndUpdate().
			SetSort(bson.D{{Key: "pushQueuedAt", Value: 1}}).
			SetReturnDocument(options.After),
	).Decode(&job)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &job, nil
}

func (s *MongoNotificationDeliveryJobStore) RequeueIncomingCallPush(
	ctx context.Context,
	jobID string,
	version int64,
	now time.Time,
) error {
	_, err := s.jobs.UpdateOne(
		ctx,
		bson.M{
			"_id":     strings.TrimSpace(jobID),
			"version": version,
			"status":  incomingCallLeasedStatus,
		},
		bson.M{
			"$set": bson.M{
				"status":    notification.IncomingCallStatusPushQueued,
				"updatedAt": now.UTC(),
			},
			"$inc": bson.M{"version": 1},
		},
	)
	return err
}

func (s *MongoNotificationDeliveryJobStore) MarkIncomingCallExternalAccepted(
	ctx context.Context,
	jobID string,
	version int64,
	externalInteractionID string,
	now time.Time,
) error {
	return s.RunInTransaction(ctx, func(txCtx context.Context) error {
		var job notification.IncomingCallDeliveryJob
		err := s.jobs.FindOneAndUpdate(
			txCtx,
			bson.M{
				"_id":     strings.TrimSpace(jobID),
				"version": version,
				"status":  incomingCallLeasedStatus,
			},
			bson.M{
				"$set": bson.M{
					"status":                        notification.IncomingCallStatusExternalAccepted,
					"externalInteractionId":         strings.TrimSpace(externalInteractionID),
					"externalInteractionAcceptedAt": now.UTC(),
					"updatedAt":                     now.UTC(),
				},
				"$inc": bson.M{"version": 1},
			},
			options.FindOneAndUpdate().SetReturnDocument(options.After),
		).Decode(&job)
		if errors.Is(err, mongo.ErrNoDocuments) {
			return fmt.Errorf("incoming call push lease lost")
		}
		if err != nil {
			return err
		}
		return s.appendIncomingCallEvent(
			txCtx,
			job,
			"IncomingCallExternalInteractionAccepted",
			now,
		)
	})
}

func (s *MongoNotificationDeliveryJobStore) ApplyExternalInteractionResult(
	ctx context.Context,
	event notification.ExternalInteractionResultEvent,
	now time.Time,
) error {
	event.AttemptID = strings.TrimSpace(event.AttemptID)
	event.RequestID = strings.TrimSpace(event.RequestID)
	event.Operation = strings.TrimSpace(event.Operation)
	event.Status = strings.TrimSpace(event.Status)
	event.Provider = strings.TrimSpace(event.Provider)
	event.ProviderRequestDigest = strings.TrimSpace(event.ProviderRequestDigest)
	event.RecoveryAction = strings.TrimSpace(event.RecoveryAction)
	if event.AttemptID == "" || event.RequestID == "" ||
		event.Operation != reliabletask.ExternalInteractionOperationPush ||
		event.Status == "" || event.Provider == "" ||
		event.ProviderRequestDigest == "" || event.RecoveryAction == "" ||
		event.OccurredAt.IsZero() {
		return errors.New("external interaction result event is incomplete")
	}
	return s.RunInTransaction(ctx, func(txCtx context.Context) error {
		var existing externalInteractionResultInboxDocument
		existingErr := s.resultInbox.FindOne(
			txCtx,
			bson.M{"_id": event.AttemptID},
		).Decode(&existing)
		if existingErr == nil {
			if existing.RequestID != event.RequestID ||
				existing.Operation != event.Operation ||
				existing.Status != event.Status ||
				existing.Provider != event.Provider ||
				existing.ProviderRequestDigest != event.ProviderRequestDigest ||
				existing.NormalizedError != event.NormalizedError ||
				existing.RecoveryAction != event.RecoveryAction ||
				!existing.OccurredAt.Equal(event.OccurredAt.UTC()) {
				return errors.New("external interaction result attemptId conflicts with immutable receipt")
			}
			return nil
		}
		if !errors.Is(existingErr, mongo.ErrNoDocuments) {
			return existingErr
		}

		var current notification.IncomingCallDeliveryJob
		if err := s.jobs.FindOne(
			txCtx,
			bson.M{"$or": bson.A{
				bson.M{"externalInteractionId": event.RequestID},
				bson.M{"cancellationExternalInteractionId": event.RequestID},
			}},
		).Decode(&current); err != nil {
			if errors.Is(err, mongo.ErrNoDocuments) {
				return deliverydomain.ErrDeliveryJobNotFound
			}
			return err
		}
		if _, err := s.resultInbox.InsertOne(txCtx, bson.M{
			"_id":                   event.AttemptID,
			"requestId":             event.RequestID,
			"operation":             event.Operation,
			"status":                event.Status,
			"provider":              event.Provider,
			"providerRequestDigest": event.ProviderRequestDigest,
			"normalizedError":       event.NormalizedError,
			"recoveryAction":        event.RecoveryAction,
			"occurredAt":            event.OccurredAt.UTC(),
			"createdAt":             now.UTC(),
		}); err != nil {
			return err
		}

		set := bson.M{"updatedAt": now.UTC()}
		eventType := "IncomingCallProviderResultRecorded"
		if current.ExternalInteractionID == event.RequestID {
			set["provider"] = event.Provider
			set["providerRequestDigest"] = event.ProviderRequestDigest
			set["providerResultStatus"] = event.Status
			set["providerResultAt"] = event.OccurredAt.UTC()
			if event.Status == reliabletask.ExternalInteractionStatusSentUnconfirmed &&
				current.Status == notification.IncomingCallStatusExternalAccepted {
				set["status"] = notification.IncomingCallStatusSentUnconfirmed
				set["sentUnconfirmedAt"] = event.OccurredAt.UTC()
				eventType = "IncomingCallSentUnconfirmed"
			} else if event.Status == reliabletask.ExternalInteractionStatusFailed &&
				event.RecoveryAction != "retry" &&
				current.Status == notification.IncomingCallStatusExternalAccepted {
				set["status"] = reliabletask.NotificationStatusDead
			}
		} else {
			set["cancellationProvider"] = event.Provider
			set["cancellationProviderRequestDigest"] = event.ProviderRequestDigest
			set["cancellationProviderResultStatus"] = event.Status
			set["cancellationProviderResultAt"] = event.OccurredAt.UTC()
			eventType = "IncomingCallCancellationProviderResultRecorded"
		}
		var updated notification.IncomingCallDeliveryJob
		if err := s.jobs.FindOneAndUpdate(
			txCtx,
			bson.M{"_id": current.ID, "version": current.Version},
			bson.M{"$set": set, "$inc": bson.M{"version": 1}},
			options.FindOneAndUpdate().SetReturnDocument(options.After),
		).Decode(&updated); err != nil {
			return err
		}
		return s.appendIncomingCallEvent(txCtx, updated, eventType, now)
	})
}

func (s *MongoNotificationDeliveryJobStore) AckIncomingCallPresentation(
	ctx context.Context,
	personaID string,
	deviceID string,
	deliveryKey string,
	now time.Time,
) (notification.AckIncomingCallPresentationResult, error) {
	var result notification.AckIncomingCallPresentationResult
	err := s.RunInTransaction(ctx, func(txCtx context.Context) error {
		var current notification.IncomingCallDeliveryJob
		if err := s.jobs.FindOne(
			txCtx,
			bson.M{
				"deliveryKey":     strings.TrimSpace(deliveryKey),
				"targetPersonaId": strings.TrimSpace(personaID),
				"deviceId":        strings.TrimSpace(deviceID),
			},
		).Decode(&current); err != nil {
			if errors.Is(err, mongo.ErrNoDocuments) {
				return deliverydomain.ErrDeliveryJobNotFound
			}
			return err
		}
		result = notification.AckIncomingCallPresentationResult{
			DeliveryKey:    current.DeliveryKey,
			DeviceID:       current.DeviceID,
			Status:         current.Status,
			AcknowledgedAt: now.UTC(),
		}
		if current.Status ==
			notification.IncomingCallStatusRealtimePresented {
			return nil
		}
		if current.Status ==
			notification.IncomingCallStatusRealtimeDispatched &&
			current.AckDeadlineAt != nil &&
			!now.After(current.AckDeadlineAt.UTC()) &&
			now.Before(current.ExpiresAt) {
			var presented notification.IncomingCallDeliveryJob
			err := s.jobs.FindOneAndUpdate(
				txCtx,
				bson.M{
					"_id":     current.ID,
					"version": current.Version,
					"status":  notification.IncomingCallStatusRealtimeDispatched,
				},
				bson.M{
					"$set": bson.M{
						"status":      notification.IncomingCallStatusRealtimePresented,
						"presentedAt": now.UTC(),
						"updatedAt":   now.UTC(),
					},
					"$inc": bson.M{"version": 1},
				},
				options.FindOneAndUpdate().
					SetReturnDocument(options.After),
			).Decode(&presented)
			if err != nil {
				return err
			}
			result.Status = presented.Status
			return s.appendIncomingCallEvent(
				txCtx,
				presented,
				"IncomingCallRealtimePresented",
				now,
			)
		}
		result.Raced = true
		_, err := s.jobs.UpdateOne(
			txCtx,
			bson.M{"_id": current.ID, "version": current.Version},
			bson.M{
				"$set": bson.M{
					"lastAckRaceAt": now.UTC(),
					"updatedAt":     now.UTC(),
				},
				"$inc": bson.M{
					"ackRaceCount": 1,
					"version":      1,
				},
			},
		)
		return err
	})
	return result, err
}

func (s *MongoNotificationDeliveryJobStore) CancelIncomingCallJobs(
	ctx context.Context,
	event notification.IncomingCallCancellationEvent,
	now time.Time,
) ([]notification.IncomingCallCancellationWork, error) {
	var works []notification.IncomingCallCancellationWork
	err := s.RunInTransaction(ctx, func(txCtx context.Context) error {
		cursor, err := s.jobs.Find(
			txCtx,
			bson.M{"callId": strings.TrimSpace(event.CallID)},
		)
		if err != nil {
			return err
		}
		defer cursor.Close(txCtx)
		var jobs []notification.IncomingCallDeliveryJob
		if err := cursor.All(txCtx, &jobs); err != nil {
			return err
		}
		for _, current := range jobs {
			pushRequired := incomingCallCancellationPushRequired(
				current.Status,
				current.ExpiresAt,
				now,
			)
			var cancelled notification.IncomingCallDeliveryJob
			err := s.jobs.FindOneAndUpdate(
				txCtx,
				bson.M{
					"_id":     current.ID,
					"version": current.Version,
					"status":  bson.M{"$in": activeIncomingCallStatuses()},
				},
				bson.M{
					"$set": bson.M{
						"status":                   notification.IncomingCallStatusCancelled,
						"cancelledAt":              now.UTC(),
						"cancellationEventId":      strings.TrimSpace(event.EventID),
						"cancellationEventType":    strings.TrimSpace(event.EventType),
						"cancellationActorId":      strings.TrimSpace(event.ActorID),
						"cancellationOccurredAt":   event.OccurredAt.UTC(),
						"cancellationPushRequired": pushRequired,
						"updatedAt":                now.UTC(),
					},
					"$unset": bson.M{"ackDeadlineAt": ""},
					"$inc":   bson.M{"version": 1},
				},
				options.FindOneAndUpdate().
					SetReturnDocument(options.After),
			).Decode(&cancelled)
			if errors.Is(err, mongo.ErrNoDocuments) {
				continue
			}
			if err != nil {
				return err
			}
			if err := s.appendIncomingCallEvent(
				txCtx,
				cancelled,
				"IncomingCallDeliveryCancelled",
				now,
			); err != nil {
				return err
			}
		}
		cancelledCursor, err := s.jobs.Find(
			txCtx,
			bson.M{
				"callId":              strings.TrimSpace(event.CallID),
				"status":              notification.IncomingCallStatusCancelled,
				"cancellationEventId": strings.TrimSpace(event.EventID),
			},
		)
		if err != nil {
			return err
		}
		defer cancelledCursor.Close(txCtx)
		var cancelledJobs []notification.IncomingCallDeliveryJob
		if err := cancelledCursor.All(txCtx, &cancelledJobs); err != nil {
			return err
		}
		for _, job := range cancelledJobs {
			realtimeRequired := job.CancellationRealtimeDispatchedAt == nil
			pushRequired := job.CancellationPushRequired &&
				job.CancellationPushSubmittedAt == nil &&
				job.ExpiresAt.After(now.UTC())
			if !realtimeRequired && !pushRequired {
				continue
			}
			works = append(works, notification.IncomingCallCancellationWork{
				Job:                      job,
				RealtimeDispatchRequired: realtimeRequired,
				PushDispatchRequired:     pushRequired,
			})
		}
		return nil
	})
	return works, err
}

func (s *MongoNotificationDeliveryJobStore) MarkIncomingCallCancellationExternalAccepted(
	ctx context.Context,
	jobID string,
	version int64,
	externalInteractionID string,
	now time.Time,
) error {
	return s.RunInTransaction(ctx, func(txCtx context.Context) error {
		var job notification.IncomingCallDeliveryJob
		err := s.jobs.FindOneAndUpdate(
			txCtx,
			bson.M{
				"_id":                         strings.TrimSpace(jobID),
				"version":                     version,
				"status":                      notification.IncomingCallStatusCancelled,
				"cancellationPushRequired":    true,
				"cancellationPushSubmittedAt": bson.M{"$exists": false},
			},
			bson.M{
				"$set": bson.M{
					"cancellationExternalInteractionId":         strings.TrimSpace(externalInteractionID),
					"cancellationExternalInteractionAcceptedAt": now.UTC(),
					"cancellationPushSubmittedAt":               now.UTC(),
					"updatedAt":                                 now.UTC(),
				},
				"$inc": bson.M{"version": 1},
			},
			options.FindOneAndUpdate().SetReturnDocument(options.After),
		).Decode(&job)
		if errors.Is(err, mongo.ErrNoDocuments) {
			var current notification.IncomingCallDeliveryJob
			if loadErr := s.jobs.FindOne(
				txCtx,
				bson.M{"_id": strings.TrimSpace(jobID)},
			).Decode(&current); loadErr == nil &&
				current.CancellationPushSubmittedAt != nil {
				return nil
			}
			return errors.New("incoming call cancellation push state changed")
		}
		if err != nil {
			return err
		}
		return s.appendIncomingCallEvent(
			txCtx,
			job,
			"IncomingCallCancellationExternalInteractionAccepted",
			now,
		)
	})
}

func (s *MongoNotificationDeliveryJobStore) MarkIncomingCallCancellationRealtimeDispatched(
	ctx context.Context,
	callID string,
	personaID string,
	eventID string,
	now time.Time,
) error {
	return s.RunInTransaction(ctx, func(txCtx context.Context) error {
		cursor, err := s.jobs.Find(
			txCtx,
			bson.M{
				"callId":                           strings.TrimSpace(callID),
				"targetPersonaId":                  strings.TrimSpace(personaID),
				"status":                           notification.IncomingCallStatusCancelled,
				"cancellationEventId":              strings.TrimSpace(eventID),
				"cancellationRealtimeDispatchedAt": bson.M{"$exists": false},
			},
		)
		if err != nil {
			return err
		}
		defer cursor.Close(txCtx)
		var jobs []notification.IncomingCallDeliveryJob
		if err := cursor.All(txCtx, &jobs); err != nil {
			return err
		}
		for _, current := range jobs {
			var updated notification.IncomingCallDeliveryJob
			err := s.jobs.FindOneAndUpdate(
				txCtx,
				bson.M{
					"_id":                              current.ID,
					"version":                          current.Version,
					"status":                           notification.IncomingCallStatusCancelled,
					"cancellationRealtimeDispatchedAt": bson.M{"$exists": false},
				},
				bson.M{
					"$set": bson.M{
						"cancellationRealtimeDispatchedAt": now.UTC(),
						"updatedAt":                        now.UTC(),
					},
					"$inc": bson.M{"version": 1},
				},
				options.FindOneAndUpdate().SetReturnDocument(options.After),
			).Decode(&updated)
			if errors.Is(err, mongo.ErrNoDocuments) {
				continue
			}
			if err != nil {
				return err
			}
			if err := s.appendIncomingCallEvent(
				txCtx,
				updated,
				"IncomingCallCancellationRealtimeDispatched",
				now,
			); err != nil {
				return err
			}
		}
		return nil
	})
}

func incomingCallCancellationPushRequired(
	status string,
	expiresAt time.Time,
	now time.Time,
) bool {
	if !expiresAt.After(now.UTC()) {
		return false
	}
	switch status {
	case notification.IncomingCallStatusRealtimeDispatched,
		notification.IncomingCallStatusRealtimePresented,
		incomingCallLeasedStatus,
		notification.IncomingCallStatusExternalAccepted,
		notification.IncomingCallStatusSentUnconfirmed:
		return true
	default:
		return false
	}
}

func (s *MongoNotificationDeliveryJobStore) appendIncomingCallEvent(
	ctx context.Context,
	job notification.IncomingCallDeliveryJob,
	eventType string,
	occurredAt time.Time,
) error {
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
				"jobId":          job.ID,
				"notificationId": job.NotificationID,
				"callId":         job.CallID,
				"deviceId":       job.DeviceID,
				"deliveryKey":    job.DeliveryKey,
				"status":         job.Status,
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
