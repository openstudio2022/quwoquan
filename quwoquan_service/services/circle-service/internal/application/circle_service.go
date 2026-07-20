package application

import (
	"context"
	"errors"
	"sort"
	"strings"

	"go.opentelemetry.io/otel/attribute"

	rtimpact "quwoquan_service/runtime/impact"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/operation"
	rtsearch "quwoquan_service/runtime/search"
	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
	generated "quwoquan_service/services/circle-service/internal/generated"
)

// CircleService 承载 Circle 聚合本体的具名查询 Reader/Slice。
// 写路径由 CircleCommandFacade + AggregateStore 承载，本服务不再持有写端口。
type CircleService struct {
	records       CircleRecordStore
	feedStore     CircleFeedStore
	discoveryFeed CircleDiscoveryFeedReader
}

type CircleServiceOption func(*CircleService)

func WithFeedStore(fs CircleFeedStore) CircleServiceOption {
	return func(s *CircleService) { s.feedStore = fs }
}

func WithDiscoveryFeedReader(reader CircleDiscoveryFeedReader) CircleServiceOption {
	return func(s *CircleService) { s.discoveryFeed = reader }
}

func NewCircleService(
	storage CircleStoragePorts,
	opts ...CircleServiceOption,
) *CircleService {
	s := &CircleService{records: storage.Records}
	for _, o := range opts {
		o(s)
	}
	return s
}

func (s *CircleService) GetCircle(ctx context.Context, circleID string) (*model.Circle, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.GetCircle",
		attribute.String("circle.id", circleID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	c, ok := s.records.FindByID(ctx, circleID)
	if !ok {
		err = generated.AppErrorFromCircleNotFound("circle not found")
		return nil, err
	}
	return c, nil
}

type ListCirclesRequest struct {
	Category     string
	DomainID     string
	RecommendFor string
	Sort         string
	Cursor       string
	Limit        int
}

type ListCirclesResponse struct {
	Items  []model.Circle `json:"items"`
	Cursor string         `json:"cursor,omitempty"`
}

func (s *CircleService) ListCircles(ctx context.Context, req ListCirclesRequest) ListCirclesResponse {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.ListCircles",
		attribute.String("list.category", req.Category),
		attribute.Int("list.limit", req.Limit))
	defer func() { rtobs.EndSpan(span, nil) }()

	circles, cursor := s.records.List(ctx, ListCirclesQuery{
		Category:     req.Category,
		DomainID:     req.DomainID,
		RecommendFor: req.RecommendFor,
		Sort:         req.Sort,
		Cursor:       req.Cursor,
		Limit:        req.Limit,
	})
	if circles == nil {
		circles = []model.Circle{}
	}
	return ListCirclesResponse{Items: circles, Cursor: cursor}
}

type SearchCirclesRequest struct {
	Query       string
	CategoryID  string
	SubCategory string
	Cursor      string
	Limit       int
}

// CircleSearchItemWire aligns with contracts/metadata/social/circle/fields.yaml CircleSearchItemView.
type CircleSearchItemWire struct {
	CircleID            string `json:"circleId"`
	Name                string `json:"name"`
	Description         string `json:"description,omitempty"`
	CoverURL            string `json:"coverUrl,omitempty"`
	CategoryID          string `json:"categoryId,omitempty"`
	SubCategory         string `json:"subCategory,omitempty"`
	DomainID            string `json:"domainId,omitempty"`
	Kind                string `json:"kind,omitempty"`
	DisplaySubjectType  string `json:"displaySubjectType,omitempty"`
	MemberCount         int64  `json:"memberCount"`
	PostCount           int64  `json:"postCount"`
	HighlightText       string `json:"highlightText,omitempty"`
	MatchedField        string `json:"matchedField,omitempty"`
	LinkedHomepageID    string `json:"linkedHomepageId,omitempty"`
	LinkedHomepageType  string `json:"linkedHomepageType,omitempty"`
	LinkedHomepageTitle string `json:"linkedHomepageTitle,omitempty"`
}

// CircleFacetBucketWire aligns with CircleFacetBucketView.
type CircleFacetBucketWire struct {
	FacetKey    string `json:"facetKey"`
	Label       string `json:"label"`
	CategoryID  string `json:"categoryId,omitempty"`
	SubCategory string `json:"subCategory,omitempty"`
	FacetCount  int64  `json:"facetCount"`
}

type SearchCirclesResponse struct {
	Items        []CircleSearchItemWire  `json:"items"`
	FacetBuckets []CircleFacetBucketWire `json:"facetBuckets"`
	Cursor       string                  `json:"cursor,omitempty"`
}

func (s *CircleService) SearchCircles(
	ctx context.Context,
	req SearchCirclesRequest,
) SearchCirclesResponse {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.SearchCircles",
		attribute.String("search.query", req.Query),
		attribute.String("search.category_id", req.CategoryID))
	defer func() { rtobs.EndSpan(span, nil) }()

	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}
	listResp := s.ListCircles(ctx, ListCirclesRequest{
		Category: req.CategoryID,
		Cursor:   req.Cursor,
		Limit:    limit * 8,
	})
	query := strings.TrimSpace(req.Query)
	type indexedCircle struct {
		circle     model.Circle
		categoryID string
	}
	index := map[string]indexedCircle{}
	docs := make([]rtsearch.Document, 0, len(listResp.Items))
	facetCounts := map[string]int{}
	for _, circle := range listResp.Items {
		categoryID := circleSearchCategoryID(circle)
		facetCounts[categoryID]++
		index[circle.ID] = indexedCircle{circle: circle, categoryID: categoryID}
		docs = append(docs, ProjectCircleToSearchDocument(circle))
	}
	searchResp := rtsearch.Execute(rtsearch.Request{
		Query:       query,
		Mode:        rtsearch.ModeResult,
		ObjectTypes: []string{rtsearch.ObjectTypeCircle},
		Limit:       limit,
	}, docs)
	items := make([]CircleSearchItemWire, 0, len(searchResp.Hits))
	for _, hit := range searchResp.Hits {
		indexed, ok := index[hit.ObjectID]
		if !ok {
			continue
		}
		circle := indexed.circle
		categoryID := indexed.categoryID
		items = append(items, CircleSearchItemWire{
			CircleID:            circle.ID,
			Name:                circle.Name,
			Description:         circle.Description,
			CoverURL:            circle.CoverUrl,
			CategoryID:          categoryID,
			SubCategory:         "",
			DomainID:            circle.DomainID,
			Kind:                string(circle.Kind),
			DisplaySubjectType:  string(circle.DisplaySubjectType),
			MemberCount:         circle.MemberCount,
			PostCount:           circle.PostCount,
			HighlightText:       hit.Snippet,
			MatchedField:        hit.MatchedField,
			LinkedHomepageID:    circle.LinkedHomepageID,
			LinkedHomepageType:  string(circle.LinkedHomepageType),
			LinkedHomepageTitle: circle.LinkedHomepageTitle,
		})
	}
	facetKeys := make([]string, 0, len(facetCounts))
	for key := range facetCounts {
		facetKeys = append(facetKeys, key)
	}
	sort.Strings(facetKeys)
	facetBuckets := make([]CircleFacetBucketWire, 0, len(facetKeys))
	for _, key := range facetKeys {
		facetBuckets = append(facetBuckets, CircleFacetBucketWire{
			FacetKey:    key,
			Label:       key,
			CategoryID:  key,
			SubCategory: "",
			FacetCount:  int64(facetCounts[key]),
		})
	}
	cursor := ""
	if len(items) == limit {
		cursor = items[len(items)-1].CircleID
	}
	return SearchCirclesResponse{
		Items:        items,
		FacetBuckets: facetBuckets,
		Cursor:       cursor,
	}
}

// --- Stats ---

// CircleStatsWire 是 GetCircleStats 的稳定回读投影，键集合与
// contracts/metadata/social/circle/projections/circle_stats_wire.yaml 对齐。
type CircleStatsWire struct {
	TotalMembers      int64 `json:"totalMembers"`
	WeeklyActive      int64 `json:"weeklyActive"`
	TotalPosts        int64 `json:"totalPosts"`
	TotalDiscussions  int64 `json:"totalDiscussions"`
	StorageUsedBytes  int64 `json:"storageUsedBytes"`
	StorageQuotaBytes int64 `json:"storageQuotaBytes"`
}

func (s *CircleService) GetCircleStats(ctx context.Context, circleID string) (CircleStatsWire, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.GetCircleStats",
		attribute.String("circle.id", circleID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	c, ok := s.records.FindByID(ctx, circleID)
	if !ok {
		err = generated.AppErrorFromCircleNotFound("circle not found")
		return CircleStatsWire{}, err
	}
	return CircleStatsWire{
		TotalMembers:      c.MemberCount,
		WeeklyActive:      c.WeeklyActiveCount,
		TotalPosts:        c.PostCount,
		TotalDiscussions:  0,
		StorageUsedBytes:  c.StorageUsedBytes,
		StorageQuotaBytes: c.StorageQuotaBytes,
	}, nil
}

// CircleImpactSummaryWire 是 GetCircleImpact 的稳定回读投影。
type CircleImpactSummaryWire struct {
	CircleID string               `json:"circleId"`
	Total    int64                `json:"total"`
	Items    []rtimpact.Statement `json:"items"`
}

func (s *CircleService) GetCircleImpact(ctx context.Context, circleID string) (CircleImpactSummaryWire, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.GetCircleImpact",
		attribute.String("circle.id", circleID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	c, ok := s.records.FindByID(ctx, circleID)
	if !ok {
		err = generated.AppErrorFromCircleNotFound("circle not found")
		return CircleImpactSummaryWire{}, err
	}
	items := make([]rtimpact.Statement, 0, 1)
	if item, complete := buildCircleMemberImpact(c); complete {
		items = append(items, item)
	}
	total := int64(0)
	for _, item := range items {
		total += item.Count
	}
	return CircleImpactSummaryWire{CircleID: circleID, Total: total, Items: items}, nil
}

// buildCircleMemberImpact only publishes the member fact because the owner is
// part of that persisted member set. PostCount and WeeklyActiveCount do not
// carry an actor evidence snapshot and therefore cannot be converted into a
// user-facing sentence on this read path.
func buildCircleMemberImpact(c *model.Circle) (rtimpact.Statement, bool) {
	if c == nil {
		return rtimpact.Statement{}, false
	}
	ownerID := strings.TrimSpace(c.OwnerID)
	ownerName := strings.TrimSpace(c.OwnerDisplayNameSnapshot)
	circleID := strings.TrimSpace(c.ID)
	circleName := strings.TrimSpace(c.Name)
	snapshotID := "circle:" + circleID + ":members:v1"
	return rtimpact.BuildStatement(rtimpact.StatementEvidence{
		HelpType:              rtimpact.HelpCommunity,
		Action:                "join_circle",
		IntersectionDimension: "relationship",
		Source:                "circle_members",
		Count:                 c.MemberCount,
		SubtitleText:          "成员事实来自圈子成员读模型快照。",
		ImpactID:              circleID + "_members",
		EvidenceSnapshotID:    snapshotID,
		RepresentativeActor: rtimpact.RepresentativeActor{
			ActorID:         ownerID,
			DisplayName:     ownerName,
			RelationLabel:   "圈子主理人",
			PrivacyState:    "visible",
			Target:          &rtimpact.Target{ObjectType: "user", ObjectID: ownerID, ObjectKind: "person", RouteID: "profile"},
			EvidenceRank:    1,
			SnapshotVersion: snapshotID,
		},
		ObjectName:      circleName,
		ObjectTarget:    rtimpact.Target{ObjectType: "circle", ObjectID: circleID, ObjectKind: "circle", RouteID: "circleDetail"},
		ObjectVisualURL: strings.TrimSpace(c.IconUrl),
	})
}

// --- Feed ---

func (s *CircleService) GetCircleFeed(
	ctx context.Context,
	circleID string,
	limit int,
	cursor string,
	sort string,
	identity string,
	contentType string,
) (CircleFeedSlice, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.GetCircleFeed",
		attribute.String("circle.id", circleID),
		attribute.String("feed.sort", sort))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	if s.feedStore == nil {
		err = generated.AppErrorFromInternalError("circle feed reader is not configured")
		return CircleFeedSlice{}, err
	}
	items, nextCursor, readErr := s.feedStore.ListCirclePosts(ctx, circleID, ListCirclePostsQuery{
		Identity: identity,
		Type:     contentType,
		Sort:     sort,
		Cursor:   cursor,
		Limit:    limit,
	})
	if readErr != nil {
		if errors.Is(readErr, ErrInvalidCircleFeedCursor) {
			err = generated.AppErrorFromInvalidArgument(readErr.Error())
			return CircleFeedSlice{}, err
		}
		err = generated.AppErrorFromInternalError(readErr.Error())
		return CircleFeedSlice{}, err
	}
	if items == nil {
		items = []CircleFeedPost{}
	}
	return CircleFeedSlice{Items: items, Cursor: nextCursor}, nil
}

func (s *CircleService) ListCircleDiscoveryFeed(
	ctx context.Context,
	query CircleDiscoveryFeedQuery,
) (CircleDiscoveryFeedSlice, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.ListCircleDiscoveryFeed",
		attribute.String("feed.category", query.Category),
		attribute.String("feed.scope", string(query.Scope)),
		attribute.String("feed.sort", query.Sort))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	if s.discoveryFeed == nil {
		err = generated.AppErrorFromInternalError("circle discovery feed reader is not configured")
		return CircleDiscoveryFeedSlice{}, err
	}
	if query.Scope == "" {
		query.Scope = CircleDiscoveryFeedScopeRecommended
	}
	if query.Scope != CircleDiscoveryFeedScopeRecommended &&
		query.Scope != CircleDiscoveryFeedScopeMine {
		err = generated.AppErrorFromInvalidArgument("scope must be recommended or mine")
		return CircleDiscoveryFeedSlice{}, err
	}
	if query.Limit <= 0 || query.Limit > 200 {
		err = generated.AppErrorFromInvalidArgument("limit must be in 1..200")
		return CircleDiscoveryFeedSlice{}, err
	}
	if current, ok := operation.FromContext(ctx); ok {
		query.PersonaID = strings.TrimSpace(current.Actor.PersonaID)
	}
	if query.Scope == CircleDiscoveryFeedScopeMine && query.PersonaID == "" {
		return CircleDiscoveryFeedSlice{
			Circles: []model.Circle{},
			Items:   []CircleFeedPost{},
		}, nil
	}
	result, readErr := s.discoveryFeed.ListCircleDiscoveryFeed(ctx, query)
	if readErr != nil {
		err = generated.AppErrorFromInternalError(readErr.Error())
		return CircleDiscoveryFeedSlice{}, err
	}
	if result.Circles == nil {
		result.Circles = []model.Circle{}
	}
	if result.Items == nil {
		result.Items = []CircleFeedPost{}
	}
	return result, nil
}
