// Package sharedtags 是 content-service 读取 tag-service 共享标签交集的防腐层。
//
// tag-service 独占 object_tag_index 写入，两个对象之间的共享 tagRef 只能由
// `GET /internal/tag/shared-tags` 给出；content-service 不复制这份倒排投影，也不
// 在本地重算用户档案标签。
package sharedtags

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"time"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
)

const sharedTagsOperationID = "tag.tag_node_view.SharedTags"

// maxSharedTagCacheEntries 限制进程内缓存规模。object_tag_index 会随用户改资料
// 变化，所以这里只能做短 TTL 缓存，且必须有上界，避免按 viewer×object 无限增长。
const maxSharedTagCacheEntries = 4096

// SharedTag 是两个对象之间的一条共享标签事实。
//
// 字段与 tag/tag_node_view SharedTagView 契约一一对应。Strength 目前由 tag-service
// 固定给 1，调用方不得据此排序。
type SharedTag struct {
	TagRef   string
	Label    string
	Strength float64
	Source   string
}

// ObjectRef 是共享标签查询的一端。
type ObjectRef struct {
	ID   string
	Type string
}

// HTTPSharedTagReader 通过 generated operation descriptor 访问 tag-service，
// 不在本地重复路由字符串。
//
// SharedTags 的 security 是 auth_mode=required / principal=service，所以必须带
// 服务凭据 bearer；只发 X-Internal-Service 会被 operation guard 拒绝。
type HTTPSharedTagReader struct {
	baseURL     string
	path        string
	client      *http.Client
	timeout     time.Duration
	credentials rtauth.ServiceAuthorizationProvider
	ttl         time.Duration
	now         func() time.Time

	mu    sync.Mutex
	cache map[string]cachedSharedTags
}

type cachedSharedTags struct {
	tags      []SharedTag
	expiresAt time.Time
}

type HTTPSharedTagReaderOption func(*HTTPSharedTagReader)

// WithHTTPClient 供适配器测试与装配注入受控 client。
func WithHTTPClient(client *http.Client) HTTPSharedTagReaderOption {
	return func(reader *HTTPSharedTagReader) {
		if client != nil {
			reader.client = client
		}
	}
}

// WithCacheTTL 覆盖默认缓存时长；<=0 表示不缓存。
func WithCacheTTL(ttl time.Duration) HTTPSharedTagReaderOption {
	return func(reader *HTTPSharedTagReader) {
		reader.ttl = ttl
	}
}

// WithClock 供测试推进缓存过期。
func WithClock(now func() time.Time) HTTPSharedTagReaderOption {
	return func(reader *HTTPSharedTagReader) {
		if now != nil {
			reader.now = now
		}
	}
}

func NewHTTPSharedTagReader(
	baseURL string,
	timeout time.Duration,
	credentials rtauth.ServiceAuthorizationProvider,
	options ...HTTPSharedTagReaderOption,
) (*HTTPSharedTagReader, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" || parsed.User != nil {
		return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"shared tag intersection requires a valid tag-service endpoint",
		)
	}
	if timeout <= 0 {
		return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"shared tag intersection requires a positive request timeout",
		)
	}
	if credentials == nil {
		return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"shared tag intersection requires service credentials",
		)
	}
	path, err := sharedTagsPath()
	if err != nil {
		return nil, err
	}
	reader := &HTTPSharedTagReader{
		baseURL:     strings.TrimRight(parsed.String(), "/"),
		path:        path,
		client:      &http.Client{Timeout: timeout},
		timeout:     timeout,
		credentials: credentials,
		ttl:         30 * time.Second,
		now:         func() time.Time { return time.Now().UTC() },
		cache:       map[string]cachedSharedTags{},
	}
	for _, option := range options {
		if option != nil {
			option(reader)
		}
	}
	return reader, nil
}

func sharedTagsPath() (string, error) {
	for _, descriptor := range operationsecurity.ForDomain("tag") {
		if descriptor.CanonicalOperationID != sharedTagsOperationID {
			continue
		}
		if descriptor.Method != http.MethodGet ||
			descriptor.PathTemplate == "" ||
			strings.ContainsAny(descriptor.PathTemplate, "{}") {
			return "", contentgenerated.AppErrorFromRequiredDependencyUnavailable(
				"shared tag intersection generated operation descriptor is invalid",
			)
		}
		return descriptor.PathTemplate, nil
	}
	return "", contentgenerated.AppErrorFromRequiredDependencyUnavailable(
		"shared tag intersection generated operation descriptor is missing",
	)
}

type sharedTagWire struct {
	TagRef   string  `json:"tagRef"`
	Label    string  `json:"label"`
	Strength float64 `json:"strength"`
	Source   string  `json:"source"`
}

// SharedTags 返回两个对象共享的活跃标签。
//
// 空结果是合法答复：tag-service 对「没有倒排记录」与「确实没有交集」都返回 200 []，
// 调用方必须按「无交集」处理，不得把空结果当失败，也不得自行编造事实。
func (r *HTTPSharedTagReader) SharedTags(
	ctx context.Context,
	first ObjectRef,
	second ObjectRef,
	limit int,
) ([]SharedTag, error) {
	if r == nil || r.client == nil || strings.TrimSpace(r.baseURL) == "" ||
		strings.TrimSpace(r.path) == "" || r.timeout <= 0 || r.credentials == nil {
		return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"shared tag intersection adapter is not configured",
		)
	}
	first, second, err := canonicalObjectPair(first, second)
	if err != nil {
		return nil, err
	}
	if limit < 0 {
		return nil, contentgenerated.AppErrorFromInvalidArgument(
			"shared tag intersection limit must not be negative",
		)
	}
	cacheKey := sharedTagCacheKey(first, second, limit)
	if cached, found := r.cachedTags(cacheKey); found {
		return cached, nil
	}

	query := url.Values{}
	query.Set("objectAId", first.ID)
	query.Set("objectAType", first.Type)
	query.Set("objectBId", second.ID)
	query.Set("objectBType", second.Type)
	if limit > 0 {
		query.Set("limit", strconv.Itoa(limit))
	}

	requestContext, cancel := context.WithTimeout(ctx, r.timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(
		requestContext,
		http.MethodGet,
		r.baseURL+r.path+"?"+query.Encode(),
		nil,
	)
	if err != nil {
		return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"shared tag intersection request could not be created",
		)
	}
	authorization, err := r.credentials.AuthorizationHeader(requestContext)
	if err != nil {
		return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"shared tag intersection service credentials are unavailable",
		)
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("X-Internal-Service", "content-service")

	response, err := r.client.Do(request)
	if err != nil {
		if errors.Is(err, context.DeadlineExceeded) ||
			errors.Is(requestContext.Err(), context.DeadlineExceeded) {
			return nil, contentgenerated.AppErrorFromUpstreamTimeout(
				"shared tag intersection request timed out",
			)
		}
		return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"shared tag intersection request failed",
		)
	}
	defer response.Body.Close()

	switch response.StatusCode {
	case http.StatusOK:
		tags, decodeErr := decodeSharedTags(response.Body, limit)
		if decodeErr != nil {
			return nil, decodeErr
		}
		r.storeTags(cacheKey, tags)
		return tags, nil
	case http.StatusBadRequest:
		discardResponse(response.Body)
		return nil, contentgenerated.AppErrorFromInvalidArgument(
			"shared tag intersection rejected the object pair",
		)
	case http.StatusGatewayTimeout:
		discardResponse(response.Body)
		return nil, contentgenerated.AppErrorFromUpstreamTimeout(
			"shared tag intersection returned HTTP 504",
		)
	default:
		discardResponse(response.Body)
		return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"shared tag intersection returned an unavailable upstream response",
		)
	}
}

func canonicalObjectPair(first, second ObjectRef) (ObjectRef, ObjectRef, error) {
	first = ObjectRef{
		ID:   strings.TrimSpace(first.ID),
		Type: strings.TrimSpace(first.Type),
	}
	second = ObjectRef{
		ID:   strings.TrimSpace(second.ID),
		Type: strings.TrimSpace(second.Type),
	}
	if first.ID == "" || second.ID == "" {
		return ObjectRef{}, ObjectRef{}, contentgenerated.AppErrorFromInvalidArgument(
			"shared tag intersection requires both object ids",
		)
	}
	if first.Type == "" || second.Type == "" {
		return ObjectRef{}, ObjectRef{}, contentgenerated.AppErrorFromInvalidArgument(
			"shared tag intersection requires both object types",
		)
	}
	if first.ID == second.ID && first.Type == second.Type {
		return ObjectRef{}, ObjectRef{}, contentgenerated.AppErrorFromInvalidArgument(
			"shared tag intersection requires two distinct objects",
		)
	}
	return first, second, nil
}

// sharedTagCacheKey 对两端排序后成键：共享标签是对称关系，viewer↔object 与
// object↔viewer 必须命中同一条缓存。
func sharedTagCacheKey(first, second ObjectRef, limit int) string {
	left := first.Type + ":" + first.ID
	right := second.Type + ":" + second.ID
	if left > right {
		left, right = right, left
	}
	return left + "|" + right + "|" + strconv.Itoa(limit)
}

func (r *HTTPSharedTagReader) cachedTags(key string) ([]SharedTag, bool) {
	if r.ttl <= 0 {
		return nil, false
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	entry, found := r.cache[key]
	if !found {
		return nil, false
	}
	if r.now().After(entry.expiresAt) {
		delete(r.cache, key)
		return nil, false
	}
	return append([]SharedTag(nil), entry.tags...), true
}

func (r *HTTPSharedTagReader) storeTags(key string, tags []SharedTag) {
	if r.ttl <= 0 {
		return
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if len(r.cache) >= maxSharedTagCacheEntries {
		r.cache = map[string]cachedSharedTags{}
	}
	r.cache[key] = cachedSharedTags{
		tags:      append([]SharedTag(nil), tags...),
		expiresAt: r.now().Add(r.ttl),
	}
}

func decodeSharedTags(body io.Reader, limit int) ([]SharedTag, error) {
	decoder := json.NewDecoder(io.LimitReader(body, 1024*1024))
	var wire []sharedTagWire
	if err := decoder.Decode(&wire); err != nil {
		return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"shared tag intersection response could not be decoded",
		)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"shared tag intersection response contains trailing data",
		)
	}
	if limit > 0 && len(wire) > limit {
		return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"shared tag intersection response exceeds the requested limit",
		)
	}
	seen := make(map[string]struct{}, len(wire))
	tags := make([]SharedTag, 0, len(wire))
	for _, row := range wire {
		tagRef := strings.TrimSpace(row.TagRef)
		if tagRef == "" {
			return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
				"shared tag intersection response contains an empty tagRef",
			)
		}
		if _, duplicate := seen[tagRef]; duplicate {
			return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
				"shared tag intersection response duplicates a tagRef",
			)
		}
		seen[tagRef] = struct{}{}
		tags = append(tags, SharedTag{
			TagRef:   tagRef,
			Label:    strings.TrimSpace(row.Label),
			Strength: row.Strength,
			Source:   strings.TrimSpace(row.Source),
		})
	}
	return tags, nil
}

func discardResponse(body io.Reader) {
	_, _ = io.Copy(io.Discard, io.LimitReader(body, 1024))
}
