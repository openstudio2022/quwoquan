package mq

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"sort"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

func decodeUserAccountClosed(
	values map[string]string,
) (application.UserAccountClosedEvent, error) {
	eventID := strings.TrimSpace(values["eventId"])
	eventName := strings.TrimSpace(values["eventName"])
	if eventName != "" && eventName != application.UserAccountClosedEventName {
		return application.UserAccountClosedEvent{}, fmt.Errorf(
			"%w: %s",
			errUnsupportedUserAccountEvent,
			eventName,
		)
	}
	accountID := strings.TrimSpace(values["accountId"])
	version, err := strconv.ParseInt(
		strings.TrimSpace(values["accountVersion"]),
		10,
		64,
	)
	if eventID == "" || eventName != application.UserAccountClosedEventName ||
		accountID == "" || err != nil || version <= 0 {
		return application.UserAccountClosedEvent{},
			fmt.Errorf("UserAccountClosed stream identity is invalid")
	}
	occurredAt, err := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(values["occurredAt"]),
	)
	if err != nil {
		return application.UserAccountClosedEvent{},
			fmt.Errorf("UserAccountClosed occurredAt is invalid")
	}
	var payload struct {
		UserID       string   `json:"userId"`
		PersonaIDs   []string `json:"personaIds"`
		AccountState string   `json:"accountState"`
		UpdatedAt    string   `json:"updatedAt"`
	}
	decoder := json.NewDecoder(bytes.NewBufferString(values["payload"]))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		return application.UserAccountClosedEvent{},
			fmt.Errorf("decode UserAccountClosed payload: %w", err)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return application.UserAccountClosedEvent{},
			fmt.Errorf("decode UserAccountClosed payload trailing data")
	}
	payload.UserID = strings.TrimSpace(payload.UserID)
	payload.AccountState = strings.TrimSpace(payload.AccountState)
	if payload.PersonaIDs == nil ||
		payload.UserID == "" || payload.UserID != accountID ||
		payload.AccountState != "closed" {
		return application.UserAccountClosedEvent{},
			fmt.Errorf("UserAccountClosed payload state or identity is invalid")
	}
	updatedAt, err := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(payload.UpdatedAt),
	)
	if err != nil {
		return application.UserAccountClosedEvent{},
			fmt.Errorf("UserAccountClosed updatedAt is invalid")
	}
	event := application.UserAccountClosedEvent{
		EventID:        eventID,
		EventName:      eventName,
		AccountID:      accountID,
		AccountVersion: version,
		UserID:         payload.UserID,
		PersonaIDs:     dedupeAccountSubjects(payload.PersonaIDs),
		AccountState:   payload.AccountState,
		UpdatedAt:      updatedAt.UTC(),
		OccurredAt:     occurredAt.UTC(),
	}
	if err := event.Validate(); err != nil {
		return application.UserAccountClosedEvent{}, err
	}
	return event, nil
}

func dedupeAccountSubjects(values []string) []string {
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
