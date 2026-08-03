package api_integration

import (
	"context"
	"errors"
	"strings"
	"time"

	inboxapp "quwoquan_service/services/chat-service/internal/chat/chat_inbox_view/application"
	conversationapp "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	membershipmodel "quwoquan_service/services/chat-service/internal/chat/conversation_membership/domain/model"
	membershippersistence "quwoquan_service/services/chat-service/internal/chat/conversation_membership/infrastructure/persistence"
	userstatemodel "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/domain/model"
	userstatepersistence "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/infrastructure/persistence"
)

type testInboxAggregateSource struct {
	source conversationapp.AggregateOutboxSource
}

func (source testInboxAggregateSource) ReadAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]inboxapp.Event, error) {
	events, err := source.source.ReadAggregateOutboxAfter(ctx, checkpoint, limit)
	if err != nil {
		return nil, err
	}
	result := make([]inboxapp.Event, 0, len(events))
	for _, event := range events {
		result = append(result, inboxapp.Event{
			ID: event.EventID, Type: event.EventType, ConversationID: event.ConversationID,
			ActorID: event.ActorID, Payload: event.Payload, Checkpoint: event.Checkpoint,
		})
	}
	return result, nil
}

type testInboxMessageSource struct {
	source conversationapp.MessageOutboxReader
}

func (source testInboxMessageSource) ReadAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]inboxapp.Event, error) {
	events, err := source.source.ReadMessageOutboxAfter(ctx, checkpoint, limit)
	if err != nil {
		return nil, err
	}
	result := make([]inboxapp.Event, 0, len(events))
	for _, event := range events {
		result = append(result, inboxapp.Event{
			ID: event.EventID, Type: event.EventType, ConversationID: event.ConversationID,
			ActorID: event.ActorID, Payload: event.Payload, Checkpoint: event.Checkpoint,
		})
	}
	return result, nil
}

type testInboxMembershipReader struct {
	store *membershippersistence.MongoStore
}

func (reader testInboxMembershipReader) ListPersonaIDs(ctx context.Context, conversationID string) ([]string, error) {
	members, err := reader.store.ListMembers(ctx, conversationID, membershipmodel.ListQuery{Limit: 1000})
	if err != nil {
		return nil, err
	}
	ids := make([]string, 0, len(members))
	for _, member := range members {
		if member.MemberType == "user" {
			ids = append(ids, member.UserId)
		}
	}
	return ids, nil
}

type testInboxStateAdvancer struct {
	store *userstatepersistence.MongoStore
}

func (advancer testInboxStateAdvancer) AdvanceUnread(
	ctx context.Context,
	identity inboxapp.Identity,
	eventSeq int64,
	unreadDelta int,
	mentionDelta int,
	occurredAt time.Time,
) error {
	return advancer.store.AdvanceInboxUnread(
		ctx, identity.UserID, identity.ConversationID,
		eventSeq, unreadDelta, mentionDelta, occurredAt,
	)
}

type testInboxSnapshotSource struct {
	conversations conversationReader
	states        *userstatepersistence.MongoStore
}

type testInboxProjectionReader struct{ reader *inboxapp.Reader }

func newTestInboxService() *conversationapp.InboxService {
	return conversationapp.NewInboxService(testInboxProjectionReader{
		reader: inboxapp.NewReader(testInboxViewStore),
	})
}

func (reader testInboxProjectionReader) ListInboxPage(
	ctx context.Context,
	request conversationapp.ListInboxRequest,
) (conversationapp.InboxPage, error) {
	page, err := reader.reader.List(ctx, request.UserId, request.Limit, request.Cursor)
	if err != nil {
		return conversationapp.InboxPage{}, err
	}
	items := make([]conversationapp.InboxItem, 0, len(page.Items))
	for _, item := range page.Items {
		items = append(items, conversationapp.InboxItem{
			Conversation: conversationmodel.Conversation{
				ID: item.ConversationID, Type: item.Type, Title: item.Title,
				AvatarUrl: item.AvatarURL, GroupAvatarVersion: item.GroupAvatarVersion,
				CircleId: item.CircleID, LastMessageId: item.LastMessageID,
				LastMessagePreview: item.LastMessagePreview, LastMessageType: item.LastMessageType,
				LastMessageTime: item.LastMessageTime, MaxSeq: item.LastSeq,
				Status:    conversationmodel.ConversationStatusActive,
				UpdatedAt: item.ConversationUpdated,
			},
			UserState: userstatemodel.State{
				UserId: item.UserID, ConversationId: item.ConversationID,
				UnreadCount: item.UnreadCount, MentionUnreadCount: item.MentionUnreadCount,
				ReadSeq: item.ReadSeq, InboxProjectedSeq: item.InboxProjectedSeq,
				Muted: item.Muted, Pinned: item.Pinned, UpdatedAt: item.StateUpdated,
				LastReadAt: item.LastReadAt,
			},
		})
	}
	return conversationapp.InboxPage{Items: items, NextCursor: page.NextCursor}, nil
}

type conversationReader interface {
	FindConversationByID(context.Context, string) (*conversationmodel.Conversation, error)
}

func (source testInboxSnapshotSource) Load(ctx context.Context, identity inboxapp.Identity) (inboxapp.Item, bool, error) {
	state, err := source.states.FindUserState(ctx, identity.UserID, identity.ConversationID)
	if errors.Is(err, userstatemodel.ErrNotFound) {
		return inboxapp.Item{}, false, nil
	}
	if err != nil {
		return inboxapp.Item{}, false, err
	}
	conversation, err := source.conversations.FindConversationByID(ctx, identity.ConversationID)
	if errors.Is(err, conversationmodel.ErrConversationNotFound) {
		return inboxapp.Item{}, false, nil
	}
	if err != nil {
		return inboxapp.Item{}, false, err
	}
	if conversation.Status != "" && conversation.Status != conversationmodel.ConversationStatusActive {
		return inboxapp.Item{}, false, nil
	}
	return inboxapp.Item{
		UserID: state.UserId, ConversationID: conversation.ID,
		Type: conversation.Type, Title: conversation.Title, AvatarURL: conversation.AvatarUrl,
		GroupAvatarVersion: conversation.GroupAvatarVersion, LastMessageID: conversation.LastMessageId,
		LastMessagePreview: conversation.LastMessagePreview, LastMessageType: conversation.LastMessageType,
		LastMessageTime: conversation.LastMessageTime, LastSeq: conversation.MaxSeq,
		ReadSeq: state.ReadSeq, InboxProjectedSeq: state.InboxProjectedSeq,
		UnreadCount: state.UnreadCount, MentionUnreadCount: state.MentionUnreadCount,
		Muted: state.Muted, Pinned: state.Pinned, CircleID: strings.TrimSpace(conversation.CircleId),
		ConversationUpdated: conversation.UpdatedAt, StateUpdated: state.UpdatedAt,
		LastReadAt: state.LastReadAt,
	}, true, nil
}

func (source testInboxSnapshotSource) ListIdentities(
	ctx context.Context,
	afterID string,
	limit int,
) ([]inboxapp.Identity, string, error) {
	states, next, err := source.states.ListIdentities(ctx, afterID, limit)
	if err != nil {
		return nil, "", err
	}
	identities := make([]inboxapp.Identity, 0, len(states))
	for _, state := range states {
		identities = append(identities, inboxapp.Identity{UserID: state.UserId, ConversationID: state.ConversationId})
	}
	return identities, next, nil
}
