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
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
)

func decodeNotificationUserAccountClosed(
	message runtimemessaging.StreamDelivery,
) (application.UserAccountClosedEvent, error) {
	values := durableFieldsToMap(message.Fields)
	eventName := strings.TrimSpace(values["eventName"])
	if eventName == "" {
		return application.UserAccountClosedEvent{},
			errors.New("UserAccountClosed eventName is missing")
	}
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
	if eventID == "" ||
		accountID == "" ||
		versionErr != nil ||
		accountVersion <= 0 {
		return application.UserAccountClosedEvent{},
			errors.New("UserAccountClosed stream identity is invalid")
	}
	if _, err := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(values["occurredAt"]),
	); err != nil {
		return application.UserAccountClosedEvent{},
			errors.New("UserAccountClosed occurredAt is invalid")
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
	payload.UserID = strings.TrimSpace(payload.UserID)
	payload.AccountState = strings.TrimSpace(payload.AccountState)
	if payload.UserID == "" ||
		payload.UserID != accountID ||
		payload.AccountState != "closed" {
		return application.UserAccountClosedEvent{},
			errors.New("UserAccountClosed payload identity or state is invalid")
	}
	updatedAt, err := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(payload.UpdatedAt),
	)
	if err != nil {
		return application.UserAccountClosedEvent{},
			errors.New("UserAccountClosed updatedAt is invalid")
	}
	event := application.UserAccountClosedEvent{
		EventID:      eventID,
		UserID:       payload.UserID,
		PersonaIDs:   normalizeUserAccountClosedPersonaIDs(payload.PersonaIDs),
		AccountState: payload.AccountState,
		UpdatedAt:    updatedAt.UTC(),
	}
	if err := event.Validate(); err != nil {
		return application.UserAccountClosedEvent{}, err
	}
	return event, nil
}

func normalizeUserAccountClosedPersonaIDs(values []string) []string {
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
	return normalized
}

func userAccountClosedDeadLetterFields(
	message runtimemessaging.StreamDelivery,
	cause error,
	attempts int64,
	errorClass string,
) []runtimemessaging.DurableField {
	messageValues := durableFieldsToMap(message.Fields)
	return irreversibleDeadLetterFields(irreversibleDeadLetterReference{
		SourceStream:   UserAccountEventStream,
		SourceStreamID: message.ID,
		EventClass:     "user_account_closed",
		EventID:        messageValues["eventId"],
		Content:        messageValues["payload"],
		ErrorClass:     errorClass,
		Cause:          cause,
		Attempts:       attempts,
	})
}

// irreversibleDeadLetterReference 是 durable DLQ 的唯一持久化摘要输入。
// 它明确禁止将源事件字段透传到 DLQ；原始 payload 仅保留在未 ACK 的 source PEL，
// 供受控恢复重新读取。
type irreversibleDeadLetterReference struct {
	SourceStream   string
	SourceStreamID string
	EventClass     string
	EventID        string
	Content        string
	ErrorClass     string
	Cause          error
	Attempts       int64
}

func irreversibleDeadLetterFields(
	reference irreversibleDeadLetterReference,
) []runtimemessaging.DurableField {
	causeText := ""
	if reference.Cause != nil {
		causeText = reference.Cause.Error()
	}
	values := map[string]string{
		"deadLetterId": irreversibleStreamDigest(
			strings.TrimSpace(reference.SourceStream) +
				"\x00" +
				strings.TrimSpace(reference.SourceStreamID),
		),
		"sourceStream":   strings.TrimSpace(reference.SourceStream),
		"sourceStreamId": strings.TrimSpace(reference.SourceStreamID),
		"eventClass":     strings.TrimSpace(reference.EventClass),
		"eventDigest":    irreversibleStreamDigest(reference.EventID),
		"contentDigest":  irreversibleStreamDigest(reference.Content),
		"attempts":       strconv.FormatInt(reference.Attempts, 10),
		"errorClass":     strings.TrimSpace(reference.ErrorClass),
		"errorDigest":    irreversibleStreamDigest(causeText),
		"deadLetteredAt": time.Now().UTC().Format(time.RFC3339Nano),
	}
	return durableFieldsFromMap(values)
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

func durableFieldsFromMap(values map[string]string) []runtimemessaging.DurableField {
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

func irreversibleStreamDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}
