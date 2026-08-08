package persistence

import (
	"encoding/json"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
)

func boundedLimit(value, fallback, maximum int) int {
	if value <= 0 {
		return fallback
	}
	if value > maximum {
		return maximum
	}
	return value
}

func encodePageCursor(updatedAt time.Time, id string) string {
	return strconv.FormatInt(updatedAt.UTC().UnixNano(), 10) + "|" + id
}

func decodePageCursor(value string) (time.Time, string, error) {
	parts := strings.SplitN(strings.TrimSpace(value), "|", 2)
	if len(parts) != 2 {
		return time.Time{}, "", generated.AppErrorFromInvalidArgument("homepage cursor is malformed")
	}
	nanos, err := strconv.ParseInt(parts[0], 10, 64)
	if err != nil {
		return time.Time{}, "", generated.AppErrorFromInvalidArgument("homepage cursor timestamp is malformed")
	}
	return time.Unix(0, nanos).UTC(), parts[1], nil
}

func rawMessagesToBytes(values []json.RawMessage) [][]byte {
	result := make([][]byte, 0, len(values))
	for _, value := range values {
		result = append(result, append([]byte(nil), value...))
	}
	return result
}

func bytesToRawMessages(values [][]byte) []json.RawMessage {
	result := make([]json.RawMessage, 0, len(values))
	for _, value := range values {
		result = append(result, append(json.RawMessage(nil), value...))
	}
	return result
}

func cloneFloat64(value *float64) *float64 {
	if value == nil {
		return nil
	}
	result := *value
	return &result
}
