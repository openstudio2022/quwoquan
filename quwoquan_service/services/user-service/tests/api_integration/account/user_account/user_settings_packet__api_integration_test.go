package api_integration

import (
	"context"
	"net/http"
	"testing"
)

func TestUserSettingsTypedCommandsCASNoopAndAuditOutbox(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	const ownerID = "settings-packet-owner"
	createTestProfile(t, ownerID, "settings owner")
	createTestPersonaFull(
		t,
		"",
		ownerID,
		"settings-packet-persona",
		"settings owner",
		"open",
		true,
	)
	headers := authHeadersForPersona(ownerID, "settings-packet-persona")

	callUpdate := doRequest(
		t,
		http.MethodPatch,
		"/user/settings/calls",
		`{"defaultIncomingCallRingtoneId":"official.blue-wave","allowCallerRingtoneOverride":false,"enableCallVibration":false,"enableGroupCallRing":true}`,
		headers,
	)
	if callUpdate.Code != http.StatusOK {
		t.Fatalf(
			"update call settings: status=%d body=%s",
			callUpdate.Code,
			callUpdate.Body.String(),
		)
	}
	callBody := parseJSON(t, callUpdate)
	if callBody["version"] != float64(1) ||
		callBody["idempotentReplay"] == true {
		t.Fatalf("unexpected call command result: %#v", callBody)
	}
	callRead := doRequest(
		t,
		http.MethodGet,
		"/user/settings/calls",
		"",
		headers,
	)
	if callRead.Code != http.StatusOK {
		t.Fatalf("get call settings: status=%d body=%s", callRead.Code, callRead.Body.String())
	}
	callSlice := parseJSON(t, callRead)
	if callSlice["defaultIncomingCallRingtoneId"] != "official.blue-wave" ||
		callSlice["allowCallerRingtoneOverride"] != false ||
		callSlice["enableCallVibration"] != false ||
		callSlice["enableGroupCallRing"] != true {
		t.Fatalf("unexpected call settings slice: %#v", callSlice)
	}

	ctx := context.Background()
	var version int
	if err := pgPool.QueryRow(
		ctx,
		`SELECT version FROM user_settings WHERE user_id=$1`,
		ownerID,
	).Scan(&version); err != nil {
		t.Fatalf("read settings version: %v", err)
	}
	if version != 1 {
		t.Fatalf("first settings commit version=%d, want 1", version)
	}
	var events int
	if err := pgPool.QueryRow(
		ctx,
		`SELECT COUNT(*) FROM user_settings_outbox WHERE aggregate_id=$1`,
		ownerID,
	).Scan(&events); err != nil {
		t.Fatalf("count settings outbox: %v", err)
	}
	if events != 1 {
		t.Fatalf("first settings commit outbox=%d, want 1", events)
	}

	// 同值重写必须 no-op：版本和审计事实都不增加。
	replay := doRequest(
		t,
		http.MethodPatch,
		"/user/settings/calls",
		`{"defaultIncomingCallRingtoneId":"official.blue-wave","allowCallerRingtoneOverride":false,"enableCallVibration":false,"enableGroupCallRing":true}`,
		headers,
	)
	if replay.Code != http.StatusOK {
		t.Fatalf("same-value replay: status=%d body=%s", replay.Code, replay.Body.String())
	}
	replayBody := parseJSON(t, replay)
	if replayBody["version"] != float64(1) ||
		replayBody["idempotentReplay"] != true {
		t.Fatalf("same-value replay result mismatch: %#v", replayBody)
	}
	if err := pgPool.QueryRow(
		ctx,
		`SELECT version FROM user_settings WHERE user_id=$1`,
		ownerID,
	).Scan(&version); err != nil {
		t.Fatalf("read replay version: %v", err)
	}
	if err := pgPool.QueryRow(
		ctx,
		`SELECT COUNT(*) FROM user_settings_outbox WHERE aggregate_id=$1`,
		ownerID,
	).Scan(&events); err != nil {
		t.Fatalf("count replay outbox: %v", err)
	}
	if version != 1 || events != 1 {
		t.Fatalf("same-value replay mutated packet: version=%d events=%d", version, events)
	}

	appearance := doRequest(
		t,
		http.MethodPatch,
		"/user/settings/appearance",
		`{"themeMode":"dark","fontSizePreset":"lg","applyScope":"all_accounts"}`,
		headers,
	)
	if appearance.Code != http.StatusOK {
		t.Fatalf(
			"update appearance: status=%d body=%s",
			appearance.Code,
			appearance.Body.String(),
		)
	}
	appearanceResult := parseJSON(t, appearance)
	if appearanceResult["version"] != float64(2) {
		t.Fatalf("unexpected appearance command result: %#v", appearanceResult)
	}
	appearanceRead := doRequest(
		t,
		http.MethodGet,
		"/user/settings/appearance",
		"",
		headers,
	)
	if appearanceRead.Code != http.StatusOK {
		t.Fatalf(
			"get appearance: status=%d body=%s",
			appearanceRead.Code,
			appearanceRead.Body.String(),
		)
	}
	appearanceBody := parseJSON(t, appearanceRead)
	if appearanceBody["themeMode"] != "dark" ||
		appearanceBody["fontSizePreset"] != "lg" ||
		appearanceBody["source"] != "owner_default" {
		t.Fatalf("unexpected appearance slice: %#v", appearanceBody)
	}
	if err := pgPool.QueryRow(
		ctx,
		`SELECT version FROM user_settings WHERE user_id=$1`,
		ownerID,
	).Scan(&version); err != nil {
		t.Fatalf("read appearance version: %v", err)
	}
	if version != 2 {
		t.Fatalf("appearance commit version=%d, want 2", version)
	}

	invalid := doRequest(
		t,
		http.MethodPatch,
		"/user/settings/calls",
		`{"defaultIncomingCallRingtoneId":"custom.untrusted"}`,
		headers,
	)
	if invalid.Code != http.StatusBadRequest {
		t.Fatalf(
			"invalid ringtone status=%d body=%s",
			invalid.Code,
			invalid.Body.String(),
		)
	}

	unknownField := doRequest(
		t,
		http.MethodPatch,
		"/user/settings/notifications",
		`{"enablePush":true,"legacyDynamicPatch":true}`,
		headers,
	)
	if unknownField.Code != http.StatusBadRequest {
		t.Fatalf(
			"unknown field must be rejected: status=%d body=%s",
			unknownField.Code,
			unknownField.Body.String(),
		)
	}
}

func TestAssistantDeliveryPolicyReadsCanonicalOwnerSettings(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	const ownerID = "assistant-policy-owner"
	const personaID = "assistant-policy-persona"
	createTestProfile(t, ownerID, "assistant policy owner")
	createTestPersonaFull(
		t,
		"",
		ownerID,
		personaID,
		"assistant policy owner",
		"open",
		true,
	)
	headers := authHeadersForPersona(ownerID, personaID)
	notification := doRequest(
		t,
		http.MethodPatch,
		"/user/settings/notifications",
		`{"quietHoursStart":"22:30","quietHoursEnd":"07:00"}`,
		headers,
	)
	if notification.Code != http.StatusOK {
		t.Fatalf(
			"update quiet hours: status=%d body=%s",
			notification.Code,
			notification.Body.String(),
		)
	}
	privacy := doRequest(
		t,
		http.MethodPatch,
		"/user/settings/privacy",
		`{"assistantEnabled":false}`,
		headers,
	)
	if privacy.Code != http.StatusOK {
		t.Fatalf(
			"disable assistant: status=%d body=%s",
			privacy.Code,
			privacy.Body.String(),
		)
	}

	forbidden := doRequest(
		t,
		http.MethodGet,
		"/internal/user/accounts/"+ownerID+"/assistant-delivery-policy",
		"",
		serviceHeadersFor(
			"service:assistant-service",
			"user.profile.read",
		),
	)
	if forbidden.Code != http.StatusForbidden {
		t.Fatalf(
			"wrong service scope must fail closed: status=%d body=%s",
			forbidden.Code,
			forbidden.Body.String(),
		)
	}
	resolved := doRequest(
		t,
		http.MethodGet,
		"/internal/user/accounts/"+ownerID+"/assistant-delivery-policy",
		"",
		serviceHeadersFor(
			"service:assistant-service",
			"user.assistant_delivery_policy.read",
		),
	)
	if resolved.Code != http.StatusOK {
		t.Fatalf(
			"resolve assistant delivery policy: status=%d body=%s",
			resolved.Code,
			resolved.Body.String(),
		)
	}
	body := parseJSON(t, resolved)
	if body["userId"] != ownerID ||
		body["assistantEnabled"] != false ||
		body["quietHoursStart"] != "22:30" ||
		body["quietHoursEnd"] != "07:00" ||
		body["version"] != float64(2) {
		t.Fatalf("assistant delivery policy drifted: %#v", body)
	}
}
