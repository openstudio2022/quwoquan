package api_integration

import (
	"testing"

	"quwoquan_service/runtime/contractfixture"
)

func TestGroupFixtureMemberCountMatchesRoster(t *testing.T) {
	pack, err := contractfixture.LoadRepositoryJSON[chatFixturePack](
		"quwoquan_service/services/chat-service/tests/support/contract_fixtures/scenarios/chat_scenarios.json",
	)
	if err != nil {
		t.Fatalf("load chat fixture: %v", err)
	}
	for seedRef, seedSet := range pack.SeedSets {
		membersByConv := seedSet.Members
		for _, conv := range seedSet.Conversations {
			if conv.Type != "group" {
				continue
			}
			convID := conv.ID
			if convID == "" {
				continue
			}
			roster := membersByConv[convID]
			if conv.MemberCount != len(roster) {
				t.Fatalf(
					"%s %s: memberCount=%d roster=%d",
					seedRef,
					convID,
					conv.MemberCount,
					len(roster),
				)
			}
			rosterIDs := make(map[string]struct{}, len(roster))
			for _, member := range roster {
				if member.UserID == "" {
					continue
				}
				rosterIDs[member.UserID] = struct{}{}
			}
			for _, userID := range conv.GroupAvatarSourceUsers {
				if _, ok := rosterIDs[userID]; !ok {
					t.Fatalf(
						"%s %s: groupAvatarSourceUserIds contains %s not in roster",
						seedRef,
						convID,
						userID,
					)
				}
			}
		}
	}
}
