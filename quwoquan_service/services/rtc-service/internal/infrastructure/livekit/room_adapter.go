package livekit

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"quwoquan_service/services/rtc-service/internal/application"
)

const AdapterID = "infra.livekit_sfu"

var _ application.MediaRoomProvider = (*LiveKitRoomAdapter)(nil)

// LiveKitRoomAdapter 通过 LiveKit TWIRP API 实现中立媒体房间端口。
type LiveKitRoomAdapter struct {
	connectionURL string
	httpURL       string
	apiKey        string
	apiSecret     string
	client        *http.Client
}

func NewLiveKitRoomAdapter(connectionURL, apiKey, apiSecret string, opts ...func(*LiveKitRoomAdapter)) *LiveKitRoomAdapter {
	httpURL := connectionURL
	httpURL = strings.Replace(httpURL, "ws://", "http://", 1)
	httpURL = strings.Replace(httpURL, "wss://", "https://", 1)
	a := &LiveKitRoomAdapter{
		connectionURL: strings.TrimSpace(connectionURL),
		httpURL:       httpURL,
		apiKey:        apiKey,
		apiSecret:     apiSecret,
		client:        &http.Client{Timeout: 10 * time.Second},
	}
	for _, opt := range opts {
		opt(a)
	}
	return a
}

// WithHTTPClient replaces the default HTTP client (e.g. for CB wrapping).
func WithHTTPClient(c *http.Client) func(*LiveKitRoomAdapter) {
	return func(a *LiveKitRoomAdapter) { a.client = c }
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

func (a *LiveKitRoomAdapter) ListParticipants(ctx context.Context, roomName string) ([]application.RoomParticipant, error) {
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

	participants := make([]application.RoomParticipant, 0, len(result.Participants))
	for _, p := range result.Participants {
		state := "ACTIVE"
		if p.State == 1 {
			state = "JOINING"
		} else if p.State == 3 {
			state = "DISCONNECTED"
		}
		participants = append(participants, application.RoomParticipant{
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

func (a *LiveKitRoomAdapter) IssueParticipantAccess(
	_ context.Context,
	roomName string,
	participantIdentity string,
) (application.MediaSessionAccess, error) {
	token, err := GenerateAccessToken(
		a.apiKey,
		a.apiSecret,
		roomName,
		participantIdentity,
		6*time.Hour,
	)
	if err != nil {
		return application.MediaSessionAccess{}, fmt.Errorf("generate participant access: %w", err)
	}
	return application.MediaSessionAccess{
		AccessToken: token,
	}, nil
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
		bodyDigest := sha256.Sum256(respBody)
		return nil, fmt.Errorf(
			"livekit request rejected: status=%d body_bytes=%d body_digest=%x",
			resp.StatusCode,
			len(respBody),
			bodyDigest[:8],
		)
	}
	return respBody, nil
}
