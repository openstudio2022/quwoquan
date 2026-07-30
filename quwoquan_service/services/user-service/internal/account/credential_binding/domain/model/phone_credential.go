package model

import "strings"

// NormalizePhoneCredentialKey is the one canonical normalization applied
// before a phone identity is compared with CredentialBinding state. It does
// not validate country-specific numbering rules; provider validation remains
// outside the aggregate.
func NormalizePhoneCredentialKey(phone string) string {
	trimmed := strings.TrimSpace(phone)
	if trimmed == "" {
		return ""
	}
	replacer := strings.NewReplacer(" ", "", "-", "", "(", "", ")", "")
	return replacer.Replace(trimmed)
}
