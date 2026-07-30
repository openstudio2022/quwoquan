package accountclosure

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

const (
	UserAccountEventStream = "events.user.account"
	UserAccountClosedName  = "UserAccountClosed"
	ConsumerGroup          = "content-service-user-account-closed"
	DeadLetterStream       = "events.user.account.content-service.dlq"
)

var ErrUnsupportedEvent = errors.New("unsupported user account event")

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

func DecodeUserAccountClosedEvent(
	message rtredis.StreamMessage,
) (UserAccountClosedEvent, error) {
	values := message.Values
	eventName := strings.TrimSpace(values["eventName"])
	if eventName != UserAccountClosedName {
		return UserAccountClosedEvent{}, fmt.Errorf(
			"%w: %q",
			ErrUnsupportedEvent,
			eventName,
		)
	}
	accountVersion, err := strconv.ParseInt(
		strings.TrimSpace(values["accountVersion"]),
		10,
		64,
	)
	if err != nil || accountVersion <= 0 {
		return UserAccountClosedEvent{}, errors.New(
			"UserAccountClosed accountVersion is invalid",
		)
	}
	occurredAt, err := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(values["occurredAt"]),
	)
	if err != nil {
		return UserAccountClosedEvent{}, errors.New(
			"UserAccountClosed occurredAt is invalid",
		)
	}
	var rawPayload struct {
		UserID       string   `json:"userId"`
		PersonaIDs   []string `json:"personaIds"`
		AccountState string   `json:"accountState"`
		UpdatedAt    string   `json:"updatedAt"`
	}
	if err := json.Unmarshal([]byte(values["payload"]), &rawPayload); err != nil {
		return UserAccountClosedEvent{}, errors.New(
			"UserAccountClosed payload is invalid",
		)
	}
	if rawPayload.PersonaIDs == nil {
		return UserAccountClosedEvent{}, errors.New(
			"UserAccountClosed personaIds is missing",
		)
	}
	updatedAt, err := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(rawPayload.UpdatedAt),
	)
	if err != nil {
		return UserAccountClosedEvent{}, errors.New(
			"UserAccountClosed payload updatedAt is invalid",
		)
	}
	event := UserAccountClosedEvent{
		EventID:        strings.TrimSpace(values["eventId"]),
		EventName:      eventName,
		AccountID:      strings.TrimSpace(values["accountId"]),
		AccountVersion: accountVersion,
		Payload: UserAccountClosedPayload{
			UserID:       strings.TrimSpace(rawPayload.UserID),
			PersonaIDs:   normalizeSubjectIDs(rawPayload.PersonaIDs),
			AccountState: strings.TrimSpace(rawPayload.AccountState),
			UpdatedAt:    updatedAt.UTC(),
		},
		OccurredAt: occurredAt.UTC(),
	}
	if err := event.Validate(); err != nil {
		return UserAccountClosedEvent{}, err
	}
	return event, nil
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
		return errors.New(
			"UserAccountClosed accountId does not match payload userId",
		)
	}
	if event.Payload.AccountState != "closed" {
		return errors.New(
			"UserAccountClosed payload accountState must be closed",
		)
	}
	return nil
}

func (event UserAccountClosedEvent) SubjectIDs() []string {
	values := make(
		[]string,
		0,
		len(event.Payload.PersonaIDs)+2,
	)
	values = append(values, event.AccountID, event.Payload.UserID)
	values = append(values, event.Payload.PersonaIDs...)
	return normalizeSubjectIDs(values)
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

func normalizeSubjectIDs(values []string) []string {
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

func irreversibleDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}
