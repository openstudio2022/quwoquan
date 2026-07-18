package application

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtimpact "quwoquan_service/runtime/impact"
	messaging "quwoquan_service/runtime/messaging"
	rtobs "quwoquan_service/runtime/observability"
	rtsearch "quwoquan_service/runtime/search"
	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
)

// EventPublisher is the runtime-compatible event publisher interface.
type EventPublisher = messaging.EventPublisher

type noopPublisher struct{}

func (noopPublisher) Publish(_ context.Context, _ messaging.DomainEvent) error { return nil }

// CircleService encapsulates the Circle aggregate CRUD/read surface.
type CircleService struct {
	records   CircleRecordStore
	sections  CircleSectionStore
	feedStore CircleFeedStore
	ids       EntityIDGenerator
	events    EventPublisher
}

type CircleServiceOption func(*CircleService)

func WithEventPublisher(ep EventPublisher) CircleServiceOption {
	return func(s *CircleService) { s.events = ep }
}

func WithFeedStore(fs CircleFeedStore) CircleServiceOption {
	return func(s *CircleService) { s.feedStore = fs }
}

func NewCircleService(
	storage CircleStoragePorts,
	opts ...CircleServiceOption,
) *CircleService {
	s := &CircleService{
		records: storage.Records, sections: storage.Sections,
		ids: storage.IDs, events: noopPublisher{},
	}
	for _, o := range opts {
		o(s)
	}
	return s
}

func (s *CircleService) publishEvent(ctx context.Context, eventType string, aggregateID string, payload map[string]any) {
	s.events.Publish(ctx, messaging.DomainEvent{
		Type:          eventType,
		AggregateType: "Circle",
		AggregateID:   aggregateID,
		Payload:       payload,
		OccurredAt:    time.Now().Format(time.RFC3339),
	})
}

// --- Circle CRUD ---

type CreateCircleRequest struct {
	Name        string   `json:"name"`
	Description string   `json:"description"`
	CoverUrl    string   `json:"coverUrl"`
	Category    string   `json:"category"`
	Tags        []string `json:"tags"`
	Visibility  string   `json:"visibility"`
	JoinPolicy  string   `json:"joinPolicy"`
	OwnerID     string
}

func (s *CircleService) CreateCircle(ctx context.Context, req CreateCircleRequest) (circle *model.Circle, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.CreateCircle",
		attribute.String("circle.owner_id", req.OwnerID),
		attribute.String("circle.visibility", req.Visibility))
	defer func() { rtobs.EndSpan(span, err) }()

	if req.Name == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleCircle, "圈子名称不能为空", "missing name")
	}

	now := time.Now()
	id, err := generateEntityID(s.ids)
	if err != nil {
		return nil, err
	}

	visibility := model.CircleVisibilityPublic
	if req.Visibility == "private" {
		visibility = model.CircleVisibilityPrivate
	}
	joinPolicy := model.CircleJoinPolicyOpen
	if req.JoinPolicy == "approval" {
		joinPolicy = model.CircleJoinPolicyApproval
	} else if req.JoinPolicy == "invite_only" {
		joinPolicy = model.CircleJoinPolicyInviteOnly
	}

	defaultQuota := int64(1024 * 1024 * 1024) // 1 GB
	circle = &model.Circle{
		ID:                id,
		Name:              req.Name,
		Description:       req.Description,
		CoverUrl:          req.CoverUrl,
		OwnerID:           req.OwnerID,
		Category:          req.Category,
		Tags:              req.Tags,
		MemberCount:       0,
		Status:            model.CircleStatusActive,
		Visibility:        visibility,
		JoinPolicy:        joinPolicy,
		AutoSyncChat:      true,
		StorageQuotaBytes: defaultQuota,
		SectionConfig: []model.CircleSectionConfig{
			{SectionType: model.CircleSectionTypeWorks, Visible: true, Order: 0},
			{SectionType: model.CircleSectionTypeChat, Visible: true, Order: 1},
			{SectionType: model.CircleSectionTypeStorage, Visible: true, Order: 2},
			{SectionType: model.CircleSectionTypeInteraction, Visible: true, Order: 3},
		},
		DomainID:  req.Category,
		CreatedAt: now,
		UpdatedAt: now,
	}

	if err := s.records.Create(ctx, circle); err != nil {
		return nil, fmt.Errorf("create circle: %w", err)
	}

	s.publishEvent(ctx, "CircleCreated", id, map[string]any{
		"id": id, "name": req.Name, "ownerId": req.OwnerID,
		"category": req.Category, "tags": req.Tags,
	})

	return circle, nil
}

func (s *CircleService) GetCircle(ctx context.Context, circleID string) (*model.Circle, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.GetCircle",
		attribute.String("circle.id", circleID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	c, ok := s.records.FindByID(ctx, circleID)
	if !ok {
		err = rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"圈子不存在", "circle not found",
		)
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

func (s *CircleService) UpdateCircle(ctx context.Context, circleID string, data map[string]any) (c *model.Circle, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.UpdateCircle",
		attribute.String("circle.id", circleID))
	defer func() { rtobs.EndSpan(span, err) }()

	c, ok := s.records.FindByID(ctx, circleID)
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"圈子不存在", "circle not found",
		)
	}

	if v, ok := data["name"].(string); ok && v != "" {
		c.Name = v
	}
	if v, ok := data["description"].(string); ok {
		c.Description = v
	}
	if v, ok := data["coverUrl"].(string); ok {
		c.CoverUrl = v
	}
	if v, ok := data["category"].(string); ok {
		c.Category = v
	}

	if !s.records.Update(ctx, circleID, c) {
		return nil, fmt.Errorf("update circle failed")
	}

	s.publishEvent(ctx, "CircleUpdated", circleID, map[string]any{
		"id": circleID, "name": c.Name, "description": c.Description,
	})

	return c, nil
}

func (s *CircleService) ArchiveCircle(ctx context.Context, circleID string) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.ArchiveCircle",
		attribute.String("circle.id", circleID))
	defer func() { rtobs.EndSpan(span, err) }()

	if !s.records.Archive(ctx, circleID) {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"圈子不存在", "circle not found",
		)
	}
	s.publishEvent(ctx, "CircleArchived", circleID, map[string]any{"id": circleID, "status": "archived"})
	return nil
}

// --- Stats ---

func (s *CircleService) GetCircleStats(ctx context.Context, circleID string) (_ map[string]any, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.GetCircleStats",
		attribute.String("circle.id", circleID))
	defer func() { rtobs.EndSpan(span, err) }()

	c, ok := s.records.FindByID(ctx, circleID)
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"圈子不存在", "circle not found",
		)
	}
	return map[string]any{
		"totalMembers":      c.MemberCount,
		"weeklyActive":      c.WeeklyActiveCount,
		"totalPosts":        c.PostCount,
		"totalDiscussions":  0,
		"storageUsedBytes":  c.StorageUsedBytes,
		"storageQuotaBytes": c.StorageQuotaBytes,
	}, nil
}

func (s *CircleService) GetCircleImpact(ctx context.Context, circleID string) (_ map[string]any, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.GetCircleImpact",
		attribute.String("circle.id", circleID))
	defer func() { rtobs.EndSpan(span, err) }()

	c, ok := s.records.FindByID(ctx, circleID)
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"圈子不存在", "circle not found",
		)
	}
	items := make([]rtimpact.Statement, 0, 1)
	if item, complete := buildCircleMemberImpact(c); complete {
		items = append(items, item)
	}
	total := int64(0)
	for _, item := range items {
		total += item.Count
	}
	return map[string]any{
		"circleId": circleID,
		"total":    total,
		"items":    items,
	}, nil
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

func (s *CircleService) GetCircleFeed(ctx context.Context, circleID string, limit int, cursor string, sort string) ([]map[string]any, string) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.GetCircleFeed",
		attribute.String("circle.id", circleID),
		attribute.String("feed.sort", sort))
	defer func() { rtobs.EndSpan(span, nil) }()

	if s.feedStore == nil {
		return []map[string]any{}, ""
	}
	items, nextCursor := s.feedStore.ListCirclePosts(ctx, circleID, ListCirclePostsQuery{
		Sort:   sort,
		Cursor: cursor,
		Limit:  limit,
	})
	projected := make([]map[string]any, 0, len(items))
	for _, item := range items {
		projected = append(projected, projectCircleFeedItem(item))
	}
	return projected, nextCursor
}

func projectCircleFeedItem(item map[string]any) map[string]any {
	if item == nil {
		return nil
	}
	out := make(map[string]any, len(item))
	for key, value := range item {
		if key == "_id" {
			continue
		}
		out[key] = value
	}
	if _, ok := out["postId"]; !ok {
		if id, ok := item["_id"]; ok {
			out["postId"] = id
		}
	}
	return out
}

// --- Feed management ---

func (s *CircleService) PinPost(ctx context.Context, circleID, postID string, pinned bool) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.PinPost",
		attribute.String("circle.id", circleID),
		attribute.String("post.id", postID))
	defer func() { rtobs.EndSpan(span, err) }()

	if s.feedStore == nil {
		return rterr.NewUnavailable(rterr.ModuleCircle, "圈子动态暂不可用", "circle feed store unavailable")
	}
	ok, updateErr := s.feedStore.UpdateCirclePostPinned(ctx, circleID, postID, pinned)
	if updateErr != nil {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindSystem, "feed_update_failed"),
			"圈子动态更新失败", updateErr.Error(),
		)
	}
	if !ok {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"帖子不存在", "circle post not found",
		)
	}
	s.publishEvent(ctx, "CirclePostPinned", postID, map[string]any{
		"circleId": circleID, "postId": postID, "pinned": pinned,
	})
	return nil
}

func (s *CircleService) FeaturePost(ctx context.Context, circleID, postID string, featured bool) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.FeaturePost",
		attribute.String("circle.id", circleID),
		attribute.String("post.id", postID))
	defer func() { rtobs.EndSpan(span, err) }()

	if s.feedStore == nil {
		return rterr.NewUnavailable(rterr.ModuleCircle, "圈子动态暂不可用", "circle feed store unavailable")
	}
	ok, updateErr := s.feedStore.UpdateCirclePostFeatured(ctx, circleID, postID, featured)
	if updateErr != nil {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindSystem, "feed_update_failed"),
			"圈子动态更新失败", updateErr.Error(),
		)
	}
	if !ok {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"帖子不存在", "circle post not found",
		)
	}
	s.publishEvent(ctx, "CirclePostFeatured", postID, map[string]any{
		"circleId": circleID, "postId": postID, "featured": featured,
	})
	return nil
}

// --- Sections ---

func (s *CircleService) UpdateSections(ctx context.Context, circleID string, sections []model.CircleSectionConfig) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "circle.UpdateSections",
		attribute.String("circle.id", circleID),
		attribute.Int("sections.count", len(sections)))
	defer func() { rtobs.EndSpan(span, err) }()

	if err = s.sections.UpdateSections(ctx, circleID, sections); err != nil {
		return err
	}
	s.publishEvent(ctx, "CircleSectionsUpdated", circleID, map[string]any{
		"circleId": circleID, "sectionConfig": sections,
	})
	return nil
}
