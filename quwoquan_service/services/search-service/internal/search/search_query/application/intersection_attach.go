package application

import (
	"context"
	"errors"
	"log/slog"
	"strings"
	"time"

	rtsearch "quwoquan_service/runtime/search"
)

const (
	ConnectionStateConnected        = "connected"
	ConnectionStateUnconnected      = "unconnected"
	ConnectionStateIntersectionLead = "intersection_lead"

	intersectionAttachDegradeCode = "SEARCH.INTERSECTION.attach_unavailable"
)

// ObjectIntersectionQuery 是 search 域向统一交集真相源发起的具名 Reader 查询。
type ObjectIntersectionQuery struct {
	ViewerPersonaID string
	ObjectID        string
	ObjectType      string
	Limit           int
}

// ObjectIntersectionFact 只承载 SearchHit 所需的最小、已通过隐私过滤的展示事实。
// primaryText 必须由 content IntersectionService 生成；search-service 不拼文案。
type ObjectIntersectionFact struct {
	PrimaryText       string
	IntersectionID    string
	Dimension         string
	IntersectionClass string
	SourceRef         string
	SourceRefs        []string
	ConnectionState   string
}

// ObjectIntersectionReader 是跨上下文只读端口；具体 HTTP/鉴权在 infrastructure。
type ObjectIntersectionReader interface {
	ListObjectIntersections(
		ctx context.Context,
		query ObjectIntersectionQuery,
	) ([]ObjectIntersectionFact, error)
}

type IntersectionAttachObservation struct {
	Status        string
	Seconds       float64
	RequestedHits int
	AttachedHits  int
}

type IntersectionAttachObserver interface {
	ObserveIntersectionAttach(observation IntersectionAttachObservation)
}

type IntersectionAttacherConfig struct {
	Timeout       time.Duration
	MaxHits       int
	MaxConcurrent int
	ReasonLimit   int
}

type IntersectionAttacher struct {
	reader   ObjectIntersectionReader
	config   IntersectionAttacherConfig
	logger   *slog.Logger
	observer IntersectionAttachObserver
}

func NewIntersectionAttacher(
	reader ObjectIntersectionReader,
	config IntersectionAttacherConfig,
	logger *slog.Logger,
	observer IntersectionAttachObserver,
) *IntersectionAttacher {
	if config.Timeout <= 0 {
		config.Timeout = 300 * time.Millisecond
	}
	if config.MaxHits <= 0 {
		config.MaxHits = 8
	}
	if config.MaxConcurrent <= 0 {
		config.MaxConcurrent = 4
	}
	if config.ReasonLimit <= 0 {
		config.ReasonLimit = 1
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &IntersectionAttacher{
		reader: reader, config: config, logger: logger, observer: observer,
	}
}

// Attach 在排序完成后只处理 top-N。匿名请求不触达交集服务；已登录请求在有界
// timeout/concurrency 内读取统一事实。部分失败只附加 typed degrade signal，不阻断搜索。
func (a *IntersectionAttacher) Attach(
	ctx context.Context,
	viewerPersonaID string,
	response rtsearch.RetrieveResponse,
) rtsearch.RetrieveResponse {
	viewerPersonaID = strings.TrimSpace(viewerPersonaID)
	if a == nil || a.reader == nil || viewerPersonaID == "" || len(response.Hits) == 0 {
		return response
	}

	started := time.Now()
	hits := append([]rtsearch.RetrieveHit(nil), response.Hits...)
	for index := range hits {
		hits[index].ConnectionState = normalizedExistingConnectionState(
			hits[index].ConnectionState,
		)
	}

	count := min(len(hits), a.config.MaxHits)
	attachCtx, cancel := context.WithTimeout(ctx, a.config.Timeout)
	defer cancel()

	type result struct {
		index int
		facts []ObjectIntersectionFact
		err   error
	}
	results := make(chan result, count)
	semaphore := make(chan struct{}, a.config.MaxConcurrent)
	for index := 0; index < count; index++ {
		hit := hits[index]
		objectType, ok := intersectionObjectType(hit.Target)
		if !ok {
			results <- result{index: index}
			continue
		}
		go func(index int, hit rtsearch.RetrieveHit, objectType string) {
			select {
			case semaphore <- struct{}{}:
				defer func() { <-semaphore }()
			case <-attachCtx.Done():
				results <- result{index: index, err: attachCtx.Err()}
				return
			}
			facts, err := a.reader.ListObjectIntersections(
				attachCtx,
				ObjectIntersectionQuery{
					ViewerPersonaID: viewerPersonaID,
					ObjectID:        hit.ObjectID,
					ObjectType:      objectType,
					Limit:           a.config.ReasonLimit,
				},
			)
			results <- result{index: index, facts: facts, err: err}
		}(index, hit, objectType)
	}

	received := 0
	attached := 0
	degraded := false
	for received < count {
		select {
		case item := <-results:
			received++
			if item.err != nil {
				degraded = true
				a.logger.WarnContext(
					ctx,
					"search intersection attach degraded",
					slog.String("target", string(hits[item.index].Target)),
					slog.String("errorType", attachErrorType(item.err)),
				)
				continue
			}
			if fact, ok := firstDisplayableIntersection(item.facts); ok {
				hits[item.index].ConnectionState = resolveConnectionState(
					hits[item.index].Target,
					hits[item.index].ConnectionState,
					fact.ConnectionState,
					fact.SourceRefs,
				)
				hits[item.index].IntersectionReason = &rtsearch.HitIntersectionReason{
					PrimaryText:    strings.TrimSpace(fact.PrimaryText),
					IntersectionID: strings.TrimSpace(fact.IntersectionID),
					Dimension:      strings.TrimSpace(fact.Dimension),
					Class:          strings.TrimSpace(fact.IntersectionClass),
					SourceRef:      strings.TrimSpace(fact.SourceRef),
				}
				attached++
			}
		case <-attachCtx.Done():
			degraded = true
			received = count
		}
	}

	response.Hits = hits
	status := "ok"
	if degraded {
		status = "degraded"
		response.DegradeSignals = appendUniqueDegradeSignal(
			response.DegradeSignals,
			rtsearch.DegradeSignal{
				Code:    intersectionAttachDegradeCode,
				Message: "与你相关的连接信息暂时不可用，搜索结果不受影响。",
			},
		)
	}
	if a.observer != nil {
		a.observer.ObserveIntersectionAttach(IntersectionAttachObservation{
			Status:        status,
			Seconds:       time.Since(started).Seconds(),
			RequestedHits: count,
			AttachedHits:  attached,
		})
	}
	return response
}

func intersectionObjectType(target rtsearch.Target) (string, bool) {
	switch target {
	case rtsearch.TargetArticle, rtsearch.TargetPhoto, rtsearch.TargetVideo:
		return "post", true
	case rtsearch.TargetUser:
		return "user", true
	case rtsearch.TargetEntity:
		return "homepage", true
	case rtsearch.TargetCircle:
		return "circle", true
	case rtsearch.TargetGroup:
		return "circle_group", true
	case rtsearch.TargetLocation:
		return "location", true
	default:
		return "", false
	}
}

func firstDisplayableIntersection(
	facts []ObjectIntersectionFact,
) (ObjectIntersectionFact, bool) {
	for _, fact := range facts {
		if strings.TrimSpace(fact.PrimaryText) != "" {
			return fact, true
		}
	}
	return ObjectIntersectionFact{}, false
}

func normalizedConnectionState(value string) string {
	switch strings.TrimSpace(value) {
	case ConnectionStateConnected:
		return ConnectionStateConnected
	case ConnectionStateUnconnected:
		return ConnectionStateUnconnected
	case ConnectionStateIntersectionLead:
		return ConnectionStateIntersectionLead
	default:
		return ConnectionStateIntersectionLead
	}
}

func normalizedExistingConnectionState(value string) string {
	switch strings.TrimSpace(value) {
	case ConnectionStateConnected:
		return ConnectionStateConnected
	case ConnectionStateIntersectionLead:
		return ConnectionStateIntersectionLead
	default:
		return ConnectionStateUnconnected
	}
}

func resolveConnectionState(
	target rtsearch.Target,
	existing string,
	factState string,
	sourceRefs []string,
) string {
	if existing == ConnectionStateConnected {
		return ConnectionStateConnected
	}
	if normalizedConnectionState(factState) == ConnectionStateConnected {
		return ConnectionStateConnected
	}
	for _, sourceRef := range sourceRefs {
		if sourceProvesDirectConnection(target, sourceRef) {
			return ConnectionStateConnected
		}
	}
	return ConnectionStateIntersectionLead
}

// sourceProvesDirectConnection 只把能够证明 viewer 已对当前命中对象建立关系或
// 发生互动的证据映射为 connected。共同关注、共同联系人等仅说明“有交集”，
// 不能被误报为已关注/已加入/已互动。
func sourceProvesDirectConnection(target rtsearch.Target, sourceRef string) bool {
	sourceRef = strings.TrimSpace(sourceRef)
	switch target {
	case rtsearch.TargetArticle, rtsearch.TargetPhoto, rtsearch.TargetVideo:
		switch sourceRef {
		case "coCommented", "coSharedContent", "coCreatedContent":
			return true
		}
	case rtsearch.TargetEntity, rtsearch.TargetLocation:
		switch sourceRef {
		case "coVisitedEntity", "coWishlistedEntity", "sharedEntityAttention":
			return true
		}
	case rtsearch.TargetCircle, rtsearch.TargetGroup:
		return sourceRef == "coMemberCircle"
	}
	return false
}

func appendUniqueDegradeSignal(
	signals []rtsearch.DegradeSignal,
	signal rtsearch.DegradeSignal,
) []rtsearch.DegradeSignal {
	for _, existing := range signals {
		if existing.Code == signal.Code {
			return signals
		}
	}
	return append(signals, signal)
}

func attachErrorType(err error) string {
	if err == nil {
		return ""
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return "deadline_exceeded"
	}
	if errors.Is(err, context.Canceled) {
		return "canceled"
	}
	return "dependency_error"
}
