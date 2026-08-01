package stream

import (
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

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
)

var errUnsupportedUserAccountEvent = errors.New("unsupported user account event")

func decodeUserAccountClosed(
	message runtimemessaging.StreamDelivery,
) (application.UserAccountClosedEvent, error) {
	values := durableFieldsToMap(message.Fields)
	eventName := strings.TrimSpace(values["eventName"])
	if eventName != application.UserAccountClosedEventName {
		return application.UserAccountClosedEvent{}, fmt.Errorf(
			"%w: %s",
			errUnsupportedUserAccountEvent,
			eventName,
		)
	}
	accountVersion, versionErr := strconv.ParseInt(
		strings.TrimSpace(values["accountVersion"]),
		10,
		64,
	)
	eventID := strings.TrimSpace(values["eventId"])
	accountID := strings.TrimSpace(values["accountId"])
	if eventID == "" || accountID == "" || versionErr != nil || accountVersion <= 0 {
		return application.UserAccountClosedEvent{},
			errors.New("integration UserAccountClosed stream identity is invalid")
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(values["occurredAt"]))
	if err != nil {
		return application.UserAccountClosedEvent{},
			errors.New("integration UserAccountClosed occurredAt is invalid")
	}
	var payload struct {
		UserID       string   `json:"userId"`
		PersonaIDs   []string `json:"personaIds"`
		AccountState string   `json:"accountState"`
		UpdatedAt    string   `json:"updatedAt"`
	}
	decoder := json.NewDecoder(strings.NewReader(values["payload"]))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		return application.UserAccountClosedEvent{},
			fmt.Errorf("decode integration UserAccountClosed payload: %w", err)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return application.UserAccountClosedEvent{},
			errors.New("integration UserAccountClosed payload has trailing data")
	}
	if payload.PersonaIDs == nil {
		return application.UserAccountClosedEvent{},
			errors.New("integration UserAccountClosed personaIds is missing")
	}
	updatedAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(payload.UpdatedAt))
	if err != nil {
		return application.UserAccountClosedEvent{},
			errors.New("integration UserAccountClosed updatedAt is invalid")
	}
	event := application.UserAccountClosedEvent{
		EventID:        eventID,
		AccountVersion: accountVersion,
		UserID:         strings.TrimSpace(payload.UserID),
		PersonaIDs:     normalizedStrings(payload.PersonaIDs),
		AccountState:   strings.TrimSpace(payload.AccountState),
		UpdatedAt:      updatedAt.UTC(),
		OccurredAt:     occurredAt.UTC(),
	}
	if event.UserID != accountID {
		return application.UserAccountClosedEvent{},
			errors.New("integration UserAccountClosed account identity mismatch")
	}
	if err := event.Validate(); err != nil {
		return application.UserAccountClosedEvent{}, err
	}
	return event, nil
}

func durableFieldsToMap(fields []runtimemessaging.DurableField) map[string]string {
	values := make(map[string]string, len(fields))
	for _, field := range fields {
		values[field.Name] = field.Value
	}
	return values
}

func durableFieldsFromMap(values map[string]string) []runtimemessaging.DurableField {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	fields := make([]runtimemessaging.DurableField, 0, len(keys))
	for _, key := range keys {
		fields = append(fields, runtimemessaging.DurableField{Name: key, Value: values[key]})
	}
	return fields
}

func normalizedStrings(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}

func deadLetterFields(
	message runtimemessaging.StreamDelivery,
	cause error,
	attempts int64,
	errorClass string,
) []runtimemessaging.DurableField {
	values := durableFieldsToMap(message.Fields)
	causeText := ""
	if cause != nil {
		causeText = cause.Error()
	}
	return durableFieldsFromMap(map[string]string{
		"deadLetterId":   irreversibleDigest(UserAccountEventStream + "\x00" + message.ID),
		"sourceStream":   UserAccountEventStream,
		"sourceStreamId": message.ID,
		"eventClass":     "user_account_closed",
		"eventDigest":    irreversibleDigest(values["eventId"]),
		"contentDigest":  irreversibleDigest(values["payload"]),
		"attempts":       strconv.FormatInt(attempts, 10),
		"errorClass":     strings.TrimSpace(errorClass),
		"errorDigest":    irreversibleDigest(causeText),
		"deadLetteredAt": time.Now().UTC().Format(time.RFC3339Nano),
	})
}

func irreversibleDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}
