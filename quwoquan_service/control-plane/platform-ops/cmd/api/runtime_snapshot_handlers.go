package main

import (
	"regexp"
	"strings"
)

func isCanonicalSHA256(value string) bool {
	return regexp.MustCompile(`^sha256:[0-9a-f]{64}$`).MatchString(strings.TrimSpace(value))
}

func documentBool(value any) bool {
	if flag, ok := value.(bool); ok {
		return flag
	}
	return false
}
