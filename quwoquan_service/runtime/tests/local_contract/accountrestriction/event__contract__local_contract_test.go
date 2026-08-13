// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
package local_contract

import (
	"errors"
	"testing"

	"quwoquan_service/runtime/accountrestriction"
)

func TestDecodeCanonicalRestrictionEvent(t *testing.T) {
	values := map[string]string{
		"eventId":        "event-1",
		"eventName":      accountrestriction.UserSuspendedEventName,
		"accountId":      "account-1",
		"accountVersion": "7",
		"occurredAt":     "2026-07-21T04:01:02Z",
		"payload": `{"userId":"account-1","personaIds":["persona-2","persona-1","persona-1"],` +
			`"accountState":"suspended","authEpoch":3,"decisionRef":"decision-1",` +
			`"occurredAt":"2026-07-21T04:01:02Z"}`,
	}
	event, err := accountrestriction.Decode(values)
	if err != nil {
		t.Fatalf("decode suspension: %v", err)
	}
	if !event.Restricted() || event.AuthEpoch != 3 ||
		len(event.SubjectIDs()) != 3 || event.Digest() == "" {
		t.Fatalf("unexpected suspension event: %+v", event)
	}

	values["eventName"] = accountrestriction.UserRestoredEventName
	values["payload"] = `{"userId":"account-1","personaIds":["persona-1"],` +
		`"accountState":"active","authEpoch":4,"decisionRef":"decision-2",` +
		`"occurredAt":"2026-07-21T04:01:02Z"}`
	event, err = accountrestriction.Decode(values)
	if err != nil || event.Restricted() {
		t.Fatalf("decode restoration: event=%+v err=%v", event, err)
	}
}

func TestDecodeRestrictionEventRejectsProtocolDrift(t *testing.T) {
	base := map[string]string{
		"eventId":        "event-1",
		"eventName":      accountrestriction.UserSuspendedEventName,
		"accountId":      "account-1",
		"accountVersion": "7",
		"occurredAt":     "2026-07-21T04:01:02Z",
		"payload": `{"userId":"account-1","personaIds":[],"accountState":"suspended",` +
			`"authEpoch":3,"decisionRef":"decision-1","occurredAt":"2026-07-21T04:01:02Z"}`,
	}

	for name, mutate := range map[string]func(map[string]string){
		"unknown event": func(values map[string]string) {
			values["eventName"] = "UserRegistered"
		},
		"unknown payload field": func(values map[string]string) {
			values["payload"] = `{"userId":"account-1","personaIds":[],"accountState":"suspended",` +
				`"authEpoch":3,"decisionRef":"decision-1","occurredAt":"2026-07-21T04:01:02Z",` +
				`"caseRef":"must-not-cross"}`
		},
		"state mismatch": func(values map[string]string) {
			values["payload"] = `{"userId":"account-1","personaIds":[],"accountState":"active",` +
				`"authEpoch":3,"decisionRef":"decision-1","occurredAt":"2026-07-21T04:01:02Z"}`
		},
		"timestamp mismatch": func(values map[string]string) {
			values["occurredAt"] = "2026-07-21T04:01:03Z"
		},
	} {
		t.Run(name, func(t *testing.T) {
			values := make(map[string]string, len(base))
			for key, value := range base {
				values[key] = value
			}
			mutate(values)
			_, err := accountrestriction.Decode(values)
			if err == nil {
				t.Fatal("protocol drift unexpectedly accepted")
			}
			if name == "unknown event" && !errors.Is(
				err,
				accountrestriction.ErrUnsupportedEvent,
			) {
				t.Fatalf("unknown event error=%v", err)
			}
		})
	}
}
