package application

import (
	"context"
	"errors"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	generated "quwoquan_service/services/chat-service/generated/chat/conversation"
)

// 「从群聊中选择联系人」用例（图四群列表 + 图五群成员多选）。
//
// 与 ListGroupCandidates 同源：mutual 判定经 relationship gate 回填权威关系，
// 仅保留 mutual 且未屏蔽的联系人。两个用例共享一次 mutualContactIDSet 计算，
// 前端不再逐群多次拉成员求交集。

type SelectableGroupConversationRow struct {
	ConversationID    string `json:"conversationId"`
	Title             string `json:"title"`
	AvatarURL         string `json:"avatarUrl"`
	CircleID          string `json:"circleId"`
	FriendMemberCount int    `json:"friendMemberCount"`
	MemberCount       int    `json:"memberCount"`
}

type SelectableGroupContactMemberRow struct {
	ContactID     string `json:"contactId"`
	UserID        string `json:"userId"`
	DisplayName   string `json:"displayName"`
	AvatarURL     string `json:"avatarUrl"`
	RelationState string `json:"relationState"`
	Source        string `json:"source"`
}

type SelectableGroupConversationPage struct {
	Items      []SelectableGroupConversationRow `json:"items"`
	NextCursor string                           `json:"nextCursor,omitempty"`
}

type SelectableGroupContactMemberPage struct {
	Items      []SelectableGroupContactMemberRow `json:"items"`
	NextCursor string                            `json:"nextCursor,omitempty"`
}

const (
	selectableGroupPageLimit       = 50
	selectableGroupMemberPageLimit = 100
	selectableGroupScanBatchSize   = 100
	maxGroupSizeForCandidateScan   = 1000
)

// mutualContactIDSet 返回 viewer 的权威互关联系人 userId 集合（已排除屏蔽与自身）。
func (s *MemberService) mutualContactIDSet(
	ctx context.Context,
	userID string,
	limit int,
) (map[string]struct{}, error) {
	hits, err := s.combinedContactHitsWithMaxLimit(
		ctx,
		userID,
		"",
		limit,
		maxGroupSizeForCandidateScan,
	)
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
	source string,
	limit int,
	cursor string,
) (SelectableGroupConversationPage, error) {
	limit = clampLimit(limit, selectableGroupPageLimit, selectableGroupPageLimit)
	source = strings.TrimSpace(source)
	if source != "" && source != "group" && source != "circle" {
		return SelectableGroupConversationPage{}, rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"群聊来源无效",
			"selectable group source must be group or circle",
		)
	}
	rows := make([]SelectableGroupConversationRow, 0, limit)

	mutual, err := s.mutualContactIDSet(ctx, userID, maxGroupSizeForCandidateScan)
	if err != nil {
		return SelectableGroupConversationPage{}, err
	}
	if len(mutual) == 0 {
		return SelectableGroupConversationPage{Items: rows}, nil
	}

	viewer := strings.TrimSpace(userID)
	normalizedQuery := normalizeSearchQuery(query)

	for {
		states, err := s.userStates.ListUserStatesByConversationID(
			ctx,
			userID,
			selectableGroupScanBatchSize,
			cursor,
		)
		if err != nil {
			return SelectableGroupConversationPage{}, err
		}
		if len(states) == 0 {
			return SelectableGroupConversationPage{Items: rows}, nil
		}
		ids := make([]string, 0, len(states))
		for _, state := range states {
			ids = append(ids, state.ConversationId)
		}
		conversations, err := s.conversations.FindConversationsByIDs(ctx, ids)
		if err != nil {
			return SelectableGroupConversationPage{}, err
		}
		byID := make(map[string]model.Conversation, len(conversations))
		for _, conversation := range conversations {
			byID[conversation.ID] = conversation
		}

		for _, state := range states {
			cursor = state.ConversationId
			conv, found := byID[state.ConversationId]
			if !found ||
				conv.Type != "group" ||
				(conv.Status != "" && conv.Status != "active") {
				continue
			}
			circleID := strings.TrimSpace(conv.CircleId)
			if (source == "group" && circleID != "") ||
				(source == "circle" && circleID == "") {
				continue
			}
			if normalizedQuery != "" &&
				!strings.Contains(strings.ToLower(conv.Title), normalizedQuery) {
				continue
			}
			members, err := s.members.ListMembers(ctx, conv.ID, ListMembersQuery{
				Limit: maxGroupSizeForCandidateScan,
				Sort:  MemberListSortJoinedAsc,
			})
			if err != nil {
				return SelectableGroupConversationPage{}, err
			}
			friendCount := countMutualMembers(members, mutual, viewer)
			if friendCount == 0 {
				continue
			}
			rows = append(rows, SelectableGroupConversationRow{
				ConversationID:    conv.ID,
				Title:             conv.Title,
				AvatarURL:         conv.AvatarUrl,
				CircleID:          circleID,
				FriendMemberCount: friendCount,
				MemberCount:       conv.MemberCount,
			})
			if len(rows) == limit {
				return SelectableGroupConversationPage{
					Items:      rows,
					NextCursor: cursor,
				}, nil
			}
		}
		if len(states) < selectableGroupScanBatchSize {
			return SelectableGroupConversationPage{Items: rows}, nil
		}
	}
}

// ListSelectableGroupContactMembers 返回指定群成员中与当前用户互关的联系人。
// 排除当前用户、非 user 成员与已屏蔽关系；行形状复用联系人行（ChatContactListRow）。
func (s *MemberService) ListSelectableGroupContactMembers(
	ctx context.Context,
	userID string,
	conversationID string,
	query string,
	limit int,
	cursor string,
) (SelectableGroupContactMemberPage, error) {
	limit = clampLimit(
		limit,
		selectableGroupMemberPageLimit,
		selectableGroupMemberPageLimit,
	)
	conversationID = strings.TrimSpace(conversationID)
	if conversationID == "" {
		return SelectableGroupContactMemberPage{}, rterr.NewInvalidArgument(rterr.ModuleChat, "缺少会话标识", "conversationId is required")
	}

	conv, err := s.conversations.FindConversationByID(ctx, conversationID)
	if err != nil {
		if errors.Is(err, model.ErrConversationNotFound) {
			return SelectableGroupContactMemberPage{}, generated.AppErrorFromConversationNotFound("conversation not found: " + conversationID)
		}
		return SelectableGroupContactMemberPage{}, err
	}
	if conv == nil {
		return SelectableGroupContactMemberPage{}, generated.AppErrorFromConversationNotFound("conversation not found: " + conversationID)
	}
	if _, err := s.members.FindMember(ctx, conversationID, userID); err != nil {
		if errors.Is(err, model.ErrMemberNotFound) {
			return SelectableGroupContactMemberPage{}, generated.AppErrorFromConversationNotFound("viewer is not a conversation member")
		}
		return SelectableGroupContactMemberPage{}, err
	}

	mutual, err := s.mutualContactIDSet(ctx, userID, maxGroupSizeForCandidateScan)
	if err != nil {
		return SelectableGroupContactMemberPage{}, err
	}

	viewer := strings.TrimSpace(userID)
	normalizedQuery := normalizeSearchQuery(query)
	items := make([]SelectableGroupContactMemberRow, 0, limit)
	seen := map[string]struct{}{}

	for {
		members, err := s.members.ListMembers(ctx, conversationID, ListMembersQuery{
			Limit:  selectableGroupScanBatchSize,
			Cursor: cursor,
			Query:  normalizedQuery,
			Sort:   MemberListSortDisplayNameAsc,
		})
		if err != nil {
			return SelectableGroupContactMemberPage{}, err
		}
		if len(members) == 0 {
			return SelectableGroupContactMemberPage{Items: items}, nil
		}
		for _, member := range members {
			cursor = EncodeMemberListNextCursorDisplayName(
				member.DisplayName,
				member.UserId,
			)
			id := strings.TrimSpace(member.UserId)
			if id == "" || id == viewer {
				continue
			}
			if member.MemberType != "" && member.MemberType != "user" {
				continue
			}
			if _, ok := mutual[id]; !ok {
				continue
			}
			if _, ok := seen[id]; ok {
				continue
			}
			seen[id] = struct{}{}
			items = append(items, SelectableGroupContactMemberRow{
				ContactID:     id,
				UserID:        id,
				DisplayName:   member.DisplayName,
				AvatarURL:     member.AvatarUrl,
				RelationState: "mutual",
				Source:        "group",
			})
			if len(items) == limit {
				return SelectableGroupContactMemberPage{
					Items:      items,
					NextCursor: cursor,
				}, nil
			}
		}
		if len(members) < selectableGroupScanBatchSize {
			return SelectableGroupContactMemberPage{Items: items}, nil
		}
	}
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
