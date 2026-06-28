package application

import (
	"context"
	"errors"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
	generated "quwoquan_service/services/chat-service/internal/generated"
)

// 「从群聊中选择联系人」用例（图四群列表 + 图五群成员多选）。
//
// 与 ListGroupCandidates 同源：mutual 判定经 relationship gate 回填权威关系，
// 仅保留 mutual 且未屏蔽的联系人。两个用例共享一次 mutualContactIDSet 计算，
// 前端不再逐群多次拉成员求交集。

// mutualContactIDSet 返回 viewer 的权威互关联系人 userId 集合（已排除屏蔽与自身）。
func (s *MemberService) mutualContactIDSet(
	ctx context.Context,
	userID string,
	limit int,
) (map[string]struct{}, error) {
	hits, err := s.combinedContactHits(ctx, userID, "", limit)
	if err != nil {
		return nil, err
	}
	viewer := strings.TrimSpace(userID)
	mutual := make(map[string]struct{}, len(hits))
	for _, hit := range hits {
		contactID := strings.TrimSpace(hit.ContactID)
		if contactID == "" || contactID == viewer {
			continue
		}
		if _, ok := mutual[contactID]; ok {
			continue
		}
		relationState, blocked := s.resolveCandidateRelation(ctx, userID, contactID, hit.RelationState)
		if blocked || relationState != "mutual" {
			continue
		}
		mutual[contactID] = struct{}{}
	}
	return mutual, nil
}

// ListSelectableGroupConversations 返回当前用户所在、且含互关联系人的群会话列表，
// 并给出每个群的互关好友数（friendMemberCount）。friendMemberCount==0 的群不返回。
func (s *MemberService) ListSelectableGroupConversations(
	ctx context.Context,
	userID string,
	query string,
	limit int,
) ([]map[string]any, error) {
	limit = clampSearchLimit(limit, 50)
	rows := make([]map[string]any, 0, limit)

	mutual, err := s.mutualContactIDSet(ctx, userID, 100)
	if err != nil {
		return nil, err
	}
	if len(mutual) == 0 {
		return rows, nil
	}

	conversations, err := s.repo.ListConversationsByUser(ctx, userID, 500, "")
	if err != nil {
		return nil, err
	}
	viewer := strings.TrimSpace(userID)
	normalizedQuery := normalizeSearchQuery(query)
	for _, conv := range conversations {
		if conv.Type != "group" {
			continue
		}
		if conv.Status != "" && conv.Status != "active" {
			continue
		}
		if normalizedQuery != "" && !strings.Contains(strings.ToLower(conv.Title), normalizedQuery) {
			continue
		}
		members, err := s.repo.ListMembers(ctx, conv.ID, 1000, "", "", "joined_asc")
		if err != nil {
			return nil, err
		}
		friendCount := countMutualMembers(members, mutual, viewer)
		if friendCount == 0 {
			continue
		}
		rows = append(rows, map[string]any{
			"conversationId":    conv.ID,
			"title":             conv.Title,
			"avatarUrl":         conv.AvatarUrl,
			"friendMemberCount": friendCount,
			"memberCount":       conv.MemberCount,
		})
		if len(rows) >= limit {
			break
		}
	}
	return rows, nil
}

// ListSelectableGroupContactMembers 返回指定群成员中与当前用户互关的联系人。
// 排除当前用户、非 user 成员与已屏蔽关系；行形状复用联系人行（ChatContactListRow）。
func (s *MemberService) ListSelectableGroupContactMembers(
	ctx context.Context,
	userID string,
	conversationID string,
	query string,
	limit int,
) ([]map[string]any, error) {
	limit = clampSearchLimit(limit, 100)
	conversationID = strings.TrimSpace(conversationID)
	if conversationID == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleChat, "缺少会话标识", "conversationId is required")
	}

	conv, err := s.repo.FindConversationByID(ctx, conversationID)
	if err != nil {
		if errors.Is(err, model.ErrConversationNotFound) {
			return nil, generated.AppErrorFromConversationNotFound("conversation not found: " + conversationID)
		}
		return nil, err
	}
	if conv == nil {
		return nil, generated.AppErrorFromConversationNotFound("conversation not found: " + conversationID)
	}

	mutual, err := s.mutualContactIDSet(ctx, userID, 200)
	if err != nil {
		return nil, err
	}

	members, err := s.repo.ListMembers(ctx, conversationID, 1000, "", "", "display_name_asc")
	if err != nil {
		return nil, err
	}

	viewer := strings.TrimSpace(userID)
	normalizedQuery := normalizeSearchQuery(query)
	items := make([]map[string]any, 0, limit)
	seen := map[string]struct{}{}
	for _, m := range members {
		id := strings.TrimSpace(m.UserId)
		if id == "" || id == viewer {
			continue
		}
		if m.MemberType != "" && m.MemberType != "user" {
			continue
		}
		if _, ok := mutual[id]; !ok {
			continue
		}
		if _, ok := seen[id]; ok {
			continue
		}
		if normalizedQuery != "" && !strings.Contains(strings.ToLower(m.DisplayName), normalizedQuery) {
			continue
		}
		seen[id] = struct{}{}
		items = append(items, map[string]any{
			"contactId":     id,
			"userId":        id,
			"displayName":   m.DisplayName,
			"avatarUrl":     m.AvatarUrl,
			"relationState": "mutual",
			"source":        "group",
		})
		if len(items) >= limit {
			break
		}
	}
	return items, nil
}

// countMutualMembers 统计成员中属于 mutual 集合的真实用户数（排除 viewer 自身与非 user 成员）。
func countMutualMembers(
	members []model.ConversationMember,
	mutual map[string]struct{},
	viewer string,
) int {
	count := 0
	for _, m := range members {
		id := strings.TrimSpace(m.UserId)
		if id == "" || id == viewer {
			continue
		}
		if m.MemberType != "" && m.MemberType != "user" {
			continue
		}
		if _, ok := mutual[id]; ok {
			count++
		}
	}
	return count
}
