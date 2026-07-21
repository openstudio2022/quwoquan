package mq

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
	"quwoquan_service/services/search-service/internal/application"
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
	eventID := strings.TrimSpace(values["eventId"])
	accountID := strings.TrimSpace(values["accountId"])
	accountVersion, versionErr := strconv.ParseInt(
		strings.TrimSpace(values["accountVersion"]),
		10,
		64,
	)
	occurredAt, occurredAtErr := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(values["occurredAt"]),
	)
	if eventID == "" ||
		accountID == "" ||
		versionErr != nil ||
		accountVersion <= 0 ||
		occurredAtErr != nil {
		return application.UserAccountClosedEvent{},
			errors.New("UserAccountClosed stream identity is invalid")
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
		return application.UserAccountClosedEvent{}, fmt.Errorf(
			"decode UserAccountClosed payload: %w",
			err,
		)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return application.UserAccountClosedEvent{},
			errors.New("UserAccountClosed payload has trailing data")
	}
	if payload.PersonaIDs == nil {
		return application.UserAccountClosedEvent{},
			errors.New("UserAccountClosed personaIds is missing")
	}
	updatedAt, err := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(payload.UpdatedAt),
	)
	if err != nil {
		return application.UserAccountClosedEvent{},
			errors.New("UserAccountClosed updatedAt is invalid")
	}
	if strings.TrimSpace(payload.UserID) != accountID {
		return application.UserAccountClosedEvent{},
			errors.New("UserAccountClosed accountId does not match payload userId")
	}
	event := application.UserAccountClosedEvent{
		EventID:        eventID,
		AccountVersion: accountVersion,
		UserID:         strings.TrimSpace(payload.UserID),
		PersonaIDs:     normalizePersonaIDs(payload.PersonaIDs),
		AccountState:   strings.TrimSpace(payload.AccountState),
		UpdatedAt:      updatedAt.UTC(),
		OccurredAt:     occurredAt.UTC(),
	}
	if err := event.Validate(); err != nil {
		return application.UserAccountClosedEvent{}, err
	}
	return event, nil
}

func normalizePersonaIDs(values []string) []string {
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

func userAccountClosedDeadLetterFields(
	message runtimemessaging.StreamDelivery,
	cause error,
	attempts int64,
) []runtimemessaging.DurableField {
	values := durableFieldsToMap(message.Fields)
	deadLetterValues := map[string]string{
		"sourceStream":   UserAccountEventStream,
		"sourceStreamId": message.ID,
		"attempts":       strconv.FormatInt(attempts, 10),
		"errorDigest":    irreversibleStreamDigest(cause.Error()),
		"deadLetteredAt": time.Now().UTC().Format(time.RFC3339Nano),
	}
	for _, key := range []string{
		"eventId",
		"eventName",
		"accountId",
		"accountVersion",
		"payload",
		"occurredAt",
	} {
		deadLetterValues[key] = values[key]
	}
	fields := make([]runtimemessaging.DurableField, 0, len(deadLetterValues))
	for _, key := range []string{
		"sourceStream",
		"sourceStreamId",
		"attempts",
		"errorDigest",
		"deadLetteredAt",
		"eventId",
		"eventName",
		"accountId",
		"accountVersion",
		"payload",
		"occurredAt",
	} {
		fields = append(fields, runtimemessaging.DurableField{
			Name:  key,
			Value: deadLetterValues[key],
		})
	}
	return fields
}

func durableFieldsToMap(fields []runtimemessaging.DurableField) map[string]string {
	values := make(map[string]string, len(fields))
	for _, field := range fields {
		values[field.Name] = field.Value
	}
	return values
}

func durableFieldValue(fields []runtimemessaging.DurableField, name string) string {
	for _, field := range fields {
		if field.Name == name {
			return field.Value
		}
	}
	return ""
}

func irreversibleStreamDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}
