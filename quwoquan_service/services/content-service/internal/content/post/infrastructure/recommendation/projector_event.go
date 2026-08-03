package recommendation

import (
	"time"
)

// ProjectorEvent is the typed Post outbox envelope accepted by the remaining
// Content-owned enrichment projector. Candidate and feature projections consume
// the public lifecycle stream in recommendation-service instead.
type ProjectorEvent struct {
	Type          string
	AggregateType string
	AggregateID   string
	Payload       map[string]any
	OccurredAt    time.Time
}
