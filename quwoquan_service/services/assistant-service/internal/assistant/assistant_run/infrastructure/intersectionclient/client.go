package intersectionclient

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	runtool "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	runports "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

const (
	getObjectIntersectionsOperationID = "content.intersection_visit_state.GetObjectIntersections"
	listMyIntersectionsOperationID    = "content.intersection_visit_state.ListMyIntersections"
	maxResponseBytes                  = 512 << 10
)

type Config struct {
	BaseURL       string
	HTTPClient    *http.Client
	Authorization rtauth.DelegatedPersonaAuthorizationProvider
}

// Client 从 content-service 的正式 GetObjectIntersections Slice 回查交集证据。
type Client struct {
	baseURL       *url.URL
	http          *http.Client
	authorization rtauth.DelegatedPersonaAuthorizationProvider
	path          string
}

var _ runports.IntersectionEvidenceReader = (*Client)(nil)
var _ runtool.MyIntersectionsReader = (*Client)(nil)

func New(config Config) (*Client, error) {
	baseURL, err := url.Parse(strings.TrimSpace(config.BaseURL))
	if err != nil || baseURL.Scheme == "" || baseURL.Host == "" {
		return nil, fmt.Errorf("content-service base url is invalid")
	}
	if config.Authorization == nil {
		return nil, fmt.Errorf("content-service delegated authorization is required")
	}
	descriptor, err := operationDescriptor()
	if err != nil {
		return nil, err
	}
	httpClient := config.HTTPClient
	if httpClient == nil {
		timeout := time.Duration(descriptor.TimeoutMilliseconds) * time.Millisecond
		if timeout <= 0 {
			timeout = 1500 * time.Millisecond
		}
		httpClient = &http.Client{Timeout: timeout}
	}
	return &Client{
		baseURL:       baseURL,
		http:          httpClient,
		authorization: config.Authorization,
		path:          descriptor.PathTemplate,
	}, nil
}

// ResolveAuthorizedIntersectionEvidence 以 delegation token 读取当前 persona 对目标
// 对象的正式交集 Slice，并严格比对客户端引用的不可解释 key。展示文本和 URL 从不由
// 客户端输入进入结果。
func (c *Client) ResolveAuthorizedIntersectionEvidence(
	ctx context.Context,
	personaID string,
	refs []assistant.AssistantIntersectionEvidenceRef,
) ([]assistant.AuthorizedIntersectionEvidence, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" {
		return nil, runapplication.ErrIntersectionEvidenceNotFound
	}
	resolved := make([]assistant.AuthorizedIntersectionEvidence, 0, len(refs))
	for _, ref := range refs {
		items, err := c.listObjectIntersectionEvidence(ctx, personaID, ref)
		if err != nil {
			return nil, err
		}
		match, found := matchIntersectionEvidence(ref, items)
		if !found {
			return nil, runapplication.ErrIntersectionEvidenceNotFound
		}
		resolved = append(resolved, assistant.AuthorizedIntersectionEvidence{
			IntersectionID: strings.TrimSpace(match.IntersectionID),
			EvidenceID:     strings.TrimSpace(match.PointSummarySnapshotID),
			SourceRef:      strings.TrimSpace(match.Kind),
			ObjectTypeRef:  strings.TrimSpace(ref.ObjectTypeRef),
			ObjectID:       strings.TrimSpace(ref.ObjectID),
			PrimaryText:    strings.TrimSpace(match.PrimaryText),
			Dimension:      strings.TrimSpace(match.Dimension),
			VerifiedAt:     time.Now().UTC(),
		})
	}
	return resolved, nil
}

type objectIntersectionEvidenceItem struct {
	IntersectionID         string `json:"intersectionId"`
	PointSummarySnapshotID string `json:"pointSummarySnapshotId"`
	Kind                   string `json:"kind"`
	PrimaryText            string `json:"primaryText"`
	Dimension              string `json:"dimension"`
}

func (c *Client) listObjectIntersectionEvidence(
	ctx context.Context,
	personaID string,
	ref assistant.AssistantIntersectionEvidenceRef,
) ([]objectIntersectionEvidenceItem, error) {
	target := *c.baseURL
	target.Path = strings.TrimRight(target.Path, "/") + c.path
	values := target.Query()
	values.Set("objectId", strings.TrimSpace(ref.ObjectID))
	values.Set("objectType", strings.TrimSpace(ref.ObjectTypeRef))
	values.Set("limit", "50")
	target.RawQuery = values.Encode()

	request, err := http.NewRequestWithContext(ctx, http.MethodGet, target.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("%w: build object intersection request: %v", runapplication.ErrIntersectionEvidenceUnavailable, err)
	}
	authorization, err := c.authorization.AuthorizationHeaderForPersona(ctx, personaID)
	if err != nil {
		return nil, fmt.Errorf("%w: authorize object intersection request: %v", runapplication.ErrIntersectionEvidenceUnavailable, err)
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Accept", "application/json")
	response, err := c.http.Do(request)
	if err != nil {
		return nil, fmt.Errorf("%w: call content object intersections: %v", runapplication.ErrIntersectionEvidenceUnavailable, err)
	}
	defer response.Body.Close()
	if response.StatusCode == http.StatusUnauthorized ||
		response.StatusCode == http.StatusForbidden ||
		response.StatusCode == http.StatusNotFound ||
		response.StatusCode == http.StatusBadRequest {
		return nil, runapplication.ErrIntersectionEvidenceNotFound
	}
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf(
			"%w: content object intersections status=%d",
			runapplication.ErrIntersectionEvidenceUnavailable,
			response.StatusCode,
		)
	}
	var payload struct {
		Items []objectIntersectionEvidenceItem `json:"items"`
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, maxResponseBytes))
	if err := decoder.Decode(&payload); err != nil {
		return nil, fmt.Errorf("%w: decode content object intersections: %v", runapplication.ErrIntersectionEvidenceUnavailable, err)
	}
	return payload.Items, nil
}

// ListMyIntersections 实现 intersection.read_mine 的 domain_reader binding：
// 以 delegated persona token 读取 content-service 正式 ListMyIntersections
// Slice（与 App「我的交集」同一读面），任何失败结构化上抛 fail-closed。
func (c *Client) ListMyIntersections(
	ctx context.Context,
	personaID string,
	query runtool.MyIntersectionsQuery,
) ([]runtool.MyIntersectionItem, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" {
		return nil, fmt.Errorf("my intersections persona is required")
	}
	descriptor, err := myIntersectionsOperationDescriptor()
	if err != nil {
		return nil, err
	}
	target := *c.baseURL
	target.Path = strings.TrimRight(target.Path, "/") + descriptor.PathTemplate
	values := target.Query()
	values.Set("limit", fmt.Sprintf("%d", query.Limit))
	if query.Dimension != "" {
		values.Set("dimension", query.Dimension)
	}
	if query.Filter != "" {
		values.Set("filter", query.Filter)
	}
	if query.Cursor != "" {
		values.Set("cursor", query.Cursor)
	}
	target.RawQuery = values.Encode()

	request, err := http.NewRequestWithContext(ctx, http.MethodGet, target.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("build my intersections request: %w", err)
	}
	authorization, err := c.authorization.AuthorizationHeaderForPersona(ctx, personaID)
	if err != nil {
		return nil, fmt.Errorf("authorize my intersections request: %w", err)
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Accept", "application/json")
	response, err := c.http.Do(request)
	if err != nil {
		return nil, fmt.Errorf("call content my intersections: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf(
			"content my intersections status=%d", response.StatusCode,
		)
	}
	var payload struct {
		Items []struct {
			IntersectionID    string  `json:"intersectionId"`
			IntersectionClass string  `json:"intersectionClass"`
			Kind              string  `json:"kind"`
			Dimension         string  `json:"dimension"`
			ObjectKind        string  `json:"objectKind"`
			DisplayName       string  `json:"displayName"`
			PrimaryText       string  `json:"primaryText"`
			Strength          float64 `json:"strength"`
			FreshAt           string  `json:"freshAt"`
			ExpiresAt         string  `json:"expiresAt"`
			ActionHints       []struct {
				ActionKey string `json:"actionKey"`
			} `json:"actionHints"`
		} `json:"items"`
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, maxResponseBytes))
	if err := decoder.Decode(&payload); err != nil {
		return nil, fmt.Errorf("decode content my intersections: %w", err)
	}
	items := make([]runtool.MyIntersectionItem, 0, len(payload.Items))
	for _, item := range payload.Items {
		actionKeys := make([]string, 0, len(item.ActionHints))
		for _, hint := range item.ActionHints {
			if key := strings.TrimSpace(hint.ActionKey); key != "" {
				actionKeys = append(actionKeys, key)
			}
		}
		items = append(items, runtool.MyIntersectionItem{
			IntersectionID:    strings.TrimSpace(item.IntersectionID),
			IntersectionClass: strings.TrimSpace(item.IntersectionClass),
			Kind:              strings.TrimSpace(item.Kind),
			Dimension:         strings.TrimSpace(item.Dimension),
			ObjectKind:        strings.TrimSpace(item.ObjectKind),
			DisplayName:       strings.TrimSpace(item.DisplayName),
			PrimaryText:       strings.TrimSpace(item.PrimaryText),
			Strength:          item.Strength,
			FreshAt:           strings.TrimSpace(item.FreshAt),
			ExpiresAt:         strings.TrimSpace(item.ExpiresAt),
			ActionKeys:        actionKeys,
		})
	}
	return items, nil
}

func myIntersectionsOperationDescriptor() (rtauth.OperationSecurityDescriptor, error) {
	for _, descriptor := range operationsecurity.ForDomain("content") {
		if descriptor.CanonicalOperationID == listMyIntersectionsOperationID {
			return descriptor, nil
		}
	}
	return rtauth.OperationSecurityDescriptor{}, fmt.Errorf(
		"generated operation descriptor %q is missing",
		listMyIntersectionsOperationID,
	)
}

func matchIntersectionEvidence(
	ref assistant.AssistantIntersectionEvidenceRef,
	items []objectIntersectionEvidenceItem,
) (objectIntersectionEvidenceItem, bool) {
	for _, item := range items {
		if strings.TrimSpace(item.IntersectionID) == strings.TrimSpace(ref.IntersectionID) &&
			strings.TrimSpace(item.PointSummarySnapshotID) == strings.TrimSpace(ref.EvidenceID) &&
			strings.TrimSpace(item.Kind) == strings.TrimSpace(ref.SourceRef) {
			return item, true
		}
	}
	return objectIntersectionEvidenceItem{}, false
}

func operationDescriptor() (rtauth.OperationSecurityDescriptor, error) {
	for _, descriptor := range operationsecurity.ForDomain("content") {
		if descriptor.CanonicalOperationID == getObjectIntersectionsOperationID {
			return descriptor, nil
		}
	}
	return rtauth.OperationSecurityDescriptor{}, fmt.Errorf(
		"generated operation descriptor %q is missing",
		getObjectIntersectionsOperationID,
	)
}
