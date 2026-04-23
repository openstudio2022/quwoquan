package http

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"quwoquan_service/services/chat-service/internal/application"
)

type UserProfileResolver struct {
	baseURL string
	client  *http.Client
}

type userProfileSnapshotResponse struct {
	Profile struct {
		Nickname      string `json:"nickname"`
		AvatarURL     string `json:"avatarUrl"`
		AvatarAssetID string `json:"avatarAssetId"`
		AvatarVersion int    `json:"avatarVersion"`
	} `json:"profile"`
	ActivePersona *struct {
		DisplayName string `json:"displayName"`
		AvatarURL   string `json:"avatarUrl"`
	} `json:"activePersona,omitempty"`
}

func NewUserProfileResolver(baseURL string, client *http.Client) *UserProfileResolver {
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if client == nil {
		client = &http.Client{Timeout: 2 * time.Second}
	}
	return &UserProfileResolver{
		baseURL: baseURL,
		client:  client,
	}
}

func (r *UserProfileResolver) ResolveMany(
	ctx context.Context,
	userIDs []string,
) (map[string]application.ProfileSnapshot, error) {
	result := make(map[string]application.ProfileSnapshot, len(userIDs))
	if r == nil || r.client == nil || r.baseURL == "" {
		return result, nil
	}
	for _, rawUserID := range userIDs {
		userID := strings.TrimSpace(rawUserID)
		if userID == "" {
			continue
		}
		snapshot, err := r.resolveOne(ctx, userID)
		if err != nil {
			return nil, err
		}
		result[userID] = snapshot
	}
	return result, nil
}

func (r *UserProfileResolver) resolveOne(
	ctx context.Context,
	userID string,
) (application.ProfileSnapshot, error) {
	requestURL := fmt.Sprintf("%s/v1/user/profile/%s", r.baseURL, url.PathEscape(userID))
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, requestURL, nil)
	if err != nil {
		return application.ProfileSnapshot{}, err
	}
	resp, err := r.client.Do(req)
	if err != nil {
		return application.ProfileSnapshot{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound {
		return application.ProfileSnapshot{}, nil
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return application.ProfileSnapshot{}, fmt.Errorf("get user profile %s: status %d", userID, resp.StatusCode)
	}

	var payload userProfileSnapshotResponse
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return application.ProfileSnapshot{}, err
	}

	displayName := strings.TrimSpace(payload.Profile.Nickname)
	avatarURL := strings.TrimSpace(payload.Profile.AvatarURL)
	if payload.ActivePersona != nil {
		if text := strings.TrimSpace(payload.ActivePersona.DisplayName); text != "" {
			displayName = text
		}
		if text := strings.TrimSpace(payload.ActivePersona.AvatarURL); text != "" {
			avatarURL = text
		}
	}
	return application.ProfileSnapshot{
		DisplayName:   displayName,
		AvatarURL:     avatarURL,
		AvatarAssetID: strings.TrimSpace(payload.Profile.AvatarAssetID),
		AvatarVersion: payload.Profile.AvatarVersion,
	}, nil
}
