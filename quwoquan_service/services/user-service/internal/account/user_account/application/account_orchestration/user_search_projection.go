package application

import (
	"strings"

	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

// UserProfileSearchEligible defines the discoverable user set from the canonical
// account lifecycle state. Anonymous / suspended / deleted accounts are not
// searchable, so the ES index must contain exactly this set.
func UserProfileSearchEligible(profile model.UserProfile) bool {
	return strings.EqualFold(strings.TrimSpace(profile.AccountState), "active")
}
