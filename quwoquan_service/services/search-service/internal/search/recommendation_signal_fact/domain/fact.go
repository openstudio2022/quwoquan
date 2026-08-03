package domain

import (
	"fmt"
	"strings"
	"time"
)

// Fact is the immutable recommendation signal emitted from persisted Search facts.
type Fact struct {
	SignalID         string
	SignalType       string
	SearchRequestID  string
	SessionID        string
	UserID           string
	NormalizedQuery  string
	RelatedTerms     []string
	EngagedObjectIDs []string
	ExperimentBucket string
	ResultCount      int
	CreatedAt        time.Time
}

func (fact Fact) Validate() error {
	if strings.TrimSpace(fact.SignalID) == "" || strings.TrimSpace(fact.SearchRequestID) == "" {
		return fmt.Errorf("signalId and searchRequestId are required")
	}
	if fact.CreatedAt.IsZero() || fact.ResultCount < 0 {
		return fmt.Errorf("recommendation signal time/count is invalid")
	}
	switch strings.TrimSpace(fact.SignalType) {
	case "query":
		if strings.TrimSpace(fact.NormalizedQuery) == "" || len(fact.EngagedObjectIDs) != 0 {
			return fmt.Errorf("query signal requires normalizedQuery and no engaged objects")
		}
	case "click":
		if len(fact.EngagedObjectIDs) == 0 || strings.TrimSpace(fact.NormalizedQuery) != "" {
			return fmt.Errorf("click signal requires engaged objects and no query")
		}
	default:
		return fmt.Errorf("unsupported signalType %q", fact.SignalType)
	}
	return nil
}
