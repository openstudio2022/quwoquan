package application

import (
	"context"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
)

type RoomService struct {
	manager RoomManager
}

func NewRoomService(manager RoomManager) *RoomService {
	return &RoomService{manager: manager}
}

func (s *RoomService) CreateRoom(ctx context.Context, roomName string, maxParticipants int) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "rtc.CreateRoom",
		attribute.String("room.name", roomName),
		attribute.Int("room.max_participants", maxParticipants))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.manager.CreateRoom(ctx, roomName, maxParticipants)
}

func (s *RoomService) DeleteRoom(ctx context.Context, roomName string) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "rtc.DeleteRoom",
		attribute.String("room.name", roomName))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.manager.DeleteRoom(ctx, roomName)
}

func (s *RoomService) ListParticipants(ctx context.Context, roomName string) (_ []RoomParticipant, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "rtc.ListParticipants",
		attribute.String("room.name", roomName))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.manager.ListParticipants(ctx, roomName)
}

func (s *RoomService) RemoveParticipant(ctx context.Context, roomName string, identity string) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "rtc.RemoveParticipant",
		attribute.String("room.name", roomName),
		attribute.String("participant.identity", identity))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.manager.RemoveParticipant(ctx, roomName, identity)
}
