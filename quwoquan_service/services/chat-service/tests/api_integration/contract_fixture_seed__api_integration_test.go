package api_integration

import (
	"testing"

	"quwoquan_service/runtime/contractfixture"
)

type chatFixturePack struct {
	SeedSets map[string]chatFixtureSeedSet `json:"seedSets"`
}

type chatFixtureSeedSet struct {
	Conversations []chatFixtureConversation      `json:"conversations"`
	Members       map[string][]chatFixtureMember `json:"members"`
}

type chatFixtureConversation struct {
	ID                     string   `json:"_id"`
	Type                   string   `json:"type"`
	MemberCount            int      `json:"memberCount"`
	GroupAvatarSourceUsers []string `json:"groupAvatarSourceUserIds"`
}

type chatFixtureMember struct {
	UserID string `json:"userId"`
}

func TestGroupFixtureMemberCountMatchesRoster(t *testing.T) {
	pack, err := contractfixture.LoadMetadataJSON[chatFixturePack](
		"messages/chat/test_fixtures/scenarios/chat_scenarios.json",
	)
	if err != nil {
		t.Fatalf("load chat fixture: %v", err)
	}
	for seedRef, seedSet := range pack.SeedSets {
		membersByConv := seedSet.Members
		for _, conv := range seedSet.Conversations {
			if conv.Type != "group" || conv.ID == "" {
				continue
			}
			roster := membersByConv[conv.ID]
			if conv.MemberCount != len(roster) {
				t.Fatalf("%s %s: memberCount=%d roster=%d", seedRef, conv.ID, conv.MemberCount, len(roster))
			}
			rosterIDs := make(map[string]struct{}, len(roster))
			for _, member := range roster {
				if member.UserID != "" {
					rosterIDs[member.UserID] = struct{}{}
				}
			}
			for _, userID := range conv.GroupAvatarSourceUsers {
				if _, ok := rosterIDs[userID]; !ok {
					t.Fatalf("%s %s: groupAvatarSourceUserIds contains %s not in roster", seedRef, conv.ID, userID)
				}
			}
		}
	}
}
