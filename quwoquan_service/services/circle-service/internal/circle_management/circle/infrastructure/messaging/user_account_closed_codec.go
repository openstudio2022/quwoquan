package messaging

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"sort"
	"strconv"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
)

// decodeUserAccountClosed 直接解码 metadata 所有的 stream 字段，不定义第二套
// 可复用 wire DTO；application event 只是 Circle 投影的强类型输入。
func decodeUserAccountClosed(
	values map[string]string,
) (application.UserAccountClosedEvent, error) {
	if strings.TrimSpace(values["eventName"]) !=
		application.UserAccountClosedEventName {
		return application.UserAccountClosedEvent{},
			errUnsupportedUserAccountEvent
	}
	version, err := strconv.ParseInt(
		strings.TrimSpace(values["accountVersion"]),
		10,
		64,
	)
	if err != nil || version <= 0 {
		return application.UserAccountClosedEvent{},
			application.ErrInvalidUserAccountClosedEvent
	}
	occurredAt, err := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(values["occurredAt"]),
	)
	if err != nil {
		return application.UserAccountClosedEvent{},
			application.ErrInvalidUserAccountClosedEvent
	}
	var payload struct {
		UserID       string   `json:"userId"`
		PersonaIDs   []string `json:"personaIds"`
		AccountState string   `json:"accountState"`
		UpdatedAt    string   `json:"updatedAt"`
	}
	if err := json.Unmarshal([]byte(values["payload"]), &payload); err != nil ||
		payload.PersonaIDs == nil {
		return application.UserAccountClosedEvent{},
			application.ErrInvalidUserAccountClosedEvent
	}
	updatedAt, err := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(payload.UpdatedAt),
	)
	if err != nil {
		return application.UserAccountClosedEvent{},
			application.ErrInvalidUserAccountClosedEvent
	}
	event := application.UserAccountClosedEvent{
		EventID:        strings.TrimSpace(values["eventId"]),
		AccountID:      strings.TrimSpace(values["accountId"]),
		AccountVersion: version,
		UserID:         strings.TrimSpace(payload.UserID),
		PersonaIDs:     normalizeAccountSubjects(payload.PersonaIDs),
		AccountState:   strings.TrimSpace(payload.AccountState),
		UpdatedAt:      updatedAt.UTC(),
		OccurredAt:     occurredAt.UTC(),
	}
	if err := event.Validate(); err != nil {
		return application.UserAccountClosedEvent{}, err
	}
	return event, nil
}

func normalizeAccountSubjects(values []string) []string {
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
	sort.Strings(result)
	return result
}

func uniqueUserAccountMessages(
	groups ...[]runtimemessaging.StreamDelivery,
) []runtimemessaging.StreamDelivery {
	seen := make(map[string]struct{})
	result := make([]runtimemessaging.StreamDelivery, 0)
	for _, messages := range groups {
		for _, message := range messages {
			if _, exists := seen[message.ID]; exists {
				continue
			}
			seen[message.ID] = struct{}{}
			result = append(result, message)
		}
	}
	return result
}

func userAccountClosedDLQFields(
	message runtimemessaging.StreamDelivery,
	errorDigest string,
	attempts int64,
) []runtimemessaging.DurableField {
	values := runtimemessaging.DurableFieldMap(message.Fields)
	eventName := strings.TrimSpace(values["eventName"])
	if eventName == "" {
		eventName = "unknown"
	}
	return runtimemessaging.DurableFieldsFromMap(map[string]string{
		"deadLetterId":    irreversiblyIdentifyUserAccountMessage(message.ID),
		"sourceStream":    UserAccountEventStream,
		"sourceStreamId":  message.ID,
		"eventName":       eventName,
		"eventIdDigest":   irreversibleDigest(values["eventId"]),
		"accountIdDigest": irreversibleDigest(values["accountId"]),
		"payloadDigest":   irreversibleDigest(values["payload"]),
		"errorDigest":     errorDigest,
		"attempts":        strconv.FormatInt(attempts, 10),
		"deadLetteredAt":  time.Now().UTC().Format(time.RFC3339Nano),
	})
}

func irreversiblyIdentifyUserAccountMessage(messageID string) string {
	return irreversibleDigest(UserAccountEventStream + "\x00" + messageID)
}

func irreversibleDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}
