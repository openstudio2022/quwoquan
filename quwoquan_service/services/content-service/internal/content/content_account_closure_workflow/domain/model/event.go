package model

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"sort"
	"strconv"
	"strings"
	"time"
)

const UserAccountClosedName = "UserAccountClosed"

type UserAccountClosedPayload struct {
	UserID       string
	PersonaIDs   []string
	AccountState string
	UpdatedAt    time.Time
}

type UserAccountClosedEvent struct {
	EventID        string
	EventName      string
	AccountID      string
	AccountVersion int64
	Payload        UserAccountClosedPayload
	OccurredAt     time.Time
}

func (event UserAccountClosedEvent) Validate() error {
	if event.EventID == "" ||
		event.EventName != UserAccountClosedName ||
		event.AccountID == "" ||
		event.AccountVersion <= 0 ||
		event.OccurredAt.IsZero() ||
		event.Payload.UserID == "" ||
		event.Payload.UpdatedAt.IsZero() {
		return errors.New("UserAccountClosed event is incomplete")
	}
	if event.AccountID != event.Payload.UserID {
		return errors.New("UserAccountClosed accountId does not match payload userId")
	}
	if event.Payload.AccountState != "closed" {
		return errors.New("UserAccountClosed payload accountState must be closed")
	}
	return nil
}

func (event UserAccountClosedEvent) SubjectIDs() []string {
	values := make([]string, 0, len(event.Payload.PersonaIDs)+2)
	values = append(values, event.AccountID, event.Payload.UserID)
	values = append(values, event.Payload.PersonaIDs...)
	return NormalizeSubjectIDs(values)
}

func (event UserAccountClosedEvent) Digest() string {
	personaIDs := append([]string(nil), event.Payload.PersonaIDs...)
	sort.Strings(personaIDs)
	canonical := strings.Join([]string{
		event.EventID,
		event.EventName,
		event.AccountID,
		strconv.FormatInt(event.AccountVersion, 10),
		strings.Join(personaIDs, "\x1f"),
		event.Payload.AccountState,
		event.Payload.UpdatedAt.UTC().Format(time.RFC3339Nano),
		event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}, "\x00")
	sum := sha256.Sum256([]byte(canonical))
	return hex.EncodeToString(sum[:])
}

func NormalizeSubjectIDs(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	normalized := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		normalized = append(normalized, value)
	}
	sort.Strings(normalized)
	return normalized
}

type WorkflowState string

const (
	WorkflowStateReceived               WorkflowState = "received"
	WorkflowStateExternalCleanupPending WorkflowState = "external_cleanup_pending"
	WorkflowStateCompleted              WorkflowState = "completed"
)

func (state WorkflowState) Valid() bool {
	return state == WorkflowStateReceived ||
		state == WorkflowStateExternalCleanupPending ||
		state == WorkflowStateCompleted
}
