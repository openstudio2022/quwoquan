package model

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"time"
)

const (
	StateSeen = "seen"
	StateRead = "read"
)

type Fact struct {
	FactID         string    `json:"factId" bson:"factId"`
	OwnerPersonaID string    `json:"ownerPersonaId" bson:"ownerPersonaId"`
	ActivityID     string    `json:"activityId" bson:"activityId"`
	State          string    `json:"state" bson:"state"`
	OccurredAt     time.Time `json:"occurredAt" bson:"occurredAt"`
}

func New(
	ownerPersonaID string,
	activityID string,
	state string,
	occurredAt time.Time,
) (Fact, error) {
	ownerPersonaID = strings.TrimSpace(ownerPersonaID)
	activityID = strings.TrimSpace(activityID)
	state = strings.TrimSpace(state)
	if ownerPersonaID == "" || activityID == "" {
		return Fact{}, fmt.Errorf("owner persona and activity are required")
	}
	if state != StateSeen && state != StateRead {
		return Fact{}, fmt.Errorf("profile interaction read state must be seen or read")
	}
	if occurredAt.IsZero() {
		return Fact{}, fmt.Errorf("profile interaction read fact occurredAt is required")
	}
	sum := sha256.Sum256([]byte(ownerPersonaID + "\x00" + activityID + "\x00" + state))
	return Fact{
		FactID:         "pirf_" + hex.EncodeToString(sum[:16]),
		OwnerPersonaID: ownerPersonaID,
		ActivityID:     activityID,
		State:          state,
		OccurredAt:     occurredAt.UTC(),
	}, nil
}

func (f Fact) Validate() error {
	expected, err := New(f.OwnerPersonaID, f.ActivityID, f.State, f.OccurredAt)
	if err != nil {
		return err
	}
	if expected.FactID != strings.TrimSpace(f.FactID) {
		return fmt.Errorf("profile interaction read fact identity mismatch")
	}
	return nil
}
