// Package stream consumes durable UserAccount security terminal facts.
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
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
)

const userAccountEventStream = "events.user.account"

var errUnsupportedUserAccountSecurityEvent = errors.New(
	"unsupported user account security event",
)

func decodeUserAccountSecurityEvent(
	message runtimemessaging.StreamDelivery,
) (application.AccountSecurityEvent, error) {
	values := durableFieldsToMap(message.Fields)
	eventName := strings.TrimSpace(values["eventName"])
	switch eventName {
	case "UserAccountClosed", "UserSuspended", "UserRestored":
	default:
		return application.AccountSecurityEvent{}, fmt.Errorf(
			"%w: %s",
			errUnsupportedUserAccountSecurityEvent,
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
	if eventID == "" || accountID == "" || versionErr != nil ||
		accountVersion <= 0 || occurredAtErr != nil {
		return application.AccountSecurityEvent{},
			errors.New("invalid UserAccount security stream identity")
	}
	switch eventName {
	case "UserAccountClosed":
		return decodeUserAccountClosedSecurityEvent(
			values["payload"],
			eventID,
			accountID,
			occurredAt,
		)
	default:
		return decodeUserAccountEnforcementSecurityEvent(
			eventName,
			values["payload"],
			eventID,
			accountID,
			occurredAt,
		)
	}
}

func decodeUserAccountClosedSecurityEvent(
	rawPayload string,
	eventID string,
	accountID string,
	occurredAt time.Time,
) (application.AccountSecurityEvent, error) {
	var payload struct {
		UserID       string   `json:"userId"`
		PersonaIDs   []string `json:"personaIds"`
		AccountState string   `json:"accountState"`
		UpdatedAt    string   `json:"updatedAt"`
	}
	if err := decodeExactPayload(rawPayload, &payload); err != nil {
		return application.AccountSecurityEvent{}, err
	}
	if payload.PersonaIDs == nil ||
		strings.TrimSpace(payload.UserID) != accountID ||
		strings.TrimSpace(payload.AccountState) != "closed" {
		return application.AccountSecurityEvent{},
			errors.New("invalid UserAccountClosed security payload")
	}
	if _, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(payload.UpdatedAt)); err != nil {
		return application.AccountSecurityEvent{},
			errors.New("invalid UserAccountClosed update time")
	}
	event := application.AccountSecurityEvent{
		EventID:      eventID,
		AccountID:    accountID,
		PersonaIDs:   normalizePersonaIDs(payload.PersonaIDs),
		AccountState: "closed",
		OccurredAt:   occurredAt.UTC(),
	}
	if err := event.Validate(); err != nil {
		return application.AccountSecurityEvent{}, err
	}
	return event, nil
}

func decodeUserAccountEnforcementSecurityEvent(
	eventName string,
	rawPayload string,
	eventID string,
	accountID string,
	occurredAt time.Time,
) (application.AccountSecurityEvent, error) {
	var payload struct {
		UserID       string   `json:"userId"`
		PersonaIDs   []string `json:"personaIds"`
		AccountState string   `json:"accountState"`
		AuthEpoch    int64    `json:"authEpoch"`
		DecisionRef  string   `json:"decisionRef"`
		OccurredAt   string   `json:"occurredAt"`
	}
	if err := decodeExactPayload(rawPayload, &payload); err != nil {
		return application.AccountSecurityEvent{}, err
	}
	expectedState := "suspended"
	if eventName == "UserRestored" {
		expectedState = "active"
	}
	if payload.PersonaIDs == nil ||
		strings.TrimSpace(payload.UserID) != accountID ||
		strings.TrimSpace(payload.AccountState) != expectedState ||
		payload.AuthEpoch <= 0 ||
		strings.TrimSpace(payload.DecisionRef) == "" {
		return application.AccountSecurityEvent{},
			errors.New("invalid UserAccount enforcement security payload")
	}
	if _, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(payload.OccurredAt)); err != nil {
		return application.AccountSecurityEvent{},
			errors.New("invalid UserAccount enforcement occurrence time")
	}
	event := application.AccountSecurityEvent{
		EventID:      eventID,
		AccountID:    accountID,
		PersonaIDs:   normalizePersonaIDs(payload.PersonaIDs),
		AccountState: expectedState,
		AuthEpoch:    payload.AuthEpoch,
		OccurredAt:   occurredAt.UTC(),
	}
	if err := event.Validate(); err != nil {
		return application.AccountSecurityEvent{}, err
	}
	return event, nil
}

func decodeExactPayload(raw string, destination any) error {
	decoder := json.NewDecoder(strings.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(destination); err != nil {
		return errors.New("invalid UserAccount security payload")
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return errors.New("invalid UserAccount security payload")
	}
	return nil
}

func normalizePersonaIDs(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, duplicate := seen[value]; duplicate {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func accountSecurityDeadLetterFields(
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
		"attempts":       strconv.FormatInt(attempts, 10),
		"contentDigest":  accountSecurityDigest(values["payload"]),
		"deadLetterId":   accountSecurityDigest(userAccountEventStream + "\x00" + message.ID),
		"deadLetteredAt": time.Now().UTC().Format(time.RFC3339Nano),
		"errorClass":     strings.TrimSpace(errorClass),
		"errorDigest":    accountSecurityDigest(causeText),
		"eventClass":     accountSecurityEventClass(strings.TrimSpace(values["eventName"])),
		"eventDigest":    accountSecurityDigest(values["eventId"]),
		"sourceStream":   userAccountEventStream,
		"sourceStreamId": message.ID,
	})
}

func accountSecurityEventClass(eventName string) string {
	switch eventName {
	case "UserAccountClosed":
		return "closed"
	case "UserSuspended":
		return "suspended"
	case "UserRestored":
		return "restored"
	default:
		return "unknown"
	}
}

func durableFieldsToMap(
	fields []runtimemessaging.DurableField,
) map[string]string {
	values := make(map[string]string, len(fields))
	for _, field := range fields {
		values[field.Name] = field.Value
	}
	return values
}

func durableFieldValue(
	fields []runtimemessaging.DurableField,
	name string,
) string {
	for _, field := range fields {
		if field.Name == name {
			return field.Value
		}
	}
	return ""
}

func durableFieldsFromMap(
	values map[string]string,
) []runtimemessaging.DurableField {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	fields := make([]runtimemessaging.DurableField, 0, len(keys))
	for _, key := range keys {
		fields = append(fields, runtimemessaging.DurableField{
			Name:  key,
			Value: values[key],
		})
	}
	return fields
}

func accountSecurityDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}
