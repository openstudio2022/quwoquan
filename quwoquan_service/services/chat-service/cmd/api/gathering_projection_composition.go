package main

import (
	"context"
	"errors"
	"time"

	conversationapp "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
	userstatemodel "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/domain/model"
)

type gatheringBindingReader struct {
	reader conversationapp.GatheringConversationReader
}

func (reader gatheringBindingReader) ReadGatheringConversation(
	ctx context.Context,
	gatheringID string,
) (membershipapp.GatheringBinding, bool, error) {
	conversation, err := reader.reader.FindConversationByGatheringID(ctx, gatheringID)
	if errors.Is(err, conversationmodel.ErrConversationNotFound) {
		return membershipapp.GatheringBinding{}, false, nil
	}
	if err != nil {
		return membershipapp.GatheringBinding{}, false, err
	}
	return membershipapp.GatheringBinding{
		GatheringID: conversation.GatheringId, ConversationID: conversation.ID,
		Active: conversation.Status == conversationmodel.ConversationStatusActive,
	}, true, nil
}

type gatheringUserStateWriter struct {
	states conversationapp.UserStateStore
}

func (writer gatheringUserStateWriter) EnsureGatheringUserState(
	ctx context.Context,
	personaID string,
	conversationID string,
	occurredAt time.Time,
) error {
	return writer.states.UpsertUserState(ctx, &userstatemodel.State{
		ID:     "gathering:" + conversationID + ":" + personaID,
		UserId: personaID, ConversationId: conversationID, UpdatedAt: occurredAt.UTC(),
	})
}

func (writer gatheringUserStateWriter) DeleteGatheringUserState(
	ctx context.Context,
	personaID string,
	conversationID string,
) error {
	return writer.states.DeleteUserState(ctx, personaID, conversationID)
}

type gatheringRosterWriter struct {
	roster conversationapp.ConversationRosterProjector
}

func (writer gatheringRosterWriter) BumpGatheringRoster(
	ctx context.Context,
	conversationID string,
	memberCount int,
) error {
	return writer.roster.BumpMembersRosterRevision(ctx, conversationID, &memberCount)
}

type gatheringProfileReader struct {
	profiles conversationapp.ProfileSnapshotResolver
}

func (reader gatheringProfileReader) ReadGatheringMemberProfile(
	ctx context.Context,
	personaID string,
) (membershipapp.GatheringMemberProfile, error) {
	profiles, err := reader.profiles.ResolveMany(ctx, []string{personaID})
	if err != nil {
		return membershipapp.GatheringMemberProfile{}, err
	}
	profile := profiles[personaID]
	return membershipapp.GatheringMemberProfile{
		UserHandle: profile.UserHandle, DisplayName: profile.DisplayName,
		AvatarURL: profile.AvatarURL, AvatarAssetID: profile.AvatarAssetID,
		AvatarVersion: int64(profile.AvatarVersion),
	}, nil
}

type gatheringProjectionOutbox struct {
	members       conversationapp.AggregateCommandStore
	conversations conversationapp.AggregateCommandStore
}

func (outbox gatheringProjectionOutbox) AppendGatheringProjectionEvents(
	ctx context.Context,
	membershipEvents []membershipapp.GatheringOutboxEvent,
	conversationEvents []membershipapp.GatheringOutboxEvent,
) error {
	if err := outbox.members.AppendAggregateOutboxEvents(ctx, convertGatheringEvents(membershipEvents)); err != nil {
		return err
	}
	return outbox.conversations.AppendAggregateOutboxEvents(ctx, convertGatheringEvents(conversationEvents))
}

func convertGatheringEvents(events []membershipapp.GatheringOutboxEvent) []conversationapp.AggregateOutboxEvent {
	converted := make([]conversationapp.AggregateOutboxEvent, 0, len(events))
	for _, event := range events {
		converted = append(converted, conversationapp.AggregateOutboxEvent{
			EventID: event.EventID, EventType: event.EventType, AggregateID: event.AggregateID,
			ConversationID: event.ConversationID, ActorID: event.ActorID, Payload: event.Payload,
		})
	}
	return converted
}
