package application

import (
	"context"
	"strings"
	"time"

	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

func (s *MemberService) conversationContactHits(ctx context.Context, userID string, query string, limit int) ([]ContactSearchHit, error) {
	conversations, err := listUserConversations(ctx, s.conversations, s.userStates, userID)
	if err != nil {
		return nil, err
	}
	results := make([]ContactSearchHit, 0, limit)
	seen := make(map[string]struct{}, limit)
	for _, conversation := range conversations {
		hit, ok := s.contactHitForConversation(ctx, userID, conversation)
		if !ok {
			continue
		}
		contactID := hit.ContactID
		if _, ok := seen[contactID]; ok {
			continue
		}
		if query != "" && !matchesContactQuery(hit, query) {
			continue
		}
		if query != "" {
			hit.HighlightText = highlightContactHit(hit, query)
		}
		results = append(results, hit)
		seen[contactID] = struct{}{}
		if len(results) >= limit {
			break
		}
	}
	return results, nil
}

func (s *MemberService) contactHitForConversation(
	ctx context.Context,
	userID string,
	conversation conversationmodel.Conversation,
) (ContactSearchHit, bool) {
	if conversation.Type != "direct" {
		return ContactSearchHit{}, false
	}
	members, err := s.members.ListMembers(
		ctx,
		conversation.ID,
		ListMembersQuery{Limit: 10, Sort: MemberListSortJoinedAsc},
	)
	if err != nil {
		return ContactSearchHit{}, false
	}
	contactID := ""
	displayName := strings.TrimSpace(conversation.Title)
	avatarURL := strings.TrimSpace(conversation.AvatarUrl)
	for _, member := range members {
		if strings.TrimSpace(member.UserId) == strings.TrimSpace(userID) {
			continue
		}
		contactID = strings.TrimSpace(member.UserId)
		if name := strings.TrimSpace(member.DisplayName); name != "" {
			displayName = name
		}
		if avatar := strings.TrimSpace(member.AvatarUrl); avatar != "" {
			avatarURL = avatar
		}
		break
	}
	if contactID == "" {
		contactID = strings.TrimSpace(conversation.ID)
	}
	if displayName == "" {
		displayName = contactID
	}
	return ContactSearchHit{
		ContactID:       contactID,
		DisplayName:     displayName,
		AvatarURL:       avatarURL,
		Bio:             strings.TrimSpace(conversation.LastMessagePreview),
		MetFrom:         "会话",
		LastInteraction: conversation.LastMessageTime.UTC().Format(time.RFC3339),
		RelationState:   "not_following",
		ConversationID:  conversation.ID,
		ConversationType: strings.TrimSpace(
			conversation.Type,
		),
		Source:        "conversation",
		Subtitle:      conversation.LastMessagePreview,
		HighlightText: displayName,
		MatchedField:  "displayName",
	}, true
}
