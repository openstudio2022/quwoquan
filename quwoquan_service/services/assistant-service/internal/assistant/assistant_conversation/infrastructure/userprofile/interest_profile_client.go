// Package userprofile implements the assistant ProactiveInterestReader port by
// calling user-service's GET /users/{userId}/interest-profile. It is the only
// assistant egress to the user domain (assistant and user are always separate
// workloads, as derived from per-environment runtime and deployment directories), so reads must go
// over HTTP rather than in-process.
package userprofile

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
)

// Client reads derived interest profiles from user-service for proactive
// personalization. It implements application.ProactiveInterestReader.
type Client struct {
	baseURL string
	http    *http.Client
}

// NewClient builds a reader bound to user-service baseURL using the provided
// egress http client (timeout + circuit breaker configured by the caller).
func NewClient(httpClient *http.Client, baseURL string) *Client {
	return &Client{
		baseURL: strings.TrimRight(strings.TrimSpace(baseURL), "/"),
		http:    httpClient,
	}
}

// interestProfileResponse mirrors user_profile/operations.yaml GetUserInterestProfile
// response_fields (the single contract source). Field names are the API's JSON
// keys; unknown fields are ignored.
type interestProfileResponse struct {
	UserID         string              `json:"userId"`
	TopInterests   []topInterest       `json:"topInterests"`
	DimensionTops  map[string][]string `json:"dimensionTops"`
	LifecycleStage string              `json:"lifecycleStage"`
	FreshnessDays  int                 `json:"freshnessDays"`
	Segments       []string            `json:"segments"`
}

type topInterest struct {
	TagRef    string  `json:"tagRef"`
	Dimension string  `json:"dimension"`
	Score     float64 `json:"score"`
	Level     int     `json:"level"`
}

// GetInterestProfile fetches and maps the user's derived interest profile.
// A nil profile (nil error) is returned when the reader is not configured
// (empty base url / nil client) or userID is blank, so callers degrade to
// non-personalized output without special-casing.
func (c *Client) GetInterestProfile(ctx context.Context, userID string) (*application.ProactiveInterestProfile, error) {
	userID = strings.TrimSpace(userID)
	if c == nil || c.http == nil || c.baseURL == "" || userID == "" {
		return nil, nil
	}
	endpoint := c.baseURL + "/users/" + url.PathEscape(userID) + "/interest-profile"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("interest profile build request: %w", err)
	}
	// Internal trust header for attribution; the permissive auth middleware
	// passes service-to-service calls (no bearer) through to the handler.
	req.Header.Set("X-Client-User-Id", userID)
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("interest profile request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("interest profile status %d", resp.StatusCode)
	}
	var payload interestProfileResponse
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return nil, fmt.Errorf("interest profile decode: %w", err)
	}
	return mapProfile(payload), nil
}

func mapProfile(payload interestProfileResponse) *application.ProactiveInterestProfile {
	interests := make([]application.ProactiveInterest, 0, len(payload.TopInterests))
	for _, it := range payload.TopInterests {
		interests = append(interests, application.ProactiveInterest{
			TagRef:    it.TagRef,
			Dimension: it.Dimension,
			Score:     it.Score,
			Level:     it.Level,
		})
	}
	return &application.ProactiveInterestProfile{
		TopInterests:   interests,
		DimensionTops:  payload.DimensionTops,
		LifecycleStage: payload.LifecycleStage,
		FreshnessDays:  payload.FreshnessDays,
		Segments:       payload.Segments,
	}
}
