package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	deliverydomain "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/domain"
)

type closedAccountDeliveryJobEventDocument struct {
	ID               string            `bson:"_id"`
	AggregateID      string            `bson:"aggregateId"`
	AggregateVersion int64             `bson:"aggregateVersion"`
	EventType        string            `bson:"eventType"`
	Payload          map[string]string `bson:"payload"`
	Status           string            `bson:"status"`
}

type closedAccountDeliveryJobReceiptDocument struct {
	ID            string                                              `bson:"_id"`
	CommandDigest string                                              `bson:"commandDigest"`
	Result        deliverydomain.RecoverNotificationDeliveryJobResult `bson:"result"`
}

// anonymizeDeliveryAudit 保留投递审计的状态、时延与时间信息，但不可逆替换
// 已注销账号关联的任务、通知、设备和供应商请求标识。
func (projection *MongoUserAccountClosedProjection) anonymizeDeliveryAudit(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	jobIDs []string,
	messageIDs []string,
) (int64, error) {
	sensitiveValues := make(map[string]struct{}, len(jobIDs)+len(messageIDs)+len(event.SubjectIDs()))
	for _, values := range [][]string{jobIDs, messageIDs, event.SubjectIDs()} {
		for _, value := range values {
			if normalized := strings.TrimSpace(value); normalized != "" {
				sensitiveValues[normalized] = struct{}{}
			}
		}
	}

	var anonymized int64
	outboxClauses := bson.A{}
	if len(jobIDs) > 0 {
		outboxClauses = append(
			outboxClauses,
			bson.M{"aggregateId": bson.M{"$in": jobIDs}},
			bson.M{"payload.jobId": bson.M{"$in": jobIDs}},
		)
	}
	if len(messageIDs) > 0 {
		outboxClauses = append(
			outboxClauses,
			bson.M{"payload.notificationId": bson.M{"$in": messageIDs}},
		)
	}
	if len(outboxClauses) > 0 {
		cursor, err := projection.deliveryOutbox.Find(
			ctx,
			bson.M{"$or": outboxClauses},
		)
		if err != nil {
			return 0, fmt.Errorf(
				"scan closed-account notification delivery outbox: %w",
				err,
			)
		}
		var documents []closedAccountDeliveryJobEventDocument
		if err := cursor.All(ctx, &documents); err != nil {
			cursor.Close(ctx)
			return 0, fmt.Errorf(
				"decode closed-account notification delivery outbox: %w",
				err,
			)
		}
		cursor.Close(ctx)
		for _, document := range documents {
			document.AggregateID = closedNotificationAuditValue(
				event.EventID,
				document.AggregateID,
			)
			for key, value := range document.Payload {
				normalized := strings.TrimSpace(value)
				if normalized == "" {
					continue
				}
				_, directlyReferencesClosedSubject := sensitiveValues[normalized]
				if directlyReferencesClosedSubject ||
					isNotificationAuditIdentityField(key) {
					document.Payload[key] = closedNotificationAuditValue(
						event.EventID,
						normalized,
					)
				}
			}
			if _, err := projection.deliveryOutbox.ReplaceOne(
				ctx,
				bson.M{"_id": document.ID},
				document,
			); err != nil {
				return 0, fmt.Errorf(
					"anonymize closed-account notification delivery outbox: %w",
					err,
				)
			}
			anonymized++
		}
	}

	receiptClauses := bson.A{}
	if len(jobIDs) > 0 {
		receiptClauses = append(
			receiptClauses,
			bson.M{"result.jobId": bson.M{"$in": jobIDs}},
		)
	}
	if len(messageIDs) > 0 {
		receiptClauses = append(
			receiptClauses,
			bson.M{"result.notificationId": bson.M{"$in": messageIDs}},
		)
	}
	if len(receiptClauses) > 0 {
		cursor, err := projection.commandReceipts.Find(
			ctx,
			bson.M{"$or": receiptClauses},
		)
		if err != nil {
			return 0, fmt.Errorf(
				"scan closed-account notification command receipts: %w",
				err,
			)
		}
		var documents []closedAccountDeliveryJobReceiptDocument
		if err := cursor.All(ctx, &documents); err != nil {
			cursor.Close(ctx)
			return 0, fmt.Errorf(
				"decode closed-account notification command receipts: %w",
				err,
			)
		}
		cursor.Close(ctx)
		for _, document := range documents {
			document.CommandDigest = closedNotificationAuditValue(
				event.EventID,
				document.CommandDigest,
			)
			document.Result.JobID = closedNotificationAuditValue(
				event.EventID,
				document.Result.JobID,
			)
			document.Result.NotificationID = closedNotificationAuditValue(
				event.EventID,
				document.Result.NotificationID,
			)
			if _, err := projection.commandReceipts.ReplaceOne(
				ctx,
				bson.M{"_id": document.ID},
				document,
			); err != nil {
				return 0, fmt.Errorf(
					"anonymize closed-account notification command receipt: %w",
					err,
				)
			}
			anonymized++
		}
	}

	return anonymized, nil
}

func isNotificationAuditIdentityField(field string) bool {
	switch strings.ToLower(strings.TrimSpace(field)) {
	case "accountid",
		"aggregateid",
		"callid",
		"dedupekey",
		"deliverykey",
		"destinationref",
		"deviceid",
		"endpointref",
		"jobid",
		"notificationid",
		"personaid",
		"recipientid",
		"requestid",
		"targetpersonaid",
		"userid":
		return true
	default:
		return false
	}
}

func closedNotificationAuditValue(eventID string, value string) string {
	normalized := strings.TrimSpace(value)
	if normalized == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(
		"notification-user-account-closed-audit\n" +
			strings.TrimSpace(eventID) + "\n" + normalized,
	))
	return "closed:sha256:" + hex.EncodeToString(sum[:])
}
