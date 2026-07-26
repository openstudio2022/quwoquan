package livekit

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"sync"

	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
)

// ProtocolFixtureAdapterID is the non-prod MediaTransportPort substitute.
const ProtocolFixtureAdapterID = "infra.livekit_protocol_fixture"

// ProtocolFixtureRoomAdapter implements MediaRoomProvider without a vendor SFU.
type ProtocolFixtureRoomAdapter struct {
	mu    sync.Mutex
	rooms map[string]map[string]application.RoomParticipant
}

func NewProtocolFixtureRoomAdapter() *ProtocolFixtureRoomAdapter {
	return &ProtocolFixtureRoomAdapter{rooms: map[string]map[string]application.RoomParticipant{}}
}

func (a *ProtocolFixtureRoomAdapter) CreateRoom(_ context.Context, roomName string, _ int) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	if _, ok := a.rooms[roomName]; !ok {
		a.rooms[roomName] = map[string]application.RoomParticipant{}
	}
	return nil
}

func (a *ProtocolFixtureRoomAdapter) DeleteRoom(_ context.Context, roomName string) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	delete(a.rooms, roomName)
	return nil
}

func (a *ProtocolFixtureRoomAdapter) ListParticipants(
	_ context.Context,
	roomName string,
) ([]application.RoomParticipant, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	participants, found := a.rooms[roomName]
	if !found {
		return nil, errors.New("fixture media room not found")
	}
	out := make([]application.RoomParticipant, 0, len(participants))
	for _, participant := range participants {
		out = append(out, participant)
	}
	return out, nil
}

func (a *ProtocolFixtureRoomAdapter) RemoveParticipant(
	_ context.Context,
	roomName string,
	identity string,
) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	if participants, ok := a.rooms[roomName]; ok {
		delete(participants, identity)
	}
	return nil
}

func (a *ProtocolFixtureRoomAdapter) IssueParticipantAccess(
	_ context.Context,
	roomName string,
	participantIdentity string,
) (application.MediaSessionAccess, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	participants, ok := a.rooms[roomName]
	if !ok {
		return application.MediaSessionAccess{},
			errors.New("fixture media room not found")
	}
	participants[participantIdentity] = application.RoomParticipant{
		Identity: participantIdentity,
		SID:      fmt.Sprintf("fixture-%s", participantIdentity),
	}
	digest := sha256.Sum256([]byte(roomName + ":" + participantIdentity))
	return application.MediaSessionAccess{
		AccessToken: "fixture-" + hex.EncodeToString(digest[:8]),
	}, nil
}
