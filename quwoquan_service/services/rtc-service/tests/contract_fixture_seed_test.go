package tests

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
	pack, err := contractfixture.LoadMetadataJSON[rtcFixturePack](
		"rtc/test_fixtures/scenarios/rtc_scenarios.json",
	)
	if err != nil {
		t.Fatalf("load rtc fixture: %v", err)
	}
	seed := pack.SeedSets["rtc_core"]
	if len(seed.Sessions) == 0 {
		t.Fatalf("rtc_core has no sessions")
	}
	for _, session := range seed.Sessions {
		callType := "audio"
		if session.Type == "video" {
			callType = "video"
		}
		invitee := "fixture_user_invitee"
		if len(session.ParticipantUserIDs) > 1 {
			invitee = session.ParticipantUserIDs[1]
		}
		resp := doPost(
			t,
			"/v1/rtc/calls",
			fmt.Sprintf(`{"callType":%q,"inviteeIds":[%q]}`, callType, invitee),
			session.CallerUserID,
			http.StatusCreated,
		)
		call := extractSession(t, resp)
		if call["initiatorId"] != session.CallerUserID {
			t.Fatalf("initiatorId=%v, want %s", call["initiatorId"], session.CallerUserID)
		}
	}
}
