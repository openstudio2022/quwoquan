package api_integration

import (
	"testing"
)

func TestGroupFixtureMemberCountMatchesRoster(t *testing.T) {
	seedSet, ok := buildChatContractSeed("chat_core")
	if !ok {
		t.Fatal("chat_core builder is unavailable")
	}
	for seedRef, seedSet := range map[string]chatFixtureSeedSet{"chat_core": seedSet} {
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
