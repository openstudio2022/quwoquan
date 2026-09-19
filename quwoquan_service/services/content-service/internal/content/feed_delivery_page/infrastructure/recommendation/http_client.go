package recommendation

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	transport "quwoquan_service/services/content-service/generated/content/feed_delivery_page"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
)

const retryBackoff = 20 * time.Millisecond

type HTTPClient struct {
	baseURL     string
	httpClient  *http.Client
	credentials rtauth.ServiceAuthorizationProvider
}

func NewHTTPClient(
	baseURL string,
	credentials rtauth.ServiceAuthorizationProvider,
) (*HTTPClient, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("ranked recommendation client: valid base URL is required")
	}
	if credentials == nil {
		return nil, fmt.Errorf("ranked recommendation client: service credentials are required")
	}
	return &HTTPClient{
		baseURL:     strings.TrimRight(parsed.String(), "/"),
		httpClient:  &http.Client{},
		credentials: credentials,
	}, nil
}

func (client *HTTPClient) SetTransport(transport http.RoundTripper) {
	if transport == nil {
		transport = http.DefaultTransport
	}
	client.httpClient.Transport = transport
}

func (client *HTTPClient) Create(
	ctx context.Context,
	command transport.CreateRankedRecommendationWindowCommand,
) (transport.RankedRecommendationPage, error) {
	if err := transport.ValidateClientContentPresentationContract(
		command.ClientPresentationContract,
	); err != nil {
		return transport.RankedRecommendationPage{}, fmt.Errorf(
			"%w: create ranked window client presentation contract: %v",
			deliveryapp.ErrRecommendationUnavailable,
			err,
		)
	}
	body, err := json.Marshal(transport.CreateRankedRecommendationWindowRequestBody{
		ContentFence:               command.ContentFence,
		SubjectId:                  command.SubjectId,
		Scenario:                   command.Scenario,
		ClientPresentationContract: command.ClientPresentationContract,
		Limit:                      command.Limit,
	})
	if err != nil {
		return transport.RankedRecommendationPage{}, fmt.Errorf(
			"%w: encode create ranked window request: %v",
			deliveryapp.ErrRecommendationUnavailable,
			err,
		)
	}
	return client.do(
		ctx,
		transport.CreateRankedRecommendationWindowMethod,
		client.baseURL+transport.CreateRankedRecommendationWindowPath,
		body,
		strings.TrimSpace(command.IdempotencyKey),
		800*time.Millisecond,
	)
}

func (client *HTTPClient) GetPage(
	ctx context.Context,
	request transport.GetRankedRecommendationPageQuery,
) (transport.RankedRecommendationPage, error) {
	path := strings.Replace(
		transport.GetRankedRecommendationPagePath,
		"{windowId}",
		url.PathEscape(strings.TrimSpace(request.WindowId)),
		1,
	)
	if err := transport.ValidateClientContentPresentationContract(
		request.ClientPresentationContract,
	); err != nil {
		return transport.RankedRecommendationPage{}, fmt.Errorf(
			"%w: ranked window page client presentation contract: %v",
			deliveryapp.ErrRecommendationUnavailable,
			err,
		)
	}
	// windowId 走 path，其余查询字段走 body。clientPresentationContract 必须与
	// 建窗时相同：续页窗口的能力绑定由 recommendation 侧按本字段校验，缺席即
	// 让窗口退回固定基线，与首刷不再是同一能力。
	body, err := json.Marshal(getRankedRecommendationPageRequestBody{
		ContentFence:               request.ContentFence,
		SubjectID:                  strings.TrimSpace(request.SubjectId),
		ClientPresentationContract: request.ClientPresentationContract,
		FromOrdinal:                request.FromOrdinal,
		Limit:                      request.Limit,
	})
	if err != nil {
		return transport.RankedRecommendationPage{}, err
	}
	return client.do(
		ctx,
		transport.GetRankedRecommendationPageMethod,
		client.baseURL+path,
		body,
		"",
		300*time.Millisecond,
	)
}

// getRankedRecommendationPageRequestBody 是续页查询的 wire body。GetPage 没有
// 生成 request body 类型（windowId 属于 path），字段集合仍必须与
// GetRankedRecommendationPageQuery 去掉 windowId 后完全一致。
type getRankedRecommendationPageRequestBody struct {
	ContentFence               transport.ReleasePinnedQueryFence           `json:"contentFence"`
	SubjectID                  string                                      `json:"subjectId"`
	ClientPresentationContract transport.ClientContentPresentationContract `json:"clientPresentationContract"`
	FromOrdinal                *int                                        `json:"fromOrdinal,omitempty"`
	Limit                      *int                                        `json:"limit,omitempty"`
}

type transientStatusError struct {
	status int
}

func (err transientStatusError) Error() string {
	return fmt.Sprintf("transient recommendation status %d", err.status)
}

func (client *HTTPClient) do(
	ctx context.Context,
	method string,
	endpoint string,
	body []byte,
	idempotencyKey string,
	timeout time.Duration,
) (transport.RankedRecommendationPage, error) {
	if client == nil || client.httpClient == nil || client.credentials == nil {
		return transport.RankedRecommendationPage{}, deliveryapp.ErrRecommendationUnavailable
	}
	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		if attempt > 0 {
			timer := time.NewTimer(retryBackoff)
			select {
			case <-ctx.Done():
				timer.Stop()
				return transport.RankedRecommendationPage{}, ctx.Err()
			case <-timer.C:
			}
		}
		page, err := client.doOnce(
			ctx,
			method,
			endpoint,
			body,
			idempotencyKey,
			timeout,
		)
		if err == nil {
			return page, nil
		}
		lastErr = err
		var transient transientStatusError
		if !errors.As(err, &transient) {
			break
		}
	}
	return transport.RankedRecommendationPage{}, fmt.Errorf(
		"%w: %v",
		deliveryapp.ErrRecommendationUnavailable,
		lastErr,
	)
}

func (client *HTTPClient) doOnce(
	ctx context.Context,
	method string,
	endpoint string,
	body []byte,
	idempotencyKey string,
	timeout time.Duration,
) (transport.RankedRecommendationPage, error) {
	requestContext, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(
		requestContext,
		method,
		endpoint,
		bytes.NewReader(body),
	)
	if err != nil {
		return transport.RankedRecommendationPage{}, err
	}
	request.Header.Set("Accept", "application/json")
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	authorization, err := client.credentials.AuthorizationHeader(requestContext)
	if err != nil {
		return transport.RankedRecommendationPage{}, fmt.Errorf("service authorization: %w", err)
	}
	request.Header.Set("Authorization", authorization)
	response, err := client.httpClient.Do(request)
	if err != nil {
		return transport.RankedRecommendationPage{}, transientStatusError{status: http.StatusServiceUnavailable}
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		if response.StatusCode == http.StatusBadGateway ||
			response.StatusCode == http.StatusServiceUnavailable ||
			response.StatusCode == http.StatusGatewayTimeout {
			return transport.RankedRecommendationPage{}, transientStatusError{status: response.StatusCode}
		}
		return transport.RankedRecommendationPage{}, fmt.Errorf(
			"recommendation status %d",
			response.StatusCode,
		)
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, 2*1024*1024))
	decoder.DisallowUnknownFields()
	var page transport.RankedRecommendationPage
	if err := decoder.Decode(&page); err != nil {
		return transport.RankedRecommendationPage{}, fmt.Errorf("decode ranked recommendation page: %w", err)
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return transport.RankedRecommendationPage{}, fmt.Errorf("ranked recommendation page has trailing payload")
	}
	if err := validatePage(page); err != nil {
		return transport.RankedRecommendationPage{}, err
	}
	return page, nil
}

func validatePage(page transport.RankedRecommendationPage) error {
	if strings.TrimSpace(page.WindowId) == "" || strings.TrimSpace(page.Scenario) == "" ||
		!strings.HasPrefix(strings.TrimSpace(page.PolicyDigest), "sha256:") ||
		strings.TrimSpace(page.RankingSnapshotDigest) == "" || page.FeatureSnapshotAt.IsZero() ||
		page.ExpiresAt.IsZero() || !page.ExpiresAt.After(time.Now().UTC()) ||
		page.UserFeatureSnapshot == nil || len(page.Items) > 100 {
		return fmt.Errorf("ranked recommendation page identity is invalid")
	}
	modelChannel := optionalText(page.ModelChannel)
	modelReleaseID := optionalText(page.ModelReleaseId)
	switch page.ModelBucket {
	case "model":
		if modelChannel == "" || modelReleaseID == "" {
			return fmt.Errorf("model ranked page attribution is incomplete")
		}
	case "rule":
		if modelChannel != "" || modelReleaseID != "" {
			return fmt.Errorf("rule ranked page cannot claim a model release")
		}
	default:
		return fmt.Errorf("ranked page model bucket is invalid")
	}
	// 窗口回显的能力声明必须自洽：digest 由本地重算，不接受对方自报。
	if err := transport.ValidateClientContentPresentationContract(
		page.ClientPresentationContract,
	); err != nil {
		return fmt.Errorf("ranked recommendation page presentation contract is invalid: %w", err)
	}
	seenOrdinals := make(map[int]struct{}, len(page.Items))
	seenObjects := make(map[string]struct{}, len(page.Items))
	for _, item := range page.Items {
		objectID, err := listItemObjectIdentity(item.Envelope)
		if err != nil {
			return err
		}
		if err := envelopeWithinContract(
			item.Envelope,
			page.ClientPresentationContract,
		); err != nil {
			return err
		}
		if item.Ordinal < 0 || strings.TrimSpace(item.FeatureSnapshotDigest) == "" ||
			item.ItemFeatureSnapshot == nil {
			return fmt.Errorf("ranked recommendation item is invalid")
		}
		if _, duplicate := seenOrdinals[item.Ordinal]; duplicate {
			return fmt.Errorf("ranked recommendation item ordinal is duplicated")
		}
		if _, duplicate := seenObjects[objectID]; duplicate {
			return fmt.Errorf("ranked recommendation object identity is duplicated")
		}
		seenOrdinals[item.Ordinal] = struct{}{}
		seenObjects[objectID] = struct{}{}
	}
	if page.NextOrdinal != nil && (*page.NextOrdinal < 0 || len(page.Items) == 0) {
		return fmt.Errorf("ranked recommendation continuation is invalid")
	}
	return nil
}

// listItemObjectIdentity 按 objectKind 读出这一项的对象身份。objectKind 决定
// 读哪一个引用字段；引用与 objectKind 不匹配、缺席或两个引用同时出现都是
// 无效窗口，不能靠取值组合推断这一项到底是什么。
func listItemObjectIdentity(
	envelope transport.ListItemPresentationEnvelope,
) (string, error) {
	objectKind := string(envelope.ObjectKind)
	if envelope.ObjectKind.Validate() != nil || envelope.OpenSurface.Validate() != nil {
		return "", fmt.Errorf("ranked recommendation list item envelope is incomplete")
	}
	if (envelope.Post != nil) == (envelope.Homepage != nil) {
		return "", fmt.Errorf(
			"ranked recommendation list item envelope must carry exactly one object reference",
		)
	}
	switch {
	case envelope.Post != nil:
		if objectKind != "post" {
			return "", fmt.Errorf(
				"ranked recommendation list item envelope objectKind %q does not match its post reference",
				objectKind,
			)
		}
		postID := strings.TrimSpace(envelope.Post.PostId)
		if postID == "" {
			return "", fmt.Errorf("ranked recommendation list item post reference is empty")
		}
		return objectKind + ":" + postID, nil
	default:
		if objectKind != "entity_homepage" {
			return "", fmt.Errorf(
				"ranked recommendation list item envelope objectKind %q does not match its homepage reference",
				objectKind,
			)
		}
		homepageID := strings.TrimSpace(envelope.Homepage.HomepageId)
		if homepageID == "" {
			return "", fmt.Errorf("ranked recommendation list item homepage reference is empty")
		}
		return objectKind + ":" + homepageID, nil
	}
}

// envelopeWithinContract 断言窗口条目没有越过该窗口自己声明的能力。窗口是按
// 请求能力构造的，越界条目意味着对方没有遵守建窗契约；这类条目不能靠客户端
// 丢弃兜底，只能让整个窗口 fail-closed。
func envelopeWithinContract(
	envelope transport.ListItemPresentationEnvelope,
	contract transport.ClientContentPresentationContract,
) error {
	if !declares(contract.ListObjectKinds, envelope.ObjectKind) {
		return fmt.Errorf(
			"ranked recommendation list item objectKind %q is outside the window presentation contract",
			envelope.ObjectKind,
		)
	}
	if !declares(contract.OpenSurfaces, envelope.OpenSurface) {
		return fmt.Errorf(
			"ranked recommendation list item openSurface %q is outside the window presentation contract",
			envelope.OpenSurface,
		)
	}
	if envelope.ContentType != nil && !declares(contract.ContentTypes, *envelope.ContentType) {
		return fmt.Errorf(
			"ranked recommendation list item contentType %q is outside the window presentation contract",
			*envelope.ContentType,
		)
	}
	if envelope.PresentationRecipe != nil &&
		!declares(contract.PresentationRecipes, *envelope.PresentationRecipe) {
		return fmt.Errorf(
			"ranked recommendation list item presentationRecipe %q is outside the window presentation contract",
			*envelope.PresentationRecipe,
		)
	}
	return nil
}

func declares[member comparable](declared []member, value member) bool {
	for _, candidate := range declared {
		if candidate == value {
			return true
		}
	}
	return false
}

func optionalText(value *string) string {
	if value == nil {
		return ""
	}
	return strings.TrimSpace(*value)
}

var _ deliveryapp.RankedRecommendationGateway = (*HTTPClient)(nil)
