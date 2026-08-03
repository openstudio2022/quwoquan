package domain

import (
	"errors"
	"strings"
	"time"
)

var ErrInvalid = errors.New("invalid SearchRequestFact")

// QueryLog is an immutable SearchRequestFact.
type QueryLog struct {
	SearchRequestID  string
	Query            string
	SessionID        string
	Mode             string
	ViewerID         string
	ObjectTypes      []string
	ResultCount      int
	ExperimentBucket string
	RelatedTerms     []string
	CreatedAt        time.Time
}

func (fact QueryLog) Validate() error {
	if strings.TrimSpace(fact.SearchRequestID) == "" || strings.TrimSpace(fact.Query) == "" {
		return ErrInvalid
	}
	if fact.ResultCount < 0 || fact.CreatedAt.IsZero() {
		return ErrInvalid
	}
	return nil
}
