package external

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	shared "quwoquan_service/generated/serviceclients/hostauthority"
	rtauth "quwoquan_service/runtime/auth"
	runtimeauthority "quwoquan_service/runtime/hostauthority"
	gatheringcontract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	gatheringmodel "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

const defaultHostAuthorityTimeout = 800 * time.Millisecond

type ownerHostAuthorityHTTPClient struct {
	baseURL     *url.URL
	httpClient  *http.Client
	credentials rtauth.ServiceAuthorizationProvider
	encode      func(shared.EvaluationQuery) (shared.RequestPacket, error)
	decode      func(shared.ResponsePacket) (shared.Evidence, error)
}

type PersonaHostAuthorityHTTPClient struct {
	client *ownerHostAuthorityHTTPClient
}

type EntityHomepageHostAuthorityHTTPClient struct {
	client *ownerHostAuthorityHTTPClient
}

func NewPersonaHostAuthorityHTTPClient(
	rawBaseURL string,
	credentials rtauth.ServiceAuthorizationProvider,
	httpClient *http.Client,
) (*PersonaHostAuthorityHTTPClient, error) {
	client, err := newOwnerHostAuthorityHTTPClient(
		"USER_SERVICE_BASE_URL",
		rawBaseURL,
		credentials,
		httpClient,
		shared.EncodeEvaluatePersona,
		shared.DecodeEvaluatePersonaResponse,
	)
	if err != nil {
		return nil, err
	}
	return &PersonaHostAuthorityHTTPClient{client: client}, nil
}

func NewEntityHomepageHostAuthorityHTTPClient(
	rawBaseURL string,
	credentials rtauth.ServiceAuthorizationProvider,
	httpClient *http.Client,
) (*EntityHomepageHostAuthorityHTTPClient, error) {
	client, err := newOwnerHostAuthorityHTTPClient(
		"ENTITY_SERVICE_BASE_URL",
		rawBaseURL,
		credentials,
		httpClient,
		shared.EncodeEvaluateEntityHomepage,
		shared.DecodeEvaluateEntityHomepageResponse,
	)
	if err != nil {
		return nil, err
	}
	return &EntityHomepageHostAuthorityHTTPClient{client: client}, nil
}

func newOwnerHostAuthorityHTTPClient(
	configName string,
	rawBaseURL string,
	credentials rtauth.ServiceAuthorizationProvider,
	httpClient *http.Client,
	encode func(shared.EvaluationQuery) (shared.RequestPacket, error),
	decode func(shared.ResponsePacket) (shared.Evidence, error),
) (*ownerHostAuthorityHTTPClient, error) {
	baseURL, err := requireHTTPBaseURL(configName, rawBaseURL)
	if err != nil {
		return nil, err
	}
	if credentials == nil {
		return nil, fmt.Errorf("%s Host authority client requires service authorization", configName)
	}
	if httpClient == nil {
		httpClient = &http.Client{Timeout: defaultHostAuthorityTimeout}
	}
	return &ownerHostAuthorityHTTPClient{
		baseURL: baseURL, httpClient: httpClient, credentials: credentials,
		encode: encode, decode: decode,
	}, nil
}

func (client *PersonaHostAuthorityHTTPClient) EvaluatePersonaHostAuthority(
	ctx context.Context,
	query gatheringmodel.HostAuthorityQuery,
) (gatheringmodel.HostAuthorityEvidence, error) {
	return client.client.evaluate(ctx, query)
}

func (client *EntityHomepageHostAuthorityHTTPClient) EvaluateEntityHomepageHostAuthority(
	ctx context.Context,
	query gatheringmodel.HostAuthorityQuery,
) (gatheringmodel.HostAuthorityEvidence, error) {
	return client.client.evaluate(ctx, query)
}

func (client *ownerHostAuthorityHTTPClient) evaluate(
	ctx context.Context,
	query gatheringmodel.HostAuthorityQuery,
) (gatheringmodel.HostAuthorityEvidence, error) {
	packet, err := client.encode(toSharedAuthorityQuery(query))
	if err != nil {
		return gatheringmodel.HostAuthorityEvidence{}, err
	}
	target := *client.baseURL
	escapedPath := strings.TrimRight(target.EscapedPath(), "/") + packet.Path
	decodedPath, err := url.PathUnescape(escapedPath)
	if err != nil {
		return gatheringmodel.HostAuthorityEvidence{}, err
	}
	target.Path = decodedPath
	target.RawPath = escapedPath
	target.RawQuery = packet.Query.Encode()
	request, err := http.NewRequestWithContext(
		ctx,
		packet.Operation.Method,
		target.String(),
		bytes.NewReader(packet.CanonicalRequest),
	)
	if err != nil {
		return gatheringmodel.HostAuthorityEvidence{}, err
	}
	authorization, err := client.credentials.AuthorizationHeader(ctx)
	if err != nil {
		return gatheringmodel.HostAuthorityEvidence{}, err
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Content-Type", "application/json")
	response, err := client.httpClient.Do(request)
	if err != nil {
		return gatheringmodel.HostAuthorityEvidence{}, err
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 1<<20))
	if err != nil {
		return gatheringmodel.HostAuthorityEvidence{}, err
	}
	evidence, err := client.decode(shared.ResponsePacket{
		StatusCode: response.StatusCode,
		Body:       body,
	})
	if err != nil {
		return gatheringmodel.HostAuthorityEvidence{}, err
	}
	return fromSharedAuthorityEvidence(evidence), nil
}

type LocalCircleHostAuthorityEvaluator interface {
	Evaluate(context.Context, runtimeauthority.Query) (runtimeauthority.Evidence, error)
}

type LocalCircleHostAuthorityClient struct {
	evaluator LocalCircleHostAuthorityEvaluator
}

func NewLocalCircleHostAuthorityClient(
	evaluator LocalCircleHostAuthorityEvaluator,
) *LocalCircleHostAuthorityClient {
	if evaluator == nil {
		panic("local Circle Host authority client requires canonical evaluator")
	}
	return &LocalCircleHostAuthorityClient{evaluator: evaluator}
}

func (client *LocalCircleHostAuthorityClient) EvaluateCircleHostAuthority(
	ctx context.Context,
	query gatheringmodel.HostAuthorityQuery,
) (gatheringmodel.HostAuthorityEvidence, error) {
	evidence, err := client.evaluator.Evaluate(ctx, runtimeauthority.Query{
		HostSubjectKind:      string(query.HostSubjectKind),
		HostSubjectID:        strings.TrimSpace(query.HostSubjectID),
		HostSubjectRef:       authorityHostReference(query),
		ActorPersonaID:       strings.TrimSpace(query.ActorPersonaID),
		OrganizerPersonaID:   strings.TrimSpace(query.OrganizerPersonaID),
		AuthorityEvidenceRef: strings.TrimSpace(query.AuthorityEvidenceRef),
		AuthorityVersion:     query.AuthorityVersion,
		Action:               string(query.Action),
	})
	if err != nil {
		return gatheringmodel.HostAuthorityEvidence{}, err
	}
	return gatheringmodel.HostAuthorityEvidence{
		HostSubjectKind:      query.HostSubjectKind,
		HostSubjectID:        evidence.HostSubjectID,
		HostReference:        evidence.HostSubjectRef,
		ActorPersonaID:       evidence.ActorPersonaID,
		OrganizerPersonaID:   evidence.OrganizerPersonaID,
		AuthorityEvidenceRef: evidence.AuthorityEvidenceRef,
		AuthorityVersion:     evidence.AuthorityVersion,
		AuthorityDigest:      evidence.AuthorityDigest,
		Action:               gatheringmodel.HostAuthorityAction(evidence.Action),
		Valid:                evidence.Valid,
		Revoked:              evidence.Revoked,
		ExpiresAt:            evidence.ExpiresAt,
	}, nil
}

func toSharedAuthorityQuery(
	query gatheringmodel.HostAuthorityQuery,
) shared.EvaluationQuery {
	return shared.EvaluationQuery{
		HostSubjectKind:      string(query.HostSubjectKind),
		HostSubjectID:        strings.TrimSpace(query.HostSubjectID),
		HostSubjectRef:       authorityHostReference(query),
		ActorPersonaID:       strings.TrimSpace(query.ActorPersonaID),
		OrganizerPersonaID:   strings.TrimSpace(query.OrganizerPersonaID),
		AuthorityEvidenceRef: strings.TrimSpace(query.AuthorityEvidenceRef),
		AuthorityVersion:     query.AuthorityVersion,
		Action:               string(query.Action),
	}
}

func authorityHostReference(query gatheringmodel.HostAuthorityQuery) string {
	return strings.TrimSpace(string(query.HostSubjectKind)) +
		":" + strings.TrimSpace(query.HostSubjectID)
}

func fromSharedAuthorityEvidence(
	evidence shared.Evidence,
) gatheringmodel.HostAuthorityEvidence {
	return gatheringmodel.HostAuthorityEvidence{
		HostSubjectKind:      gatheringHostSubjectKind(evidence.HostSubjectKind),
		HostSubjectID:        evidence.HostSubjectID,
		HostReference:        evidence.HostSubjectRef,
		ActorPersonaID:       evidence.ActorPersonaID,
		OrganizerPersonaID:   evidence.OrganizerPersonaID,
		AuthorityEvidenceRef: evidence.AuthorityEvidenceRef,
		AuthorityVersion:     evidence.AuthorityVersion,
		AuthorityDigest:      evidence.AuthorityDigest,
		Action:               gatheringmodel.HostAuthorityAction(evidence.Action),
		Valid:                evidence.Valid,
		Revoked:              evidence.Revoked,
		ExpiresAt:            evidence.ExpiresAt,
	}
}

func gatheringHostSubjectKind(
	value string,
) gatheringcontract.GatheringHostSubjectKind {
	return gatheringcontract.GatheringHostSubjectKind(strings.TrimSpace(value))
}
