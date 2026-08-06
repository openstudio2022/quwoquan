package external

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	gatheringapp "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
)

const (
	defaultGatheringSafetyAuthorityTimeout = 750 * time.Millisecond
	maxGatheringSafetyIdentityLength       = 64
	maxGatheringSafetyReferenceLength      = 192
)

type HTTPSafetyTerminationAuthorizer struct {
	baseURL     *url.URL
	credentials rtauth.ServiceAuthorizationProvider
	client      *http.Client
	now         func() time.Time
}

type safetyTerminationAuthorityRequest struct {
	ActorPersonaID string `json:"actorPersonaId"`
	GatheringID    string `json:"gatheringId"`
	Action         string `json:"action"`
	EvidenceRef    string `json:"evidenceRef"`
	DecisionRef    string `json:"decisionRef"`
}

type safetyTerminationAuthorityResponse struct {
	Allowed         bool       `json:"allowed"`
	ActorPersonaID  string     `json:"actorPersonaId"`
	GatheringID     string     `json:"gatheringId"`
	Action          string     `json:"action"`
	EvidenceRef     string     `json:"evidenceRef"`
	DecisionRef     string     `json:"decisionRef"`
	DecisionVersion int64      `json:"decisionVersion"`
	DecisionDigest  string     `json:"decisionDigest"`
	ExpiresAt       *time.Time `json:"expiresAt"`
	RevokedAt       *time.Time `json:"revokedAt"`
}

func NewHTTPSafetyTerminationAuthorizer(
	rawBaseURL string,
	credentials rtauth.ServiceAuthorizationProvider,
	client *http.Client,
) (*HTTPSafetyTerminationAuthorizer, error) {
	baseURL, err := requireHTTPBaseURL("CONTENT_SERVICE_BASE_URL", rawBaseURL)
	if err != nil {
		return nil, err
	}
	if credentials == nil {
		return nil, fmt.Errorf("Gathering safety authority requires service authorization")
	}
	if client == nil {
		client = &http.Client{Timeout: defaultGatheringSafetyAuthorityTimeout}
	}
	return &HTTPSafetyTerminationAuthorizer{
		baseURL: baseURL, credentials: credentials, client: client, now: time.Now,
	}, nil
}

func (authorizer *HTTPSafetyTerminationAuthorizer) AuthorizeSafetyTermination(
	ctx context.Context,
	request gatheringapp.GatheringSafetyTerminationAuthorizationRequest,
) error {
	request.ActorPersonaID = strings.TrimSpace(request.ActorPersonaID)
	request.GatheringID = strings.TrimSpace(request.GatheringID)
	request.Action = strings.TrimSpace(request.Action)
	request.EvidenceRef = strings.TrimSpace(request.EvidenceRef)
	request.DecisionRef = strings.TrimSpace(request.DecisionRef)
	if request.ActorPersonaID == "" ||
		len(request.ActorPersonaID) > maxGatheringSafetyIdentityLength ||
		request.GatheringID == "" ||
		len(request.GatheringID) > maxGatheringSafetyIdentityLength ||
		request.Action != gatheringapp.GatheringSafetyTerminationAction ||
		request.EvidenceRef == "" ||
		len(request.EvidenceRef) > maxGatheringSafetyReferenceLength ||
		request.DecisionRef == "" ||
		len(request.DecisionRef) > maxGatheringSafetyReferenceLength ||
		request.ExpectedGatheringVersion < 1 {
		return gatheringerrors.ErrGatheringSafetyTerminationDenied
	}
	body, err := json.Marshal(safetyTerminationAuthorityRequest{
		ActorPersonaID: request.ActorPersonaID,
		GatheringID:    request.GatheringID,
		Action:         request.Action,
		EvidenceRef:    request.EvidenceRef,
		DecisionRef:    request.DecisionRef,
	})
	if err != nil {
		return gatheringerrors.ErrGatheringSafetyTerminationDenied
	}
	endpoint := *authorizer.baseURL
	endpoint.Path = strings.TrimRight(endpoint.Path, "/") +
		"/internal/content/gathering-safety-termination:authorize"
	httpRequest, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		endpoint.String(),
		bytes.NewReader(body),
	)
	if err != nil {
		return gatheringerrors.ErrGatheringSafetyAuthorityUnavailable
	}
	authorization, err := authorizer.credentials.AuthorizationHeader(ctx)
	if err != nil {
		return gatheringerrors.ErrGatheringSafetyAuthorityUnavailable
	}
	httpRequest.Header.Set("Authorization", authorization)
	httpRequest.Header.Set("Content-Type", "application/json")
	httpRequest.Header.Set("Accept", "application/json")
	response, err := authorizer.client.Do(httpRequest)
	if err != nil {
		return gatheringerrors.ErrGatheringSafetyAuthorityUnavailable
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
		return gatheringerrors.ErrGatheringSafetyAuthorityUnavailable
	}
	var payload safetyTerminationAuthorityResponse
	decoder := json.NewDecoder(io.LimitReader(response.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		return gatheringerrors.ErrGatheringSafetyAuthorityUnavailable
	}
	if !payload.Allowed {
		return gatheringerrors.ErrGatheringSafetyTerminationDenied
	}
	if strings.TrimSpace(payload.ActorPersonaID) != request.ActorPersonaID ||
		strings.TrimSpace(payload.GatheringID) != request.GatheringID ||
		strings.TrimSpace(payload.Action) != request.Action ||
		strings.TrimSpace(payload.EvidenceRef) != request.EvidenceRef ||
		strings.TrimSpace(payload.DecisionRef) != request.DecisionRef ||
		payload.DecisionVersion < 1 ||
		!validSafetyDecisionDigest(payload.DecisionDigest) ||
		payload.ExpiresAt == nil ||
		!authorizer.now().UTC().Before(payload.ExpiresAt.UTC()) ||
		payload.RevokedAt != nil {
		return gatheringerrors.ErrGatheringSafetyTerminationDenied
	}
	return nil
}

func validSafetyDecisionDigest(raw string) bool {
	raw = strings.TrimSpace(raw)
	decoded, err := hex.DecodeString(raw)
	return err == nil && len(decoded) == sha256DigestLength
}

const sha256DigestLength = 32

var _ gatheringapp.GatheringSafetyTerminationAuthorizer = (*HTTPSafetyTerminationAuthorizer)(nil)
