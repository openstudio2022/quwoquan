package api_integration

import (
	"fmt"
	"net/http"
	"testing"

	"quwoquan_service/runtime/contractfixture"
)

type rtcFixturePack struct {
	SeedSets map[string]rtcFixtureSeedSet `json:"seedSets"`
}

type rtcFixtureSeedSet struct {
	Sessions []rtcFixtureSession `json:"sessions"`
}

type rtcFixtureSession struct {
	SessionID          string   `json:"sessionId"`
	Type               string   `json:"type"`
	CallerUserID       string   `json:"callerUserId"`
	ParticipantUserIDs []string `json:"participantUserIds"`
}

func TestContractFixtureSeed_RtcReadsViaHandler(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	pack, err := contractfixture.LoadRepositoryJSON[rtcFixturePack](
		"quwoquan_service/services/rtc-service/tests/support/contract_fixtures/scenarios/rtc_scenarios.json",
	)
	if err != nil {
		t.Fatalf("load rtc fixture: %v", err)
	}
	seed := pack.SeedSets["rtc_core"]
	if len(seed.Sessions) == 0 {
		t.Fatalf("rtc_core has no sessions")
	}
	for _, session := range seed.Sessions {
		// Fixture sessions share personas but CallSession enforces one active call
		// per actor/participant; verify each scenario against an isolated store.
		cleanAll(t)
		callType := "audio"
		if session.Type == "video" {
			callType = "video"
		}
		invitee := "fixture_user_invitee"
		for _, participantID := range session.ParticipantUserIDs {
			if participantID != session.CallerUserID {
				invitee = participantID
				break
			}
		}
		resp := doPost(
			t,
			"/rtc/calls",
			fmt.Sprintf(`{"callType":%q,"inviteeIds":[%q],"maxParticipants":2}`, callType, invitee),
			session.CallerUserID,
			http.StatusCreated,
		)
		call := extractSession(t, resp)
		if call["initiatorId"] != session.CallerUserID {
			t.Fatalf("initiatorId=%v, want %s", call["initiatorId"], session.CallerUserID)
		}
	}
}
