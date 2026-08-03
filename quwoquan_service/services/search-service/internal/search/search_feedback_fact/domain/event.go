package domain

import (
	"errors"
	"fmt"
	"strings"
)

var ErrInvalid = errors.New("invalid search feedback")

// Event is the immutable SearchFeedbackFact after actor derivation.
type Event struct {
	SearchRequestID string `json:"searchRequestId"`
	ViewerID        string `json:"-"`
	EventType       string `json:"eventType"`
	ObjectID        string `json:"objectId,omitempty"`
	Target          string `json:"target,omitempty"`
	RankPosition    int    `json:"rankPosition,omitempty"`
	ReferralSource  string `json:"referralSource,omitempty"`
	FeedRequestID   string `json:"feedRequestId,omitempty"`
	DwellMs         int    `json:"dwellMs,omitempty"`
}

func (event Event) Normalize() Event {
	event.SearchRequestID = strings.TrimSpace(event.SearchRequestID)
	event.ViewerID = strings.TrimSpace(event.ViewerID)
	event.EventType = strings.TrimSpace(event.EventType)
	event.ObjectID = strings.TrimSpace(event.ObjectID)
	event.Target = strings.TrimSpace(event.Target)
	event.ReferralSource = strings.TrimSpace(event.ReferralSource)
	event.FeedRequestID = strings.TrimSpace(event.FeedRequestID)
	return event
}

func (event Event) Validate() error {
	event = event.Normalize()
	if event.SearchRequestID == "" || len(event.SearchRequestID) > 128 {
		return fmt.Errorf("%w: searchRequestId is required and must be at most 128 characters", ErrInvalid)
	}
	switch event.EventType {
	case "impression", "click", "dwell", "refine", "zero_result", "degrade":
	default:
		return fmt.Errorf("%w: unsupported eventType", ErrInvalid)
	}
	if event.EventType == "click" &&
		(event.ObjectID == "" || event.Target == "" || event.RankPosition <= 0) {
		return fmt.Errorf("%w: click requires objectId, target and positive rankPosition", ErrInvalid)
	}
	if event.RankPosition < 0 {
		return fmt.Errorf("%w: rankPosition must not be negative", ErrInvalid)
	}
	if event.EventType == "dwell" && event.DwellMs <= 0 {
		return fmt.Errorf("%w: dwell requires positive dwellMs", ErrInvalid)
	}
	if event.EventType != "dwell" && event.DwellMs != 0 {
		return fmt.Errorf("%w: only dwell may include dwellMs", ErrInvalid)
	}
	return nil
}
