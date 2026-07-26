package http

import "strings"

func firstTwoNonEmpty(values ...string) []string {
	out := make([]string, 0, 2)
	seen := map[string]struct{}{}
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed == "" {
			continue
		}
		if _, ok := seen[trimmed]; ok {
			continue
		}
		seen[trimmed] = struct{}{}
		out = append(out, trimmed)
		if len(out) == 2 {
			break
		}
	}
	return out
}
