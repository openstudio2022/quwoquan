package livekit

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// RoomAdapter abstracts LiveKit room management operations.
type RoomAdapter interface {
	CreateRoom(ctx context.Context, roomName string, maxParticipants int) error
	DeleteRoom(ctx context.Context, roomName string) error
	ListParticipants(ctx context.Context, roomName string) ([]RoomParticipant, error)
	RemoveParticipant(ctx context.Context, roomName string, identity string) error
	StartRoomCompositeEgress(ctx context.Context, roomName string, outputBucket string) (string, error)
	StopEgress(ctx context.Context, egressID string) error
}

type RoomParticipant struct {
	Identity string `json:"identity"`
	SID      string `json:"sid"`
	State    string `json:"state"`
}

// LiveKitRoomAdapter implements RoomAdapter via LiveKit's TWIRP HTTP API.
type LiveKitRoomAdapter struct {
	httpURL   string
	apiKey    string
	apiSecret string
	client    *http.Client
}

func NewLiveKitRoomAdapter(livekitURL, apiKey, apiSecret string) *LiveKitRoomAdapter {
	httpURL := livekitURL
	httpURL = strings.Replace(httpURL, "ws://", "http://", 1)
	httpURL = strings.Replace(httpURL, "wss://", "https://", 1)
	return &LiveKitRoomAdapter{
		httpURL:   httpURL,
		apiKey:    apiKey,
		apiSecret: apiSecret,
		client:    &http.Client{Timeout: 10 * time.Second},
	}
}

func (a *LiveKitRoomAdapter) CreateRoom(ctx context.Context, roomName string, maxParticipants int) error {
	body := map[string]any{
		"name":             roomName,
		"max_participants": maxParticipants,
		"empty_timeout":    300,
	}
	_, err := a.twirpCall(ctx, "/twirp/livekit.RoomService/CreateRoom", body)
	return err
}

func (a *LiveKitRoomAdapter) DeleteRoom(ctx context.Context, roomName string) error {
	body := map[string]any{"room": roomName}
	_, err := a.twirpCall(ctx, "/twirp/livekit.RoomService/DeleteRoom", body)
	return err
}

func (a *LiveKitRoomAdapter) ListParticipants(ctx context.Context, roomName string) ([]RoomParticipant, error) {
	body := map[string]any{"room": roomName}
	respBody, err := a.twirpCall(ctx, "/twirp/livekit.RoomService/ListParticipants", body)
	if err != nil {
		return nil, err
	}

	var result struct {
		Participants []struct {
			Identity string `json:"identity"`
			SID      string `json:"sid"`
			State    int    `json:"state"`
		} `json:"participants"`
	}
	if err := json.Unmarshal(respBody, &result); err != nil {
		return nil, fmt.Errorf("parse participants response: %w", err)
	}

	participants := make([]RoomParticipant, 0, len(result.Participants))
	for _, p := range result.Participants {
		state := "ACTIVE"
		if p.State == 1 {
			state = "JOINING"
		} else if p.State == 3 {
			state = "DISCONNECTED"
		}
		participants = append(participants, RoomParticipant{
			Identity: p.Identity,
			SID:      p.SID,
			State:    state,
		})
	}
	return participants, nil
}

func (a *LiveKitRoomAdapter) RemoveParticipant(ctx context.Context, roomName string, identity string) error {
	body := map[string]any{"room": roomName, "identity": identity}
	_, err := a.twirpCall(ctx, "/twirp/livekit.RoomService/RemoveParticipant", body)
	return err
}

func (a *LiveKitRoomAdapter) StartRoomCompositeEgress(ctx context.Context, roomName string, outputBucket string) (string, error) {
	body := map[string]any{
		"room_name": roomName,
		"file": map[string]any{
			"file_type": "MP4",
			"filepath":  fmt.Sprintf("recordings/%s/{room_name}-{time}.mp4", roomName),
			"s3": map[string]any{
				"bucket": outputBucket,
			},
		},
		"audio_only": false,
	}
	respBody, err := a.twirpCall(ctx, "/twirp/livekit.Egress/StartRoomCompositeEgress", body)
	if err != nil {
		return "", err
	}
	var result struct {
		EgressID string `json:"egress_id"`
	}
	if err := json.Unmarshal(respBody, &result); err != nil {
		return "", fmt.Errorf("parse egress response: %w", err)
	}
	return result.EgressID, nil
}

func (a *LiveKitRoomAdapter) StopEgress(ctx context.Context, egressID string) error {
	body := map[string]any{"egress_id": egressID}
	_, err := a.twirpCall(ctx, "/twirp/livekit.Egress/StopEgress", body)
	return err
}

func (a *LiveKitRoomAdapter) twirpCall(ctx context.Context, path string, body map[string]any) ([]byte, error) {
	payload, err := json.Marshal(body)
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	url := a.httpURL + path
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(payload))
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	token, err := GenerateAdminToken(a.apiKey, a.apiSecret, "")
	if err != nil {
		return nil, fmt.Errorf("generate admin token: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+token)

	resp, err := a.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("livekit request failed: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}

	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("livekit error %d: %s", resp.StatusCode, string(respBody))
	}
	return respBody, nil
}
