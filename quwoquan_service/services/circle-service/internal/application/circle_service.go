package application

import (
	"context"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/repository"
	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
	"quwoquan_service/services/circle-service/internal/infrastructure/persistence"
)

// EventPublisher is the runtime-compatible event publisher interface.
type EventPublisher = repository.EventPublisher

type noopPublisher struct{}

func (noopPublisher) Publish(_ context.Context, _ repository.DomainEvent) error { return nil }

// CircleService encapsulates circle CRUD, membership, stats, and behavior use cases.
type CircleService struct {
	circles   persistence.CircleStore
	members   persistence.MemberStore
	files     persistence.FileStore
	feedStore persistence.FeedStore
	events    EventPublisher
}

type CircleServiceOption func(*CircleService)

func WithEventPublisher(ep EventPublisher) CircleServiceOption {
	return func(s *CircleService) { s.events = ep }
}

func WithFeedStore(fs persistence.FeedStore) CircleServiceOption {
	return func(s *CircleService) { s.feedStore = fs }
}

func NewCircleService(
	circles persistence.CircleStore,
	members persistence.MemberStore,
	files persistence.FileStore,
	opts ...CircleServiceOption,
) *CircleService {
	s := &CircleService{
		circles: circles,
		members: members,
		files:   files,
		events:  noopPublisher{},
	}
	for _, o := range opts {
		o(s)
	}
	return s
}

func (s *CircleService) publishEvent(ctx context.Context, eventType string, aggregateID string, payload map[string]any) {
	s.events.Publish(ctx, repository.DomainEvent{
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

func (s *CircleService) CreateCircle(ctx context.Context, req CreateCircleRequest) (*model.Circle, error) {
	if req.Name == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleCircle, "圈子名称不能为空", "missing name")
	}

	now := time.Now()
	id := bson.NewObjectID().Hex()

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
	circle := &model.Circle{
		ID:                id,
		Name:              req.Name,
		Description:       req.Description,
		CoverUrl:          req.CoverUrl,
		OwnerID:           req.OwnerID,
		Category:          req.Category,
		Tags:              req.Tags,
		MemberCount:       1,
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

	if err := s.circles.Create(ctx, circle); err != nil {
		return nil, fmt.Errorf("create circle: %w", err)
	}

	ownerMember := &model.CircleMember{
		ID:       bson.NewObjectID().Hex(),
		CircleID: id,
		UserID:   req.OwnerID,
		Role:     model.CircleMemberRoleOwner,
		JoinedAt: now,
	}
	if err := s.members.Create(ctx, ownerMember); err != nil {
		return nil, fmt.Errorf("create owner member: %w", err)
	}

	s.publishEvent(ctx, "CircleCreated", id, map[string]any{
		"_id": id, "name": req.Name, "ownerId": req.OwnerID,
		"category": req.Category, "tags": req.Tags,
	})

	return circle, nil
}

func (s *CircleService) GetCircle(ctx context.Context, circleID string) (*model.Circle, error) {
	c, ok := s.circles.FindByID(ctx, circleID)
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"圈子不存在", "circle not found", false,
		)
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
	circles, cursor := s.circles.List(ctx, persistence.ListCirclesOpts{
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

func (s *CircleService) UpdateCircle(ctx context.Context, circleID string, data map[string]any) (*model.Circle, error) {
	c, ok := s.circles.FindByID(ctx, circleID)
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"圈子不存在", "circle not found", false,
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

	if !s.circles.Update(ctx, circleID, c) {
		return nil, fmt.Errorf("update circle failed")
	}

	s.publishEvent(ctx, "CircleUpdated", circleID, map[string]any{
		"_id": circleID, "name": c.Name, "description": c.Description,
	})

	return c, nil
}

func (s *CircleService) ArchiveCircle(ctx context.Context, circleID string) error {
	if !s.circles.Archive(ctx, circleID) {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"圈子不存在", "circle not found", false,
		)
	}
	s.publishEvent(ctx, "CircleArchived", circleID, map[string]any{"_id": circleID, "status": "archived"})
	return nil
}

// --- Membership ---

func (s *CircleService) JoinCircle(ctx context.Context, circleID, userID string) error {
	c, ok := s.circles.FindByID(ctx, circleID)
	if !ok {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"圈子不存在", "circle not found", false,
		)
	}

	if _, exists := s.members.FindByCircleAndUser(ctx, circleID, userID); exists {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "conflict"),
			"您已经是该圈子成员", "already a member", false,
		)
	}

	if c.JoinPolicy == model.CircleJoinPolicyApproval {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "forbidden"),
			"该圈子需要审批才能加入", "join approval required", false,
		)
	}

	member := &model.CircleMember{
		ID:       bson.NewObjectID().Hex(),
		CircleID: circleID,
		UserID:   userID,
		Role:     model.CircleMemberRoleMember,
		JoinedAt: time.Now(),
	}
	if err := s.members.Create(ctx, member); err != nil {
		return fmt.Errorf("create member: %w", err)
	}

	if err := s.circles.IncrementMemberCount(ctx, circleID, 1); err != nil {
		return fmt.Errorf("increment member count: %w", err)
	}

	s.publishEvent(ctx, "CircleMemberJoined", circleID, map[string]any{
		"circleId": circleID, "userId": userID, "role": "member",
	})
	return nil
}

func (s *CircleService) LeaveCircle(ctx context.Context, circleID, userID string) error {
	member, ok := s.members.FindByCircleAndUser(ctx, circleID, userID)
	if !ok {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "forbidden"),
			"您不是该圈子成员", "not a member", false,
		)
	}

	if member.Role == model.CircleMemberRoleOwner {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "forbidden"),
			"圈主不能退出圈子", "owner cannot leave", false,
		)
	}

	if !s.members.Delete(ctx, circleID, userID) {
		return fmt.Errorf("delete member failed")
	}

	if err := s.circles.IncrementMemberCount(ctx, circleID, -1); err != nil {
		return fmt.Errorf("decrement member count: %w", err)
	}

	s.publishEvent(ctx, "CircleMemberLeft", circleID, map[string]any{
		"circleId": circleID, "userId": userID,
	})
	return nil
}

func (s *CircleService) ListMembers(ctx context.Context, circleID string, limit int, cursor string) ([]model.CircleMember, string) {
	return s.members.ListByCircle(ctx, circleID, limit, cursor)
}

func (s *CircleService) ListUserCircles(ctx context.Context, userID string, limit int, cursor string) ([]model.Circle, string) {
	memberships, _ := s.members.ListByUser(ctx, userID, limit, cursor)
	var circles []model.Circle
	for _, m := range memberships {
		if c, ok := s.circles.FindByID(ctx, m.CircleID); ok {
			circles = append(circles, *c)
		}
	}
	var nextCursor string
	if len(memberships) == limit && len(memberships) > 0 {
		nextCursor = memberships[len(memberships)-1].ID
	}
	return circles, nextCursor
}

func (s *CircleService) UpdateMemberRole(ctx context.Context, circleID, userID string, role string) error {
	memberRole := model.CircleMemberRole(role)
	if memberRole != model.CircleMemberRoleAdmin && memberRole != model.CircleMemberRoleMember {
		return rterr.NewInvalidArgument(rterr.ModuleCircle, "无效的角色", "invalid role: "+role)
	}

	if !s.members.UpdateRole(ctx, circleID, userID, memberRole) {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"成员不存在", "member not found", false,
		)
	}
	return nil
}

// --- Stats ---

func (s *CircleService) GetCircleStats(ctx context.Context, circleID string) (map[string]any, error) {
	c, ok := s.circles.FindByID(ctx, circleID)
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"圈子不存在", "circle not found", false,
		)
	}
	return map[string]any{
		"totalMembers":      c.MemberCount,
		"weeklyActive":      c.WeeklyActiveCount,
		"totalPosts":        c.PostCount,
		"storageUsedBytes":  c.StorageUsedBytes,
		"storageQuotaBytes": c.StorageQuotaBytes,
	}, nil
}

// --- Feed ---

func (s *CircleService) GetCircleFeed(ctx context.Context, circleID string, limit int, cursor string, sort string) ([]map[string]any, string) {
	if s.feedStore == nil {
		return []map[string]any{}, ""
	}
	return s.feedStore.ListCirclePosts(ctx, circleID, persistence.ListCirclePostsOpts{
		Sort:   sort,
		Cursor: cursor,
		Limit:  limit,
	})
}

// --- Feed management ---

func (s *CircleService) PinPost(_ context.Context, _, _ string, _ bool) error {
	return nil
}

func (s *CircleService) FeaturePost(_ context.Context, _, _ string, _ bool) error {
	return nil
}

// --- Sections ---

func (s *CircleService) UpdateSections(ctx context.Context, circleID string, sections []model.CircleSectionConfig) error {
	if err := s.circles.UpdateSections(ctx, circleID, sections); err != nil {
		return err
	}
	s.publishEvent(ctx, "CircleSectionsUpdated", circleID, map[string]any{
		"circleId": circleID, "sectionConfig": sections,
	})
	return nil
}

// --- Behavior ---

func (s *CircleService) ReportBehavior(ctx context.Context, report map[string]any) error {
	s.publishEvent(ctx, "CircleBehaviorReported", "", report)
	return nil
}
