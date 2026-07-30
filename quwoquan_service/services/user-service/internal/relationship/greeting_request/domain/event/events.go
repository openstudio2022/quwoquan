package event

import greetingevent "quwoquan_service/services/user-service/generated/relationship/greeting_request/contract/user/event"

const (
	GreetingRequestSent      = greetingevent.GreetingRequestSent
	GreetingRequestReplied   = greetingevent.GreetingRequestReplied
	GreetingRequestIgnored   = greetingevent.GreetingRequestIgnored
	GreetingRequestCancelled = greetingevent.GreetingRequestCancelled
)
