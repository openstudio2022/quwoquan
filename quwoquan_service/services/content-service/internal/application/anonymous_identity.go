package application

import "strings"

const (
	AnonymousFallbackOwnerID      = "uo_01_ad_0000_00000000000000000000000000"
	AnonymousFallbackSubAccountID = "us_01_0000_00000000000000000000000000"
)

func normalizeAnonymousSubAccountID(subAccountID string) string {
	trimmed := strings.TrimSpace(subAccountID)
	if trimmed == "" {
		return AnonymousFallbackSubAccountID
	}
	return trimmed
}

func isAnonymousFallbackSubAccountID(subAccountID string) bool {
	return normalizeAnonymousSubAccountID(subAccountID) == AnonymousFallbackSubAccountID
}
