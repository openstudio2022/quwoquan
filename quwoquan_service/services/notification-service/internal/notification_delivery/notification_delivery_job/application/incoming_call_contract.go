package application

import deliveryjob "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/domain"

// Incoming-call delivery is owned by NotificationDeliveryJob. These aliases
// are the object's public application-port vocabulary for sibling composition
// adapters; callers must not import the object's private domain package.
type IncomingCallDeliveryJob = deliveryjob.IncomingCallDeliveryJob
type ExternalInteractionResultEvent = deliveryjob.ExternalInteractionResultEvent
type IncomingCallRingingEvent = deliveryjob.IncomingCallRingingEvent
type IncomingCallCancellationEvent = deliveryjob.IncomingCallCancellationEvent
type IncomingCallCancellationWork = deliveryjob.IncomingCallCancellationWork
type PushDestinationRef = deliveryjob.PushDestinationRef
type AckIncomingCallPresentationResult = deliveryjob.AckIncomingCallPresentationResult

const (
	IncomingCallStatusRealtimeDispatched = deliveryjob.IncomingCallStatusRealtimeDispatched
	IncomingCallStatusRealtimePresented  = deliveryjob.IncomingCallStatusRealtimePresented
	IncomingCallStatusPushQueued         = deliveryjob.IncomingCallStatusPushQueued
	IncomingCallStatusExternalAccepted   = deliveryjob.IncomingCallStatusExternalAccepted
	IncomingCallStatusSentUnconfirmed    = deliveryjob.IncomingCallStatusSentUnconfirmed
	IncomingCallStatusCancelled          = deliveryjob.IncomingCallStatusCancelled
	IncomingCallStatusExpired            = deliveryjob.IncomingCallStatusExpired
)
