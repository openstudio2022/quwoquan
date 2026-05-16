package application

import (
	"context"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/rtc-service/internal/infrastructure/livekit"
)

type RoomService struct {
	adapter livekit.RoomAdapter
}

func NewRoomService(adapter livekit.RoomAdapter) *RoomService {
	return &RoomService{adapter: adapter}
}

func (s *RoomService) CreateRoom(ctx context.Context, roomName string, maxParticipants int) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "rtc.CreateRoom",
		attribute.String("room.name", roomName),
		attribute.Int("room.max_participants", maxParticipants))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.adapter.CreateRoom(ctx, roomName, maxParticipants)
}

func (s *RoomService) DeleteRoom(ctx context.Context, roomName string) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "rtc.DeleteRoom",
		attribute.String("room.name", roomName))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.adapter.DeleteRoom(ctx, roomName)
}

func (s *RoomService) ListParticipants(ctx context.Context, roomName string) (_ []livekit.RoomParticipant, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "rtc.ListParticipants",
		attribute.String("room.name", roomName))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.adapter.ListParticipants(ctx, roomName)
}

func (s *RoomService) RemoveParticipant(ctx context.Context, roomName string, identity string) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "rtc.RemoveParticipant",
		attribute.String("room.name", roomName),
		attribute.String("participant.identity", identity))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.adapter.RemoveParticipant(ctx, roomName, identity)
}

func (s *RoomService) StartRecordingEgress(ctx context.Context, roomName, outputBucket string) (_ string, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "rtc.StartRecordingEgress",
		attribute.String("room.name", roomName),
		attribute.String("egress.bucket", outputBucket))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.adapter.StartRoomCompositeEgress(ctx, roomName, outputBucket)
}

func (s *RoomService) StopRecordingEgress(ctx context.Context, egressID string) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "rtc.StopRecordingEgress",
		attribute.String("egress.id", egressID))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.adapter.StopEgress(ctx, egressID)
}
