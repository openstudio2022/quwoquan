package orchestration

import (
	"strconv"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

func normalizeSubscriptionStatus(raw string) (string, error) {
	status := strings.TrimSpace(raw)
	switch status {
	case assistant.SkillSubscriptionStatusActive, assistant.SkillSubscriptionStatusPaused, assistant.SkillSubscriptionStatusArchived:
		return status, nil
	default:
		return "", rterr.NewInvalidArgument(rterr.ModuleAssistant, "订阅状态无效", "unsupported subscription status")
	}
}

func compactStrings(items []string) []string {
	out := make([]string, 0, len(items))
	seen := map[string]bool{}
	for _, item := range items {
		item = strings.TrimSpace(item)
		if item == "" || seen[item] {
			continue
		}
		seen[item] = true
		out = append(out, item)
	}
	return out
}

func compactStringMap(items map[string]string) map[string]string {
	out := map[string]string{}
	for key, value := range items {
		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		if key == "" || value == "" {
			continue
		}
		out[key] = value
	}
	if len(out) == 0 {
		return nil
	}
	return out
}

func isSupportedCron(raw string) bool {
	parts := strings.Fields(raw)
	if len(parts) != 5 {
		return false
	}
	return cronFieldSupported(parts[0], 0, 59) && cronFieldSupported(parts[1], 0, 23) && parts[2] == "*" && parts[3] == "*" && parts[4] == "*"
}

func cronMatchesMinute(raw string, now time.Time) bool {
	parts := strings.Fields(raw)
	if len(parts) != 5 {
		return false
	}
	return cronPartMatches(parts[0], now.Minute(), 0, 59) && cronPartMatches(parts[1], now.Hour(), 0, 23) && parts[2] == "*" && parts[3] == "*" && parts[4] == "*"
}

func nextCronTrigger(raw string, after time.Time) (time.Time, bool) {
	candidate := after.UTC().Truncate(time.Minute).Add(time.Minute)
	for minute := 0; minute <= 24*60; minute++ {
		if cronMatchesMinute(raw, candidate) {
			return candidate, true
		}
		candidate = candidate.Add(time.Minute)
	}
	return time.Time{}, false
}

func cronFieldSupported(raw string, min int, max int) bool {
	if raw == "*" {
		return true
	}
	value, err := strconv.Atoi(raw)
	return err == nil && value >= min && value <= max
}

func cronPartMatches(raw string, value int, min int, max int) bool {
	if raw == "*" {
		return true
	}
	parsed, err := strconv.Atoi(raw)
	return err == nil && parsed >= min && parsed <= max && parsed == value
}
