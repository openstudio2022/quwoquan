package domainreader

import (
	"context"
	"time"
)

// ObjectTarget is the minimum trusted identity passed from AssistantRun page
// context to an owning domain query. Display text and user-authored URLs are
// deliberately excluded.
type ObjectTarget struct {
	ObjectTypeRef string
	ObjectID      string
}

// ObjectContext is a bounded, point-in-time projection returned by an owning
// service. AssistantRun may cite it, but never persists it as a second domain
// aggregate.
type ObjectContext struct {
	Target       ObjectTarget
	OperationRef string
	CapturedAt   time.Time
	SourceDigest string
	TokenCost    int
	Value        map[string]any
	Summary      string
}

type ObjectContextReader interface {
	ReadObjectContext(context.Context, ObjectTarget) (ObjectContext, error)
}
