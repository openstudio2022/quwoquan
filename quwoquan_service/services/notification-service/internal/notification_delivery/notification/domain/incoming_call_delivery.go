package notification

import "time"

const (
	IncomingCallStatusRealtimeDispatched = "realtime_dispatched"
	IncomingCallStatusRealtimePresented  = "realtime_presented"
	IncomingCallStatusPushQueued         = "push_queued"
	IncomingCallStatusExternalAccepted   = "external_accepted"
	IncomingCallStatusSentUnconfirmed    = "sent_unconfirmed"
	IncomingCallStatusCancelled          = "cancelled"
	IncomingCallStatusExpired            = "expired"
)

type IncomingCallDeliveryJob struct {
	ID                                        string     `bson:"_id" json:"id"`
	NotificationID                            string     `bson:"notificationId" json:"notificationId"`
	DedupeKey                                 string     `bson:"dedupeKey" json:"dedupeKey"`
	EventID                                   string     `bson:"eventId" json:"eventId"`
	CallID                                    string     `bson:"callId" json:"callId"`
	TargetPersonaID                           string     `bson:"targetPersonaId" json:"targetPersonaId"`
	DeviceID                                  string     `bson:"deviceId" json:"deviceId"`
	DestinationRef                            string     `bson:"destinationRef" json:"-"`
	DeliveryKey                               string     `bson:"deliveryKey" json:"deliveryKey"`
	CallType                                  string     `bson:"callType" json:"callType"`
	CallerName                                string     `bson:"callerName" json:"callerName"`
	CallerAvatarURL                           string     `bson:"callerAvatarUrl" json:"callerAvatarUrl"`
	SourceLabel                               string     `bson:"sourceLabel" json:"sourceLabel"`
	TrustRelation                             string     `bson:"trustRelation" json:"trustRelation"`
	Status                                    string     `bson:"status" json:"status"`
	ExpiresAt                                 time.Time  `bson:"expiresAt" json:"expiresAt"`
	AckDeadlineAt                             *time.Time `bson:"ackDeadlineAt,omitempty" json:"ackDeadlineAt,omitempty"`
	RealtimeDispatchedAt                      *time.Time `bson:"realtimeDispatchedAt,omitempty" json:"realtimeDispatchedAt,omitempty"`
	PresentedAt                               *time.Time `bson:"presentedAt,omitempty" json:"presentedAt,omitempty"`
	PushQueuedAt                              *time.Time `bson:"pushQueuedAt,omitempty" json:"pushQueuedAt,omitempty"`
	SentUnconfirmedAt                         *time.Time `bson:"sentUnconfirmedAt,omitempty" json:"sentUnconfirmedAt,omitempty"`
	CancelledAt                               *time.Time `bson:"cancelledAt,omitempty" json:"cancelledAt,omitempty"`
	ExternalInteractionID                     string     `bson:"externalInteractionId,omitempty" json:"externalInteractionId,omitempty"`
	ExternalInteractionAcceptedAt             *time.Time `bson:"externalInteractionAcceptedAt,omitempty" json:"externalInteractionAcceptedAt,omitempty"`
	CancellationEventID                       string     `bson:"cancellationEventId,omitempty" json:"cancellationEventId,omitempty"`
	CancellationEventType                     string     `bson:"cancellationEventType,omitempty" json:"cancellationEventType,omitempty"`
	CancellationActorID                       string     `bson:"cancellationActorId,omitempty" json:"-"`
	CancellationOccurredAt                    *time.Time `bson:"cancellationOccurredAt,omitempty" json:"cancellationOccurredAt,omitempty"`
	CancellationRealtimeDispatchedAt          *time.Time `bson:"cancellationRealtimeDispatchedAt,omitempty" json:"cancellationRealtimeDispatchedAt,omitempty"`
	CancellationPushRequired                  bool       `bson:"cancellationPushRequired" json:"cancellationPushRequired"`
	CancellationExternalInteractionID         string     `bson:"cancellationExternalInteractionId,omitempty" json:"cancellationExternalInteractionId,omitempty"`
	CancellationExternalInteractionAcceptedAt *time.Time `bson:"cancellationExternalInteractionAcceptedAt,omitempty" json:"cancellationExternalInteractionAcceptedAt,omitempty"`
	CancellationPushSubmittedAt               *time.Time `bson:"cancellationPushSubmittedAt,omitempty" json:"cancellationPushSubmittedAt,omitempty"`
	AckRaceCount                              int        `bson:"ackRaceCount" json:"ackRaceCount"`
	LastAckRaceAt                             *time.Time `bson:"lastAckRaceAt,omitempty" json:"lastAckRaceAt,omitempty"`
	Version                                   int64      `bson:"version" json:"version"`
	CreatedAt                                 time.Time  `bson:"createdAt" json:"createdAt"`
	UpdatedAt                                 time.Time  `bson:"updatedAt" json:"updatedAt"`
	AccountRestricted                         bool       `bson:"accountRestricted,omitempty" json:"-"`
	RestrictionSuppressed                     bool       `bson:"restrictionSuppressed,omitempty" json:"-"`
}

type ExternalInteractionResultEvent struct {
	AttemptID             string
	RequestID             string
	Operation             string
	Status                string
	Provider              string
	ProviderRequestDigest string
	NormalizedError       string
	RecoveryAction        string
	OccurredAt            time.Time
}

type IncomingCallRingingEvent struct {
	EventID         string    `json:"eventId"`
	CallID          string    `json:"callId"`
	TargetPersonaID string    `json:"targetPersonaId"`
	CallType        string    `json:"callType"`
	CallerName      string    `json:"callerName"`
	CallerAvatarURL string    `json:"callerAvatarUrl"`
	SourceLabel     string    `json:"sourceLabel"`
	TrustRelation   string    `json:"trustRelation"`
	ExpiresAt       time.Time `json:"expiresAt"`
	DeliveryKey     string    `json:"deliveryKey"`
}

type IncomingCallCancellationEvent struct {
	EventID    string
	EventType  string
	CallID     string
	ActorID    string
	OccurredAt time.Time
}

type IncomingCallCancellationWork struct {
	Job                      IncomingCallDeliveryJob
	RealtimeDispatchRequired bool
	PushDispatchRequired     bool
}

type PushDestinationRef struct {
	DeviceID    string `json:"deviceId"`
	EndpointRef string `json:"endpointRef"`
}

type AckIncomingCallPresentationResult struct {
	DeliveryKey    string    `json:"deliveryKey"`
	DeviceID       string    `json:"deviceId"`
	Status         string    `json:"status"`
	Raced          bool      `json:"raced"`
	AcknowledgedAt time.Time `json:"acknowledgedAt"`
}
