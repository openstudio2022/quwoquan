package event

import (
	accountevent "quwoquan_service/services/user-service/generated/account/user_account/contract/user/event"
	personaevent "quwoquan_service/services/user-service/generated/persona_management/persona/contract/user/event"
	contactevent "quwoquan_service/services/user-service/generated/relationship/contact_discovery_record/contract/user/event"
	greetingevent "quwoquan_service/services/user-service/generated/relationship/greeting_request/contract/user/event"
)

const (
	UserProfileUpdated        = accountevent.UserProfileUpdated
	UserProfileTagsChanged    = accountevent.UserProfileTagsChanged
	UserAvatarUpdated         = accountevent.UserAvatarUpdated
	UserRegistered            = accountevent.UserRegistered
	UserSuspended             = accountevent.UserSuspended
	UserRestored              = accountevent.UserRestored
	UserAccountClosed         = accountevent.UserAccountClosed
	PersonaCreated            = personaevent.PersonaCreated
	PersonaUpdated            = personaevent.PersonaUpdated
	PersonaRetired            = personaevent.PersonaRetired
	PersonaActivated          = personaevent.PersonaActivated
	ContactDiscoveryInitiated = contactevent.ContactDiscoveryInitiated
	ContactDiscoveryCompleted = contactevent.ContactDiscoveryCompleted
	GreetingRequestSent       = greetingevent.GreetingRequestSent
	GreetingRequestReplied    = greetingevent.GreetingRequestReplied
	GreetingRequestIgnored    = greetingevent.GreetingRequestIgnored
	GreetingRequestCancelled  = greetingevent.GreetingRequestCancelled
	GreetingRequestExpired    = greetingevent.GreetingRequestExpired
)
