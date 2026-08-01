package integration

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

	greetingapp "quwoquan_service/services/user-service/internal/relationship/greeting_request/application"
	greetingmodel "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/model"
)

const greetingIntersectionResponseLimit = 1 << 20

type PersonaAuthorizationProvider interface {
	AuthorizationHeaderForPersona(context.Context, string) (string, error)
}

// IntersectionResolver 只经 content-service 的公开对象交集 Reader 回查事实。
// 它严格匹配全部不可解释 key，客户端传入的文案永不进入快照。
type IntersectionResolver struct {
	baseURL       *url.URL
	client        *http.Client
	authorization PersonaAuthorizationProvider
}

func NewIntersectionResolver(
	baseURL string,
	client *http.Client,
	authorization PersonaAuthorizationProvider,
) (*IntersectionResolver, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") ||
		parsed.Host == "" || parsed.User != nil {
		return nil, errors.New("content service base URL must be absolute http or https")
	}
	if authorization == nil {
		return nil, errors.New("content intersection delegated authorization is required")
	}
	if client == nil {
		client = &http.Client{Timeout: 1500 * time.Millisecond}
	}
	return &IntersectionResolver{
		baseURL:       parsed,
		client:        client,
		authorization: authorization,
	}, nil
}

func (r *IntersectionResolver) ResolveGreetingIntersection(
	ctx context.Context,
	requesterPersonaID string,
	targetPersonaID string,
	ref greetingmodel.GreetingIntersectionRef,
) (*greetingmodel.GreetingIntersectionSnapshot, error) {
	ref = ref.Normalized()
	requesterPersonaID = strings.TrimSpace(requesterPersonaID)
	targetPersonaID = strings.TrimSpace(targetPersonaID)
	if !ref.Complete() || requesterPersonaID == "" || targetPersonaID == "" ||
		ref.ObjectID != targetPersonaID {
		return nil, errors.New("greeting intersection reference does not target recipient")
	}
	target := *r.baseURL
	target.Path = strings.TrimRight(target.Path, "/") + "/content/intersections/object"
	query := target.Query()
	query.Set("objectId", ref.ObjectID)
	query.Set("objectType", ref.ObjectTypeRef)
	query.Set("limit", "50")
	target.RawQuery = query.Encode()

	request, err := http.NewRequestWithContext(ctx, http.MethodGet, target.String(), nil)
	if err != nil {
		return nil, err
	}
	authorization, err := r.authorization.AuthorizationHeaderForPersona(ctx, requesterPersonaID)
	if err != nil {
		return nil, err
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Accept", "application/json")
	response, err := r.client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("content object intersections status=%d", response.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, greetingIntersectionResponseLimit+1))
	if err != nil || len(body) > greetingIntersectionResponseLimit {
		return nil, errors.New("content object intersections response invalid")
	}
	var payload struct {
		Items []struct {
			IntersectionID         string `json:"intersectionId"`
			PointSummarySnapshotID string `json:"pointSummarySnapshotId"`
			Kind                   string `json:"kind"`
			PrimaryText            string `json:"primaryText"`
			Dimension              string `json:"dimension"`
		} `json:"items"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, err
	}
	for _, item := range payload.Items {
		if strings.TrimSpace(item.IntersectionID) != ref.IntersectionID ||
			strings.TrimSpace(item.PointSummarySnapshotID) != ref.EvidenceID ||
			strings.TrimSpace(item.Kind) != ref.SourceRef ||
			strings.TrimSpace(item.PrimaryText) == "" {
			continue
		}
		return &greetingmodel.GreetingIntersectionSnapshot{
			IntersectionID: ref.IntersectionID,
			EvidenceID:     ref.EvidenceID,
			SourceRef:      ref.SourceRef,
			ObjectTypeRef:  ref.ObjectTypeRef,
			ObjectID:       ref.ObjectID,
			PrimaryText:    strings.TrimSpace(item.PrimaryText),
			Dimension:      strings.TrimSpace(item.Dimension),
			ResolvedAt:     time.Now().UTC(),
		}, nil
	}
	return nil, errors.New("greeting intersection reference is no longer valid")
}

var _ greetingapp.GreetingIntersectionResolver = (*IntersectionResolver)(nil)
