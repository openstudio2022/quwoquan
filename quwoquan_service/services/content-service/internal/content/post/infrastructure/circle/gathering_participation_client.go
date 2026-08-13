// Package circle is the Content-side anti-corruption boundary to the Circle
// owner. It only consumes Circle's public/internal typed contracts through the
// shared generated service clients; it never imports circle-service internals.
package circle

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	sharedclients "quwoquan_service/generated/serviceclients"
	rtauth "quwoquan_service/runtime/auth"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

const participationStatusReadTimeout = 500 * time.Millisecond

// GatheringParticipationClient is the only Content-side reader of Circle's
// Gathering participation status assertion. It answers exactly one question —
// "does this persona currently participate in this gathering" — and never
// caches, lists rosters or persists Circle facts. Failures surface as errors;
// the caller must treat them as fail-closed (unavailable is never allow).
type GatheringParticipationClient struct {
	baseURL     string
	httpClient  *http.Client
	credentials rtauth.ServiceAuthorizationProvider
}

func NewGatheringParticipationClient(
	baseURL string,
	credentials rtauth.ServiceAuthorizationProvider,
) (*GatheringParticipationClient, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("gathering participation reader: valid circle base URL is required")
	}
	if credentials == nil {
		return nil, fmt.Errorf("gathering participation reader: service credentials are required")
	}
	return &GatheringParticipationClient{
		baseURL:     strings.TrimRight(parsed.String(), "/"),
		httpClient:  &http.Client{},
		credentials: credentials,
	}, nil
}

func (client *GatheringParticipationClient) SetTransport(transport http.RoundTripper) {
	if transport == nil {
		transport = http.DefaultTransport
	}
	client.httpClient.Transport = transport
}

type participationStatusWire struct {
	GatheringID        string `json:"gatheringId"`
	PersonaID          string `json:"personaId"`
	LifecycleStatus    string `json:"lifecycleStatus"`
	ParticipationState string `json:"participationState,omitempty"`
}

func (client *GatheringParticipationClient) GetParticipationStatus(
	ctx context.Context,
	gatheringID string,
	personaID string,
) (postports.GatheringParticipationStatus, error) {
	normalizedGathering := strings.TrimSpace(gatheringID)
	normalizedPersona := strings.TrimSpace(personaID)
	if normalizedGathering == "" || normalizedPersona == "" {
		return postports.GatheringParticipationStatus{},
			fmt.Errorf("gathering participation query is invalid")
	}
	if client == nil || client.httpClient == nil || client.credentials == nil {
		return postports.GatheringParticipationStatus{},
			fmt.Errorf("gathering participation reader is not configured")
	}
	requestContext, cancel := context.WithTimeout(ctx, participationStatusReadTimeout)
	defer cancel()
	request, err := http.NewRequestWithContext(
		requestContext,
		http.MethodGet,
		client.baseURL+sharedclients.CircleGatheringGetGatheringParticipationStatusPath(
			normalizedGathering,
			normalizedPersona,
		),
		nil,
	)
	if err != nil {
		return postports.GatheringParticipationStatus{}, err
	}
	request.Header.Set("Accept", "application/json")
	authorization, err := client.credentials.AuthorizationHeader(requestContext)
	if err != nil {
		return postports.GatheringParticipationStatus{},
			fmt.Errorf("gathering participation authorization: %w", err)
	}
	request.Header.Set("Authorization", authorization)
	response, err := client.httpClient.Do(request)
	if err != nil {
		return postports.GatheringParticipationStatus{},
			fmt.Errorf("gathering participation request failed: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return postports.GatheringParticipationStatus{},
			fmt.Errorf("gathering participation status %d", response.StatusCode)
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, 64*1024))
	decoder.DisallowUnknownFields()
	var wire participationStatusWire
	if err := decoder.Decode(&wire); err != nil {
		return postports.GatheringParticipationStatus{},
			fmt.Errorf("decode gathering participation response: %w", err)
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return postports.GatheringParticipationStatus{},
			fmt.Errorf("gathering participation response has trailing payload")
	}
	if wire.GatheringID != normalizedGathering || wire.PersonaID != normalizedPersona {
		return postports.GatheringParticipationStatus{},
			fmt.Errorf("gathering participation response identity mismatch")
	}
	return postports.GatheringParticipationStatus{
		GatheringID:        wire.GatheringID,
		PersonaID:          wire.PersonaID,
		LifecycleStatus:    wire.LifecycleStatus,
		ParticipationState: wire.ParticipationState,
	}, nil
}

var _ postports.GatheringParticipationReader = (*GatheringParticipationClient)(nil)
