package application

import (
	"context"

	"quwoquan_service/services/rtc-service/internal/infrastructure/livekit"
)

type RoomService struct {
	adapter livekit.RoomAdapter
}

func NewRoomService(adapter livekit.RoomAdapter) *RoomService {
	return &RoomService{adapter: adapter}
}

func (s *RoomService) CreateRoom(ctx context.Context, roomName string, maxParticipants int) error {
	return s.adapter.CreateRoom(ctx, roomName, maxParticipants)
}

func (s *RoomService) DeleteRoom(ctx context.Context, roomName string) error {
	return s.adapter.DeleteRoom(ctx, roomName)
}

func (s *RoomService) ListParticipants(ctx context.Context, roomName string) ([]livekit.RoomParticipant, error) {
	return s.adapter.ListParticipants(ctx, roomName)
}

func (s *RoomService) RemoveParticipant(ctx context.Context, roomName string, identity string) error {
	return s.adapter.RemoveParticipant(ctx, roomName, identity)
}

func (s *RoomService) StartRecordingEgress(ctx context.Context, roomName, outputBucket string) (string, error) {
	return s.adapter.StartRoomCompositeEgress(ctx, roomName, outputBucket)
}

func (s *RoomService) StopRecordingEgress(ctx context.Context, egressID string) error {
	return s.adapter.StopEgress(ctx, egressID)
}
