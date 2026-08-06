package model

import "time"

const (
	EventCreated       = "SkillSubscriptionCreated"
	EventStatusChanged = "SkillSubscriptionStatusChanged"
	EventTriggered     = "SkillSubscriptionTriggered"
)

// ActivityEvent is the redacted event envelope exposed to SkillActivityView.
// Trigger criteria, destination details, delivery identifiers, and error
// payloads remain private to the SkillSubscription owner.
type ActivityEvent struct {
	EventID        string
	EventType      string
	SubscriptionID string
	OwnerID        string
	SkillID        string
	Status         string
	Version        int64
	FailureCode    string
	OccurredAt     time.Time
}
