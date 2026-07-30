package event

import (
	accountevent "quwoquan_service/services/user-service/generated/account/user_account/contract/user/event"
)

const (
	UserProfileUpdated     = accountevent.UserProfileUpdated
	UserProfileTagsChanged = accountevent.UserProfileTagsChanged
	UserAvatarUpdated      = accountevent.UserAvatarUpdated
	UserRegistered         = accountevent.UserRegistered
	UserSuspended          = accountevent.UserSuspended
	UserRestored           = accountevent.UserRestored
	UserAccountClosed      = accountevent.UserAccountClosed
)
