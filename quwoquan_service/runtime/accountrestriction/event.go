// Package accountrestriction decodes the canonical UserSuspended/UserRestored
// durable event owned by user-service. Resource services use this protocol to
// maintain reversible local restrictions; irreversible account closure stays
// on the separate UserAccountClosed workflow.
package accountrestriction

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	UserSuspendedEventName = "UserSuspended"
	UserRestoredEventName  = "UserRestored"
)

var (
	ErrUnsupportedEvent = errors.New("unsupported user account restriction event")
	ErrInvalidEvent     = errors.New("invalid user account restriction event")
)

// Event is the exact reversible enforcement event consumed from
// events.user.account. DecisionRef is opaque; case, evidence, approver and
// decision digest must never enter this payload.
type Event struct {
	EventID        string
	EventName      string
	AccountID      string
	AccountVersion int64
	UserID         string
	PersonaIDs     []string
	AccountState   string
	AuthEpoch      int64
	DecisionRef    string
	OccurredAt     time.Time
}

// Decode validates both the durable envelope and the strict canonical JSON
// payload. Unknown event names are distinguished so a shared stream consumer
// may route UserAccountClosed to its irreversible owner.
func Decode(values map[string]string) (Event, error) {
	eventName := strings.TrimSpace(values["eventName"])
	if eventName != UserSuspendedEventName && eventName != UserRestoredEventName {
		return Event{}, fmt.Errorf("%w: %q", ErrUnsupportedEvent, eventName)
	}
	accountVersion, err := strconv.ParseInt(
		strings.TrimSpace(values["accountVersion"]),
		10,
		64,
	)
	if err != nil || accountVersion <= 0 {
		return Event{}, fmt.Errorf("%w: accountVersion", ErrInvalidEvent)
	}
	envelopeOccurredAt, err := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(values["occurredAt"]),
	)
	if err != nil {
		return Event{}, fmt.Errorf("%w: occurredAt", ErrInvalidEvent)
	}
	var payload struct {
		UserID       string   `json:"userId"`
		PersonaIDs   []string `json:"personaIds"`
		AccountState string   `json:"accountState"`
		AuthEpoch    int64    `json:"authEpoch"`
		DecisionRef  string   `json:"decisionRef"`
		OccurredAt   string   `json:"occurredAt"`
	}
	decoder := json.NewDecoder(bytes.NewBufferString(values["payload"]))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		return Event{}, fmt.Errorf("%w: payload: %v", ErrInvalidEvent, err)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return Event{}, fmt.Errorf("%w: payload trailing data", ErrInvalidEvent)
	}
	if payload.PersonaIDs == nil {
		return Event{}, fmt.Errorf("%w: personaIds", ErrInvalidEvent)
	}
	payloadOccurredAt, err := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(payload.OccurredAt),
	)
	if err != nil {
		return Event{}, fmt.Errorf("%w: payload occurredAt", ErrInvalidEvent)
	}
	event := Event{
		EventID:        strings.TrimSpace(values["eventId"]),
		EventName:      eventName,
		AccountID:      strings.TrimSpace(values["accountId"]),
		AccountVersion: accountVersion,
		UserID:         strings.TrimSpace(payload.UserID),
		PersonaIDs:     NormalizeSubjects(payload.PersonaIDs),
		AccountState:   strings.TrimSpace(payload.AccountState),
		AuthEpoch:      payload.AuthEpoch,
		DecisionRef:    strings.TrimSpace(payload.DecisionRef),
		OccurredAt:     payloadOccurredAt.UTC(),
	}
	if !event.OccurredAt.Equal(envelopeOccurredAt.UTC()) {
		return Event{}, fmt.Errorf("%w: payload/envelope occurredAt mismatch", ErrInvalidEvent)
	}
	if err := event.Validate(); err != nil {
		return Event{}, err
	}
	return event, nil
}

func (event Event) Validate() error {
	wantState := "suspended"
	if event.EventName == UserRestoredEventName {
		wantState = "active"
	} else if event.EventName != UserSuspendedEventName {
		return fmt.Errorf("%w: eventName", ErrInvalidEvent)
	}
	if event.EventID == "" || event.AccountID == "" ||
		event.AccountVersion <= 0 || event.UserID == "" ||
		event.AuthEpoch <= 0 || event.DecisionRef == "" ||
		event.OccurredAt.IsZero() {
		return fmt.Errorf("%w: incomplete", ErrInvalidEvent)
	}
	if event.AccountID != event.UserID {
		return fmt.Errorf("%w: account identity mismatch", ErrInvalidEvent)
	}
	if event.AccountState != wantState {
		return fmt.Errorf("%w: accountState", ErrInvalidEvent)
	}
	return nil
}

func (event Event) Restricted() bool {
	return event.EventName == UserSuspendedEventName
}

func (event Event) SubjectIDs() []string {
	values := make([]string, 0, len(event.PersonaIDs)+2)
	values = append(values, event.AccountID, event.UserID)
	values = append(values, event.PersonaIDs...)
	return NormalizeSubjects(values)
}

func (event Event) Digest() string {
	personaIDs := append([]string(nil), event.PersonaIDs...)
	sort.Strings(personaIDs)
	canonical := strings.Join([]string{
		event.EventID,
		event.EventName,
		event.AccountID,
		strconv.FormatInt(event.AccountVersion, 10),
		strings.Join(personaIDs, "\x1f"),
		event.AccountState,
		strconv.FormatInt(event.AuthEpoch, 10),
		event.DecisionRef,
		event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}, "\x00")
	digest := sha256.Sum256([]byte(canonical))
	return hex.EncodeToString(digest[:])
}

func NormalizeSubjects(values []string) []string {
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
