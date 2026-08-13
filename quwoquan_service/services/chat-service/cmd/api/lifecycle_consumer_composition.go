package bootstrap

import (
	"context"

	conversationapp "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
	messageapp "quwoquan_service/services/chat-service/internal/chat/message/application"
)

type circleGroupMembershipProjectionBackend struct {
	projector conversationapp.CircleGroupChatSyncProjector
}

func (backend circleGroupMembershipProjectionBackend) ProjectCircleGroupMembership(
	ctx context.Context,
	fact membershipapp.CircleGroupMembershipFact,
) error {
	return backend.projector.Apply(ctx, conversationapp.CircleGroupChatSourceEvent{
		EventID: fact.EventID, EventType: fact.EventType, GroupID: fact.GroupID,
		CircleID: fact.CircleID, Version: fact.Version, UserID: fact.UserID,
		Role: fact.Role, State: fact.State, OccurredAt: fact.OccurredAt,
	})
}

type circleGroupMembershipConsumerProjector struct {
	handler *membershipapp.CircleGroupMembershipProjectionHandler
}

func (projector circleGroupMembershipConsumerProjector) Apply(
	ctx context.Context,
	event conversationapp.CircleGroupChatSourceEvent,
) error {
	return projector.handler.Apply(ctx, membershipapp.CircleGroupMembershipFact{
		EventID: event.EventID, EventType: event.EventType, GroupID: event.GroupID,
		CircleID: event.CircleID, Version: event.Version, UserID: event.UserID,
		Role: event.Role, State: event.State, OccurredAt: event.OccurredAt,
	})
}

type rtcCallLogProjectionBackend struct {
	writer interface {
		AppendRtcCallLog(context.Context, conversationapp.RtcCallEndedFact) error
	}
}

func (backend rtcCallLogProjectionBackend) ProjectRtcCallLog(
	ctx context.Context,
	fact messageapp.RtcCallEndedFact,
) error {
	return backend.writer.AppendRtcCallLog(ctx, conversationapp.RtcCallEndedFact{
		EventID: fact.EventID, CallID: fact.CallID, CallType: fact.CallType,
		InitiatorID: fact.InitiatorID, ConversationID: fact.ConversationID,
		EndReason: fact.EndReason, DurationMs: fact.DurationMs,
		StartedAt: fact.StartedAt, EndedAt: fact.EndedAt,
	})
}

type rtcCallLogConsumerWriter struct{ handler *messageapp.RtcCallLogHandler }

func (writer rtcCallLogConsumerWriter) AppendRtcCallLog(
	ctx context.Context,
	fact conversationapp.RtcCallEndedFact,
) error {
	return writer.handler.AppendRtcCallLog(ctx, messageapp.RtcCallEndedFact{
		EventID: fact.EventID, CallID: fact.CallID, CallType: fact.CallType,
		InitiatorID: fact.InitiatorID, ConversationID: fact.ConversationID,
		EndReason: fact.EndReason, DurationMs: fact.DurationMs,
		StartedAt: fact.StartedAt, EndedAt: fact.EndedAt,
	})
}
