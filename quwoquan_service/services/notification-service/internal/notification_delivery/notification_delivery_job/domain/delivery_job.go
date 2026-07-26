package domain

import (
	"errors"
	"time"
)

var (
	ErrDeliveryJobNotFound            = errors.New("notification delivery job not found")
	ErrDeliveryJobIdempotencyConflict = errors.New("notification delivery job idempotency conflict")
)

// NotificationDeliveryMetricsSnapshot is the operator-facing reliable-delivery
// projection owned by Notification. It deliberately hides the generic
// reliable-task runtime ABI from the HTTP contract.
type NotificationDeliveryJobMetricsSnapshot struct {
	JobsByStatus map[string]int64 `json:"jobsByStatus"`
	DeadJobs     int64            `json:"deadJobs"`
	UpdatedAt    time.Time        `json:"updatedAt"`
}

type NotificationDeliveryJobDeadLetter struct {
	JobID          string    `json:"jobId"`
	NotificationID string    `json:"notificationId"`
	Channel        string    `json:"channel"`
	EventType      string    `json:"eventType"`
	Attempts       int       `json:"attempts"`
	AttemptEpoch   int       `json:"attemptEpoch"`
	FailureCode    string    `json:"failureCode,omitempty"`
	UpdatedAt      time.Time `json:"updatedAt"`
}

type NotificationDeliveryJobDeadLetterSlice struct {
	Items []NotificationDeliveryJobDeadLetter `json:"items"`
}

type RecoverNotificationDeliveryJobResult struct {
	JobID          string    `bson:"jobId" json:"jobId"`
	NotificationID string    `bson:"notificationId" json:"notificationId"`
	Version        int64     `bson:"version" json:"version"`
	AttemptEpoch   int       `bson:"attemptEpoch" json:"attemptEpoch"`
	RecoveredAt    time.Time `bson:"recoveredAt" json:"recoveredAt"`
	Replayed       bool      `bson:"-" json:"replayed"`
}

type IncomingCallProviderReceipt struct {
	AttemptDigest         string    `json:"attemptDigest"`
	Action                string    `json:"action"`
	Status                string    `json:"status"`
	Provider              string    `json:"provider"`
	ProviderRequestDigest string    `json:"providerRequestDigest"`
	RecoveryAction        string    `json:"recoveryAction"`
	OccurredAt            time.Time `json:"occurredAt"`
}

type IncomingCallDeliveryTimelineItem struct {
	JobDigest                      string                        `json:"jobDigest"`
	DeviceDigest                   string                        `json:"deviceDigest"`
	DeliveryKeyDigest              string                        `json:"deliveryKeyDigest"`
	Status                         string                        `json:"status"`
	ExternalInteractionAcceptedAt  *time.Time                    `json:"externalInteractionAcceptedAt,omitempty"`
	PresentedAt                    *time.Time                    `json:"presentedAt,omitempty"`
	CancelledAt                    *time.Time                    `json:"cancelledAt,omitempty"`
	CancellationExternalAcceptedAt *time.Time                    `json:"cancellationExternalInteractionAcceptedAt,omitempty"`
	Receipts                       []IncomingCallProviderReceipt `json:"receipts"`
}

type IncomingCallDeliveryTimeline struct {
	CallDigest string                             `json:"callDigest"`
	Items      []IncomingCallDeliveryTimelineItem `json:"items"`
	UpdatedAt  time.Time                          `json:"updatedAt"`
}
