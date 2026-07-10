package application

import (
	"context"
	"errors"
	"fmt"
	"go.opentelemetry.io/otel/attribute"
	rtimpact "quwoquan_service/runtime/impact"
	rtobs "quwoquan_service/runtime/observability"
	rtsearch "quwoquan_service/runtime/search"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const (
	codeHomepageNotFound     = "ENTITY.USER.homepage_not_found"
	codeClaimMaterialMissing = "ENTITY.USER.claim_material_missing"
	codeAlreadyClaimed       = "ENTITY.USER.already_claimed"
	codeHomepageOffline      = "ENTITY.USER.homepage_offline"
	codeInvalidHomepageType  = "ENTITY.USER.invalid_homepage_type"
	codePermissionDenied     = "ENTITY.USER.permission_denied"
	codeInternalError        = "ENTITY.SYSTEM.internal_error"
)

type AppError struct {
	StatusCode   int    `json:"-"`
	Code         string `json:"code"`
	UserMessage  string `json:"userMessage"`
	DebugMessage string `json:"debugMessage,omitempty"`
}

func (e *AppError) Error() string {
	if e == nil {
		return ""
	}
	return e.Code + ": " + e.DebugMessage
}

type GeoPoint struct {
	Latitude  float64 `json:"latitude"`
	Longitude float64 `json:"longitude"`
}
type Homepage struct {
	ID                 string           `json:"_id"`
	Title              string           `json:"title"`
	Subtitle           string           `json:"subtitle,omitempty"`
	HomepageType       string           `json:"homepageType"`
	CanonicalEntityID  string           `json:"canonicalEntityId"`
	ObjectPageTemplate string           `json:"objectPageTemplate"`
	Status             string           `json:"status"`
	SourceType         string           `json:"sourceType"`
	ClaimStatus        string           `json:"claimStatus"`
	CategoryTags       []string         `json:"categoryTags,omitempty"`
	CoverURL           string           `json:"coverUrl,omitempty"`
	Address            string           `json:"address,omitempty"`
	City               string           `json:"city,omitempty"`
	Location           *GeoPoint        `json:"location,omitempty"`
	OwnerUserID        string           `json:"ownerUserId,omitempty"`
	OwnerSubAccountID  string           `json:"ownerSubAccountId,omitempty"`
	ViewerFollows      bool             `json:"viewerFollowsHomepage"`
	FollowerCount      int              `json:"followerCount"`
	AverageRating      *float64         `json:"averageRating,omitempty"`
	RatingCount        int              `json:"ratingCount"`
	ReviewSummary      map[string]any   `json:"reviewSummary,omitempty"`
	ContentPreview     []map[string]any `json:"contentPreview,omitempty"`
	QuestionPreview    []map[string]any `json:"questionPreview,omitempty"`
	RelatedGroups      []map[string]any `json:"relatedGroups,omitempty"`
	RelationEdges      []map[string]any `json:"relationEdges,omitempty"`
	AssistantContext   map[string]any   `json:"assistantContext,omitempty"`
	// 数据工程实体主页三件套投影承载：page.md 三段结构正文与图片资产
	// （封面 frontmatter / 正文块级内嵌图 / 页尾相关图片），见
	// contracts/metadata/entity/homepage/projections/*.yaml。
	IntroductionMarkdown string                      `json:"introductionMarkdown,omitempty"`
	IntroductionAssets   []HomepageIntroductionAsset `json:"introductionAssets,omitempty"`
	CreatedAt            time.Time                   `json:"createdAt"`
	UpdatedAt            time.Time                   `json:"updatedAt"`
	PublishedAt          *time.Time                  `json:"publishedAt,omitempty"`
	OfflineAt            *time.Time                  `json:"offlineAt,omitempty"`
}
type HomepageSearchItemView struct {
	HomepageID        string   `json:"homepageId"`
	CanonicalEntityID string   `json:"canonicalEntityId"`
	Title             string   `json:"title"`
	Subtitle          string   `json:"subtitle,omitempty"`
	HomepageType      string   `json:"homepageType"`
	CoverURL          string   `json:"coverUrl,omitempty"`
	City              string   `json:"city,omitempty"`
	Address           string   `json:"address,omitempty"`
	Status            string   `json:"status"`
	AverageRating     *float64 `json:"averageRating,omitempty"`
	RatingCount       int      `json:"ratingCount"`
}

type HomepageShellView struct {
	Homepage        Homepage         `json:"homepage"`
	ReviewSummary   map[string]any   `json:"reviewSummary,omitempty"`
	ContentPreview  []map[string]any `json:"contentPreview,omitempty"`
	QuestionPreview []map[string]any `json:"questionPreview,omitempty"`
	RelatedGroups   []map[string]any `json:"relatedGroups,omitempty"`
}

type ObjectPageBundle struct {
	ObjectType          string           `json:"objectType"`
	ObjectID            string           `json:"objectId"`
	CanonicalEntityID   string           `json:"canonicalEntityId"`
	Title               string           `json:"title"`
	Subtitle            string           `json:"subtitle,omitempty"`
	CoverURL            string           `json:"coverUrl,omitempty"`
	ObjectPageTemplate  string           `json:"objectPageTemplate"`
	TagRefs             []string         `json:"tagRefs"`
	Stats               map[string]any   `json:"stats"`
	IntersectionReasons []map[string]any `json:"intersectionReasons"`
	HighlightItems      []map[string]any `json:"highlightItems"`
	ContentSections     map[string]any   `json:"contentSections"`
	RelatedObjects      []map[string]any `json:"relatedObjects"`
	RelationEdges       []map[string]any `json:"relationEdges"`
	AssistantContext    map[string]any   `json:"assistantContext,omitempty"`
	RolloutContext      map[string]any   `json:"rolloutContext,omitempty"`
}

type HomepageReviewSummaryView struct {
	AverageRating   *float64         `json:"averageRating,omitempty"`
	RatingCount     int              `json:"ratingCount"`
	HighlightTags   []string         `json:"highlightTags,omitempty"`
	DimensionScores []map[string]any `json:"dimensionScores,omitempty"`
}

type HomepageRelatedGroupSummaryView struct {
	Groups []map[string]any `json:"groups"`
}

type HomepageImpactSummaryView struct {
	HomepageID string           `json:"homepageId"`
	Total      int              `json:"total"`
	Items      []map[string]any `json:"items"`
}

type HomepageClaimRequest struct {
	ID                   string     `json:"_id"`
	HomepageID           string     `json:"homepageId"`
	RequesterUserID      string     `json:"requesterUserId"`
	ClaimTier            string     `json:"claimTier"`
	BusinessLicenseURL   string     `json:"businessLicenseUrl,omitempty"`
	ContactPhone         string     `json:"contactPhone,omitempty"`
	IdentityCardFrontURL string     `json:"identityCardFrontUrl,omitempty"`
	IdentityCardBackURL  string     `json:"identityCardBackUrl,omitempty"`
	Note                 string     `json:"note,omitempty"`
	Status               string     `json:"status"`
	ReviewNote           string     `json:"reviewNote,omitempty"`
	CreatedAt            time.Time  `json:"createdAt"`
	ReviewedAt           *time.Time `json:"reviewedAt,omitempty"`
}

type HomepageStatusReport struct {
	ID             string     `json:"_id"`
	HomepageID     string     `json:"homepageId"`
	ReporterUserID string     `json:"reporterUserId"`
	Reason         string     `json:"reason"`
	Description    string     `json:"description,omitempty"`
	EvidenceURLs   []string   `json:"evidenceUrls,omitempty"`
	Status         string     `json:"status"`
	ReviewNote     string     `json:"reviewNote,omitempty"`
	CreatedAt      time.Time  `json:"createdAt"`
	ReviewedAt     *time.Time `json:"reviewedAt,omitempty"`
}

type HomepageInput struct {
	Title              string    `json:"title"`
	Subtitle           string    `json:"subtitle"`
	HomepageType       string    `json:"homepageType"`
	CanonicalEntityID  string    `json:"canonicalEntityId"`
	ObjectPageTemplate string    `json:"objectPageTemplate"`
	CategoryTags       []string  `json:"categoryTags"`
	CoverURL           string    `json:"coverUrl"`
	Address            string    `json:"address"`
	City               string    `json:"city"`
	Location           *GeoPoint `json:"location"`
	// 数据工程 page.md 三段结构投影承载（service.yaml writable_fields 同源）。
	IntroductionMarkdown string                      `json:"introductionMarkdown"`
	IntroductionAssets   []HomepageIntroductionAsset `json:"introductionAssets"`
}

type ClaimRequestInput struct {
	RequesterUserID      string `json:"requesterUserId"`
	ClaimTier            string `json:"claimTier"`
	BusinessLicenseURL   string `json:"businessLicenseUrl"`
	ContactPhone         string `json:"contactPhone"`
	IdentityCardFrontURL string `json:"identityCardFrontUrl"`
	IdentityCardBackURL  string `json:"identityCardBackUrl"`
	Note                 string `json:"note"`
}

type ClaimReviewInput struct {
	Status     string `json:"status"`
	ReviewNote string `json:"reviewNote"`
}

type HomepageBasicInput struct {
	Title        string    `json:"title"`
	Subtitle     string    `json:"subtitle"`
	CategoryTags []string  `json:"categoryTags"`
	CoverURL     string    `json:"coverUrl"`
	Address      string    `json:"address"`
	City         string    `json:"city"`
	Location     *GeoPoint `json:"location"`
}

type StatusReportInput struct {
	ReporterUserID string   `json:"reporterUserId"`
	Reason         string   `json:"reason"`
	Description    string   `json:"description"`
	EvidenceURLs   []string `json:"evidenceUrls"`
}

type StatusReportReviewInput struct {
	Status     string `json:"status"`
	ReviewNote string `json:"reviewNote"`
}

type HomepageService struct {
	mu              sync.RWMutex
	store           HomepageStateStore
	homepages       map[string]*Homepage
	followers       map[string]map[string]bool
	claimRequests   map[string]*HomepageClaimRequest
	statusReports   map[string]*HomepageStatusReport
	sequence        uint64
	searchProjector Projector
}

// HomepageServiceOption configures optional HomepageService collaborators.
type HomepageServiceOption func(*HomepageService)

// WithProjector wires the write-time search-index projector. When unset (ES
// disabled) all search emits are no-ops and the write path is unaffected.
func WithProjector(projector Projector) HomepageServiceOption {
	return func(s *HomepageService) {
		if projector != nil {
			s.searchProjector = projector
		}
	}
}

type HomepageStateStore interface {
	Load(ctx context.Context) (*HomepageStateSnapshot, error)
	Save(ctx context.Context, snapshot HomepageStateSnapshot) error
}

type HomepageStateSnapshot struct {
	Homepages     []Homepage             `json:"homepages" bson:"homepages"`
	Followers     map[string][]string    `json:"followers" bson:"followers"`
	ClaimRequests []HomepageClaimRequest `json:"claimRequests" bson:"claimRequests"`
	StatusReports []HomepageStatusReport `json:"statusReports" bson:"statusReports"`
	Sequence      uint64                 `json:"sequence" bson:"sequence"`
	UpdatedAt     time.Time              `json:"updatedAt" bson:"updatedAt"`
}

func NewHomepageService() *HomepageService {
	return NewHomepageServiceWithStore(context.Background(), nil)
}

func NewHomepageServiceWithStore(ctx context.Context, store HomepageStateStore, opts ...HomepageServiceOption) *HomepageService {
	svc := &HomepageService{
		store:         store,
		homepages:     map[string]*Homepage{},
		followers:     map[string]map[string]bool{},
		claimRequests: map[string]*HomepageClaimRequest{},
		statusReports: map[string]*HomepageStatusReport{},
	}
	for _, opt := range opts {
		opt(svc)
	}
	loaded := false
	if store != nil {
		if snapshot, err := store.Load(ctx); err == nil && snapshot != nil && len(snapshot.Homepages) > 0 {
			svc.applySnapshot(snapshot)
			loaded = true
		}
	}
	if !loaded {
		svc.seed()
		_ = svc.persistLocked(ctx)
	}
	return svc
}

func (s *HomepageService) SearchHomepages(
	ctx context.Context,
	query string,
	homepageType string,
	city string,
	status string,
	limit int,
) []HomepageSearchItemView {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.SearchHomepages",
		attribute.String("search.query", query),
		attribute.String("homepage.type", homepageType))
	defer func() { rtobs.EndSpan(span, nil) }()

	s.mu.RLock()
	defer s.mu.RUnlock()
	filterType := normalize(homepageType)
	filterCity := normalize(city)
	filterStatus := normalize(status)
	if limit <= 0 || limit > 50 {
		limit = 20
	}

	index := map[string]*Homepage{}
	docs := make([]rtsearch.Document, 0, len(s.homepages))
	for _, homepage := range s.homepages {
		if filterType != "" && normalize(homepage.HomepageType) != filterType {
			continue
		}
		if filterCity != "" && normalize(homepage.City) != filterCity {
			continue
		}
		if filterStatus != "" {
			if normalize(homepage.Status) != filterStatus {
				continue
			}
		} else if homepage.Status != "published" {
			continue
		}
		index[homepage.ID] = homepage
		docs = append(docs, ProjectHomepageToSearchDocument(*homepage))
	}
	searchResp := rtsearch.Execute(rtsearch.Request{
		Query:       query,
		Mode:        rtsearch.ModeResult,
		ObjectTypes: []string{rtsearch.ObjectTypeEntityHomepage},
		Limit:       limit,
	}, docs)
	items := make([]HomepageSearchItemView, 0, len(searchResp.Hits))
	for _, hit := range searchResp.Hits {
		homepage, ok := index[hit.ObjectID]
		if !ok {
			continue
		}
		items = append(items, HomepageSearchItemView{
			HomepageID:        homepage.ID,
			CanonicalEntityID: homepage.CanonicalEntityID,
			Title:             homepage.Title,
			Subtitle:          homepage.Subtitle,
			HomepageType:      homepage.HomepageType,
			CoverURL:          homepage.CoverURL,
			City:              homepage.City,
			Address:           homepage.Address,
			Status:            homepage.Status,
			AverageRating:     homepage.AverageRating,
			RatingCount:       homepage.RatingCount,
		})
	}
	return items
}

func (s *HomepageService) IntakeHomepageCandidate(ctx context.Context, input HomepageInput, sourceType string) (_ *Homepage, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.IntakeHomepageCandidate",
		attribute.String("homepage.type", input.HomepageType),
		attribute.String("source.type", sourceType))
	defer func() { rtobs.EndSpan(span, err) }()

	if err = validateHomepageInput(input); err != nil {
		return nil, err
	}
	now := time.Now().UTC()
	id := s.nextID("homepage")
	homepage := &Homepage{
		ID:                 id,
		Title:              strings.TrimSpace(input.Title),
		Subtitle:           strings.TrimSpace(input.Subtitle),
		HomepageType:       strings.TrimSpace(input.HomepageType),
		CanonicalEntityID:  canonicalEntityID(id, input.CanonicalEntityID),
		ObjectPageTemplate: objectPageTemplate(input.HomepageType, input.ObjectPageTemplate),
		Status:             "candidate",
		SourceType:         sourceType,
		ClaimStatus:        "unclaimed",
		CategoryTags:       cloneStrings(input.CategoryTags),
		CoverURL:           strings.TrimSpace(input.CoverURL),
		Address:            strings.TrimSpace(input.Address),
		City:               strings.TrimSpace(input.City),
		Location:           cloneGeoPoint(input.Location),
		CreatedAt:          now,
		UpdatedAt:          now,
	}
	homepage.IntroductionMarkdown = strings.TrimSpace(input.IntroductionMarkdown)
	homepage.IntroductionAssets = cloneIntroductionAssets(input.IntroductionAssets)
	if homepage.CoverURL == "" {
		homepage.CoverURL = coverURLFromIntroductionAssets(homepage.IntroductionAssets)
	}
	s.mu.Lock()
	s.homepages[id] = homepage
	err = s.persistLocked(ctx)
	s.mu.Unlock()
	if err != nil {
		return nil, err
	}
	out := cloneHomepage(homepage)
	return &out, nil
}

func (s *HomepageService) SuggestHomepageCandidate(ctx context.Context, input HomepageInput) (*Homepage, error) {
	return s.IntakeHomepageCandidate(ctx, input, "user_suggested")
}

func (s *HomepageService) PublishHomepageCandidate(ctx context.Context, homepageID string) (*Homepage, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.PublishHomepageCandidate",
		attribute.String("homepage.id", homepageID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	// emit runs after s.mu is released (defer LIFO) so the ES round trip never
	// holds the homepage write lock.
	var emit *ProjectorEvent
	defer func() {
		if emit != nil {
			s.emitSearchIndex(ctx, *emit)
		}
	}()

	s.mu.Lock()
	defer s.mu.Unlock()
	homepage, ok := s.resolveHomepageLocked(homepageID)
	if !ok {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "homepage not found")
		return nil, err
	}
	now := time.Now().UTC()
	homepage.Status = "published"
	homepage.SourceType = "official_seed"
	homepage.UpdatedAt = now
	homepage.PublishedAt = &now
	if strings.TrimSpace(homepage.CanonicalEntityID) == "" {
		homepage.CanonicalEntityID = canonicalEntityIDFromTypeAndTitle(
			homepage.HomepageType,
			homepage.Title,
		)
	}
	applyDefaultShellData(homepage)
	if err = s.persistLocked(ctx); err != nil {
		return nil, err
	}
	out := cloneHomepage(homepage)
	emit = &ProjectorEvent{Type: ProjectorEventHomepageUpserted, HomepageID: out.ID, Homepage: &out}
	return &out, nil
}

func (s *HomepageService) GetHomepage(ctx context.Context, homepageID string) (*Homepage, error) {
	return s.GetHomepageForViewer(ctx, homepageID, "")
}

func (s *HomepageService) GetHomepageForViewer(
	ctx context.Context,
	homepageID string,
	viewerID string,
) (*Homepage, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.GetHomepage",
		attribute.String("homepage.id", homepageID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	s.mu.RLock()
	defer s.mu.RUnlock()
	homepage, ok := s.resolveHomepageLocked(homepageID)
	if !ok {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "homepage not found")
		return nil, err
	}
	out := cloneHomepage(homepage)
	applyDefaultShellData(&out)
	s.applyViewerFollowStateLocked(&out, viewerID)
	return &out, nil
}

func (s *HomepageService) FollowHomepage(
	ctx context.Context,
	homepageID string,
	viewerID string,
) (*Homepage, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.FollowHomepage",
		attribute.String("homepage.id", homepageID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	viewerID = strings.TrimSpace(viewerID)
	if viewerID == "" {
		err = newAppError(403, codePermissionDenied, "请先登录后再关注", "missing viewer id")
		return nil, err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	homepage, ok := s.resolveHomepageLocked(homepageID)
	if !ok {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "homepage not found")
		return nil, err
	}
	if homepage.Status == "offline" {
		err = newAppError(410, codeHomepageOffline, "主页已下线，仅保留记录信息", "homepage offline")
		return nil, err
	}
	if s.followers[homepage.ID] == nil {
		s.followers[homepage.ID] = map[string]bool{}
	}
	s.followers[homepage.ID][viewerID] = true
	if err = s.persistLocked(ctx); err != nil {
		return nil, err
	}
	out := cloneHomepage(homepage)
	s.applyViewerFollowStateLocked(&out, viewerID)
	return &out, nil
}

func (s *HomepageService) UnfollowHomepage(
	ctx context.Context,
	homepageID string,
	viewerID string,
) (*Homepage, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.UnfollowHomepage",
		attribute.String("homepage.id", homepageID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	viewerID = strings.TrimSpace(viewerID)
	if viewerID == "" {
		err = newAppError(403, codePermissionDenied, "请先登录后再取消关注", "missing viewer id")
		return nil, err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	homepage, ok := s.resolveHomepageLocked(homepageID)
	if !ok {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "homepage not found")
		return nil, err
	}
	if followers := s.followers[homepage.ID]; followers != nil {
		delete(followers, viewerID)
		if len(followers) == 0 {
			delete(s.followers, homepage.ID)
		}
	}
	if err = s.persistLocked(ctx); err != nil {
		return nil, err
	}
	out := cloneHomepage(homepage)
	s.applyViewerFollowStateLocked(&out, viewerID)
	return &out, nil
}

func (s *HomepageService) GetHomepageShell(ctx context.Context, homepageID string) (*HomepageShellView, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.GetHomepageShell",
		attribute.String("homepage.id", homepageID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	homepage, err := s.GetHomepage(ctx, homepageID)
	if err != nil {
		return nil, err
	}
	return &HomepageShellView{
		Homepage:        *homepage,
		ReviewSummary:   cloneMap(homepage.ReviewSummary),
		ContentPreview:  cloneObjectSlice(homepage.ContentPreview),
		QuestionPreview: cloneObjectSlice(homepage.QuestionPreview),
		RelatedGroups:   cloneObjectSlice(homepage.RelatedGroups),
	}, nil
}

func (s *HomepageService) GetHomepageReviewSummary(ctx context.Context, homepageID string) (*HomepageReviewSummaryView, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.GetHomepageReviewSummary",
		attribute.String("homepage.id", homepageID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	homepage, err := s.GetHomepage(ctx, homepageID)
	if err != nil {
		return nil, err
	}
	highlightTags := stringSliceFromAny(homepage.ReviewSummary["highlightTags"])
	if highlightTags == nil {
		highlightTags = []string{}
	}
	dimensionScores := mapSliceFromAny(homepage.ReviewSummary["dimensionScores"])
	if dimensionScores == nil {
		dimensionScores = []map[string]any{}
	}
	return &HomepageReviewSummaryView{
		AverageRating:   homepage.AverageRating,
		RatingCount:     homepage.RatingCount,
		HighlightTags:   highlightTags,
		DimensionScores: dimensionScores,
	}, nil
}

func (s *HomepageService) GetHomepageRelatedGroups(ctx context.Context, homepageID string) (*HomepageRelatedGroupSummaryView, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.GetHomepageRelatedGroups",
		attribute.String("homepage.id", homepageID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	homepage, err := s.GetHomepage(ctx, homepageID)
	if err != nil {
		return nil, err
	}
	return &HomepageRelatedGroupSummaryView{Groups: cloneObjectSlice(homepage.RelatedGroups)}, nil
}

func (s *HomepageService) GetHomepageImpact(ctx context.Context, homepageID string) (*HomepageImpactSummaryView, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.GetHomepageImpact",
		attribute.String("homepage.id", homepageID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	homepage, err := s.GetHomepage(ctx, homepageID)
	if err != nil {
		return nil, err
	}
	return buildHomepageImpactSummary(homepage), nil
}

func (s *HomepageService) GetObjectPageBundle(
	ctx context.Context,
	viewerID string,
	homepageID string,
	referralSource string,
	feedRequestID string,
	recommendationTraceID string,
	experimentBucket string,
	rolloutCohort string,
) (*ObjectPageBundle, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.GetObjectPageBundle",
		attribute.String("homepage.id", homepageID),
		attribute.String("referral.source", referralSource))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	homepage, err := s.GetHomepage(ctx, homepageID)
	if err != nil {
		return nil, err
	}
	return buildObjectPageBundle(
		ctx,
		viewerID,
		homepage,
		referralSource,
		feedRequestID,
		recommendationTraceID,
		experimentBucket,
		rolloutCohort,
	), nil
}

func (s *HomepageService) CreateHomepageClaimRequest(
	ctx context.Context,
	homepageID string,
	input ClaimRequestInput,
) (*HomepageClaimRequest, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.CreateHomepageClaimRequest",
		attribute.String("homepage.id", homepageID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	s.mu.Lock()
	defer s.mu.Unlock()
	homepage, ok := s.resolveHomepageLocked(homepageID)
	if !ok {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "homepage not found")
		return nil, err
	}
	if homepage.Status == "offline" {
		err = newAppError(410, codeHomepageOffline, "主页已下线，仅保留记录信息", "homepage offline")
		return nil, err
	}
	if strings.TrimSpace(input.ClaimTier) == "" || strings.TrimSpace(input.ContactPhone) == "" {
		err = newAppError(400, codeClaimMaterialMissing, "认领材料不完整，请补充后重试", "claim tier or contact phone missing")
		return nil, err
	}
	if homepage.ClaimStatus == "claimed" {
		err = newAppError(409, codeAlreadyClaimed, "该主页已被认领", "homepage already claimed")
		return nil, err
	}
	now := time.Now().UTC()
	request := &HomepageClaimRequest{
		ID:                   s.nextID("claim"),
		HomepageID:           homepage.ID,
		RequesterUserID:      strings.TrimSpace(input.RequesterUserID),
		ClaimTier:            strings.TrimSpace(input.ClaimTier),
		BusinessLicenseURL:   strings.TrimSpace(input.BusinessLicenseURL),
		ContactPhone:         strings.TrimSpace(input.ContactPhone),
		IdentityCardFrontURL: strings.TrimSpace(input.IdentityCardFrontURL),
		IdentityCardBackURL:  strings.TrimSpace(input.IdentityCardBackURL),
		Note:                 strings.TrimSpace(input.Note),
		Status:               "pending_review",
		CreatedAt:            now,
	}
	homepage.ClaimStatus = "pending_review"
	homepage.UpdatedAt = now
	s.claimRequests[request.ID] = request
	if err = s.persistLocked(ctx); err != nil {
		return nil, err
	}
	out := *request
	return &out, nil
}

func (s *HomepageService) ReviewHomepageClaimRequest(
	ctx context.Context,
	homepageID string,
	claimRequestID string,
	input ClaimReviewInput,
) (*HomepageClaimRequest, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.ReviewHomepageClaimRequest",
		attribute.String("homepage.id", homepageID),
		attribute.String("claim.request_id", claimRequestID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	s.mu.Lock()
	defer s.mu.Unlock()
	resolvedHomepage, ok := s.resolveHomepageLocked(homepageID)
	if !ok {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "homepage not found")
		return nil, err
	}
	request, ok := s.claimRequests[claimRequestID]
	if !ok || request.HomepageID != resolvedHomepage.ID {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "claim request not found")
		return nil, err
	}
	homepage := resolvedHomepage
	now := time.Now().UTC()
	status := normalize(input.Status)
	switch status {
	case "approved":
		request.Status = "approved"
		homepage.ClaimStatus = "claimed"
		homepage.OwnerUserID = request.RequesterUserID
		homepage.OwnerSubAccountID = request.RequesterUserID
	case "rejected":
		request.Status = "rejected"
		homepage.ClaimStatus = "rejected"
	default:
		err = newAppError(400, codePermissionDenied, "当前无权限执行此操作", "unsupported claim review status")
		return nil, err
	}
	request.ReviewNote = strings.TrimSpace(input.ReviewNote)
	request.ReviewedAt = &now
	homepage.UpdatedAt = now
	if err = s.persistLocked(ctx); err != nil {
		return nil, err
	}
	out := *request
	return &out, nil
}

func (s *HomepageService) UpdateClaimedHomepageBasics(
	ctx context.Context,
	homepageID string,
	input HomepageBasicInput,
) (*Homepage, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.UpdateClaimedHomepageBasics",
		attribute.String("homepage.id", homepageID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	var emit *ProjectorEvent
	defer func() {
		if emit != nil {
			s.emitSearchIndex(ctx, *emit)
		}
	}()

	s.mu.Lock()
	defer s.mu.Unlock()
	homepage, ok := s.resolveHomepageLocked(homepageID)
	if !ok {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "homepage not found")
		return nil, err
	}
	if homepage.ClaimStatus != "claimed" {
		err = newAppError(403, codePermissionDenied, "当前无权限执行此操作", "homepage is not claimed yet")
		return nil, err
	}
	if strings.TrimSpace(input.Title) != "" {
		homepage.Title = strings.TrimSpace(input.Title)
	}
	if input.Subtitle != "" {
		homepage.Subtitle = strings.TrimSpace(input.Subtitle)
	}
	if len(input.CategoryTags) > 0 {
		homepage.CategoryTags = cloneStrings(input.CategoryTags)
	}
	if input.CoverURL != "" {
		homepage.CoverURL = strings.TrimSpace(input.CoverURL)
	}
	if input.Address != "" {
		homepage.Address = strings.TrimSpace(input.Address)
	}
	if input.City != "" {
		homepage.City = strings.TrimSpace(input.City)
	}
	if input.Location != nil {
		homepage.Location = cloneGeoPoint(input.Location)
	}
	homepage.UpdatedAt = time.Now().UTC()
	if err = s.persistLocked(ctx); err != nil {
		return nil, err
	}
	out := cloneHomepage(homepage)
	emit = &ProjectorEvent{Type: ProjectorEventHomepageUpserted, HomepageID: out.ID, Homepage: &out}
	return &out, nil
}

func (s *HomepageService) CreateHomepageStatusReport(
	ctx context.Context,
	homepageID string,
	input StatusReportInput,
) (*HomepageStatusReport, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.CreateHomepageStatusReport",
		attribute.String("homepage.id", homepageID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	s.mu.Lock()
	defer s.mu.Unlock()
	homepage, ok := s.resolveHomepageLocked(homepageID)
	if !ok {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "homepage not found")
		return nil, err
	}
	report := &HomepageStatusReport{
		ID:             s.nextID("report"),
		HomepageID:     homepage.ID,
		ReporterUserID: strings.TrimSpace(input.ReporterUserID),
		Reason:         strings.TrimSpace(input.Reason),
		Description:    strings.TrimSpace(input.Description),
		EvidenceURLs:   cloneStrings(input.EvidenceURLs),
		Status:         "pending_review",
		CreatedAt:      time.Now().UTC(),
	}
	s.statusReports[report.ID] = report
	if err = s.persistLocked(ctx); err != nil {
		return nil, err
	}
	out := *report
	return &out, nil
}

func (s *HomepageService) ReviewHomepageStatusReport(
	ctx context.Context,
	homepageID string,
	reportID string,
	input StatusReportReviewInput,
) (*HomepageStatusReport, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.ReviewHomepageStatusReport",
		attribute.String("homepage.id", homepageID),
		attribute.String("report.id", reportID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	var emit *ProjectorEvent
	defer func() {
		if emit != nil {
			s.emitSearchIndex(ctx, *emit)
		}
	}()

	s.mu.Lock()
	defer s.mu.Unlock()
	resolvedHomepage, ok := s.resolveHomepageLocked(homepageID)
	if !ok {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "homepage not found")
		return nil, err
	}
	report, ok := s.statusReports[reportID]
	if !ok || report.HomepageID != resolvedHomepage.ID {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "status report not found")
		return nil, err
	}
	homepage := resolvedHomepage
	now := time.Now().UTC()
	switch normalize(input.Status) {
	case "confirmed_offline":
		report.Status = "confirmed_offline"
		homepage.Status = "offline"
		homepage.OfflineAt = &now
	case "dismissed":
		report.Status = "dismissed"
	default:
		err = newAppError(400, codePermissionDenied, "当前无权限执行此操作", "unsupported status report review status")
		return nil, err
	}
	report.ReviewNote = strings.TrimSpace(input.ReviewNote)
	report.ReviewedAt = &now
	homepage.UpdatedAt = now
	if err = s.persistLocked(ctx); err != nil {
		return nil, err
	}
	if homepage.Status == "offline" {
		emit = &ProjectorEvent{Type: ProjectorEventHomepageRemoved, HomepageID: homepage.ID}
	}
	out := *report
	return &out, nil
}

func (s *HomepageService) seed() {
	now := time.Now().UTC()
	add := func(homepage *Homepage) {
		s.homepages[homepage.ID] = homepage
	}
	ratingA := 4.7
	ratingB := 4.5
	ratingC := 4.8
	pubA := now.Add(-72 * time.Hour)
	pubB := now.Add(-48 * time.Hour)
	pubC := now.Add(-96 * time.Hour)
	add(&Homepage{
		ID:                 "fixture_homepage_author",
		Title:              "契约摄影师主页",
		HomepageType:       "author",
		CanonicalEntityID:  "entity:author:fixture_user_photo",
		ObjectPageTemplate: "standard",
		Status:             "published",
		SourceType:         "official_seed",
		ClaimStatus:        "unclaimed",
		OwnerUserID:        "fixture_user_photo",
		CategoryTags:       []string{"作者", "摄影", "契约"},
		RatingCount:        32,
		CreatedAt:          now.Add(-6 * 24 * time.Hour),
		UpdatedAt:          now.Add(-2 * time.Hour),
		PublishedAt:        &pubA,
	})
	add(&Homepage{
		ID:                 "fixture_homepage_circle",
		Title:              "契约摄影社主页",
		HomepageType:       "circle",
		CanonicalEntityID:  "entity:circle:fixture_circle_photo",
		ObjectPageTemplate: "standard",
		Status:             "published",
		SourceType:         "official_seed",
		ClaimStatus:        "unclaimed",
		OwnerUserID:        "fixture_circle_photo",
		CategoryTags:       []string{"圈子", "摄影", "契约"},
		RatingCount:        24,
		CreatedAt:          now.Add(-6 * 24 * time.Hour),
		UpdatedAt:          now.Add(-2 * time.Hour),
		PublishedAt:        &pubA,
	})
	add(&Homepage{
		ID:                 "fixture_homepage_poi",
		Title:              "杭州西湖契约主页",
		HomepageType:       "poi",
		CanonicalEntityID:  "entity:poi:west_lake_contract",
		ObjectPageTemplate: "standard",
		Status:             "published",
		SourceType:         "official_seed",
		ClaimStatus:        "unclaimed",
		CategoryTags:       []string{"地点", "西湖", "契约"},
		City:               "杭州",
		Location:           &GeoPoint{Latitude: 30.2431, Longitude: 120.1505},
		RatingCount:        18,
		CreatedAt:          now.Add(-6 * 24 * time.Hour),
		UpdatedAt:          now.Add(-2 * time.Hour),
		PublishedAt:        &pubA,
	})
	add(&Homepage{
		ID:                 "homepage_sight_west_lake",
		Title:              "西湖景区",
		Subtitle:           "杭州西湖核心游览区",
		HomepageType:       "sight",
		CanonicalEntityID:  "entity:sight:west_lake",
		ObjectPageTemplate: "travel_photo",
		Status:             "published",
		SourceType:         "official_seed",
		ClaimStatus:        "unclaimed",
		CategoryTags:       []string{"景点", "城市地标", "赏景"},
		CoverURL:           "https://images.unsplash.com/photo-1506744038136-46273834b3fb",
		Address:            "浙江省杭州市西湖区",
		City:               "杭州",
		Location:           &GeoPoint{Latitude: 30.2431, Longitude: 120.1500},
		AverageRating:      &ratingA,
		RatingCount:        328,
		RelatedGroups: []map[string]any{
			{
				"circleId":            "fixture_circle_photo",
				"name":                "契约摄影社",
				"memberCount":         128,
				"linkedHomepageId":    "homepage_sight_west_lake",
				"linkedHomepageTitle": "西湖景区",
			},
		},
		CreatedAt:   now.Add(-10 * 24 * time.Hour),
		UpdatedAt:   now.Add(-2 * time.Hour),
		PublishedAt: &pubA,
	})
	add(&Homepage{
		ID:                 "homepage_hotel_bamboo_inn",
		Title:              "竹隐民宿",
		Subtitle:           "近景区山景庭院房",
		HomepageType:       "hotel",
		CanonicalEntityID:  "entity:hotel:bamboo_inn",
		ObjectPageTemplate: "standard",
		Status:             "published",
		SourceType:         "owner_created",
		ClaimStatus:        "claimed",
		OwnerUserID:        "owner_bamboo",
		CategoryTags:       []string{"民宿", "山景", "亲子"},
		CoverURL:           "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85",
		Address:            "浙江省杭州市西湖区龙井路 18 号",
		City:               "杭州",
		Location:           &GeoPoint{Latitude: 30.2250, Longitude: 120.1160},
		AverageRating:      &ratingB,
		RatingCount:        96,
		CreatedAt:          now.Add(-7 * 24 * time.Hour),
		UpdatedAt:          now.Add(-3 * time.Hour),
		PublishedAt:        &pubB,
	})
	add(&Homepage{
		ID:                 "homepage_restaurant_night_market",
		Title:              "夜巷小馆",
		Subtitle:           "本地人常去的深夜小馆",
		HomepageType:       "restaurant",
		CanonicalEntityID:  "entity:restaurant:night_market",
		ObjectPageTemplate: "standard",
		Status:             "published",
		SourceType:         "imported",
		ClaimStatus:        "unclaimed",
		CategoryTags:       []string{"餐厅", "夜宵", "本地推荐"},
		CoverURL:           "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4",
		Address:            "浙江省杭州市上城区河坊街 66 号",
		City:               "杭州",
		Location:           &GeoPoint{Latitude: 30.2486, Longitude: 120.1709},
		AverageRating:      &ratingC,
		RatingCount:        157,
		CreatedAt:          now.Add(-12 * 24 * time.Hour),
		UpdatedAt:          now.Add(-90 * time.Minute),
		PublishedAt:        &pubC,
	})
	add(&Homepage{
		ID:                 "homepage_vehicle_modelx_candidate",
		Title:              "Model X 2026 款",
		Subtitle:           "纯电中大型 SUV 候选主页",
		HomepageType:       "vehicle",
		CanonicalEntityID:  "entity:vehicle:modelx_2026",
		ObjectPageTemplate: "standard",
		Status:             "candidate",
		SourceType:         "user_suggested",
		ClaimStatus:        "unclaimed",
		CategoryTags:       []string{"汽车", "新能源"},
		CoverURL:           "https://images.unsplash.com/photo-1494976388531-d1058494cdd8",
		City:               "上海",
		CreatedAt:          now.Add(-5 * time.Hour),
		UpdatedAt:          now.Add(-5 * time.Hour),
	})
	add(&Homepage{
		ID:                 "fixture_homepage_university_pku",
		Title:              "北京大学",
		Subtitle:           "校园大学主页模板样本",
		HomepageType:       "university",
		CanonicalEntityID:  "entity:university:pku",
		ObjectPageTemplate: "campus",
		Status:             "published",
		SourceType:         "official_seed",
		ClaimStatus:        "unclaimed",
		CategoryTags:       []string{"校园", "大学", "北京"},
		City:               "北京",
		RatingCount:        1280,
		CreatedAt:          now.Add(-8 * 24 * time.Hour),
		UpdatedAt:          now.Add(-2 * time.Hour),
		PublishedAt:        &pubA,
	})
	add(&Homepage{
		ID:                 "homepage_sight_emeishan",
		Title:              "峨眉山",
		Subtitle:           "世界遗产与川西南山地旅行代表目的地",
		HomepageType:       "sight",
		CanonicalEntityID:  "entity:sight:emeishan",
		ObjectPageTemplate: "travel_photo",
		Status:             "published",
		SourceType:         "official_seed",
		ClaimStatus:        "unclaimed",
		CategoryTags:       []string{"景点", "山地旅行", "乐山"},
		CoverURL:           "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee",
		Address:            "四川省乐山市峨眉山市黄湾镇",
		City:               "乐山",
		Location:           &GeoPoint{Latitude: 29.5593, Longitude: 103.3356},
		AverageRating:      &ratingC,
		RatingCount:        356,
		CreatedAt:          now.Add(-12 * 24 * time.Hour),
		UpdatedAt:          now.Add(-90 * time.Minute),
		PublishedAt:        &pubC,
	})
	add(&Homepage{
		ID:                 "homepage_sight_leshan_giant_buddha",
		Title:              "乐山大佛",
		Subtitle:           "岷江、青衣江、大渡河交汇处的石刻造像与城市地标",
		HomepageType:       "sight",
		CanonicalEntityID:  "entity:sight:leshan_giant_buddha",
		ObjectPageTemplate: "travel_photo",
		Status:             "published",
		SourceType:         "official_seed",
		ClaimStatus:        "unclaimed",
		CategoryTags:       []string{"景点", "石刻", "乐山"},
		CoverURL:           "https://images.unsplash.com/photo-1512453979798-5ea266f8880c",
		Address:            "四川省乐山市市中区凌云路 2435 号",
		City:               "乐山",
		Location:           &GeoPoint{Latitude: 29.5447, Longitude: 103.7730},
		AverageRating:      &ratingB,
		RatingCount:        241,
		CreatedAt:          now.Add(-9 * 24 * time.Hour),
		UpdatedAt:          now.Add(-2 * time.Hour),
		PublishedAt:        &pubB,
	})
	add(&Homepage{
		ID:                 "fixture_homepage_travel_photo_west_lake",
		Title:              "西湖旅行摄影机位",
		Subtitle:           "旅行摄影主页模板样本",
		HomepageType:       "travel_photo",
		CanonicalEntityID:  "entity:travel_photo:west_lake",
		ObjectPageTemplate: "travel_photo",
		Status:             "published",
		SourceType:         "official_seed",
		ClaimStatus:        "unclaimed",
		CategoryTags:       []string{"旅行摄影", "机位", "杭州"},
		City:               "杭州",
		RatingCount:        680,
		CreatedAt:          now.Add(-8 * 24 * time.Hour),
		UpdatedAt:          now.Add(-2 * time.Hour),
		PublishedAt:        &pubA,
	})
	add(&Homepage{
		ID:                 "fixture_homepage_travel_photo_dali",
		Title:              "大理旅行摄影路线",
		Subtitle:           "旅行摄影主页模板样本",
		HomepageType:       "travel_photo",
		CanonicalEntityID:  "entity:travel_photo:dali",
		ObjectPageTemplate: "travel_photo",
		Status:             "published",
		SourceType:         "official_seed",
		ClaimStatus:        "unclaimed",
		CategoryTags:       []string{"旅行摄影", "机位", "大理"},
		City:               "大理",
		RatingCount:        352,
		CreatedAt:          now.Add(-8 * 24 * time.Hour),
		UpdatedAt:          now.Add(-2 * time.Hour),
		PublishedAt:        &pubA,
	})
	add(&Homepage{
		ID:                 "fixture_homepage_travel_photo_tokyo",
		Title:              "东京城市摄影路线",
		Subtitle:           "旅行摄影主页模板样本",
		HomepageType:       "travel_photo",
		CanonicalEntityID:  "entity:travel_photo:tokyo",
		ObjectPageTemplate: "travel_photo",
		Status:             "published",
		SourceType:         "official_seed",
		ClaimStatus:        "unclaimed",
		CategoryTags:       []string{"旅行摄影", "机位", "东京"},
		City:               "东京",
		RatingCount:        318,
		CreatedAt:          now.Add(-8 * 24 * time.Hour),
		UpdatedAt:          now.Add(-2 * time.Hour),
		PublishedAt:        &pubA,
	})
	for _, homepage := range s.homepages {
		if homepage.Status == "published" {
			applyDefaultShellData(homepage)
		}
	}
}

func applyDefaultShellData(homepage *Homepage) {
	if homepage == nil {
		return
	}
	if homepage.ID == "homepage_sight_west_lake" {
		homepage.RelatedGroups = []map[string]any{
			{
				"circleId":            "fixture_circle_photo",
				"name":                "契约摄影社",
				"memberCount":         128,
				"linkedHomepageId":    homepage.ID,
				"linkedHomepageTitle": homepage.Title,
			},
		}
	}
	reviewSummaryNeedsSeed := homepage.ReviewSummary == nil
	if !reviewSummaryNeedsSeed {
		if mapSliceFromAny(homepage.ReviewSummary["dimensionScores"]) == nil {
			reviewSummaryNeedsSeed = true
		}
		if stringSliceFromAny(homepage.ReviewSummary["highlightTags"]) == nil {
			reviewSummaryNeedsSeed = true
		}
	}
	if reviewSummaryNeedsSeed {
		highlightTags := homepage.CategoryTags
		if len(highlightTags) > 3 {
			highlightTags = highlightTags[:3]
		}
		average := 0.0
		if homepage.AverageRating != nil {
			average = *homepage.AverageRating
		}
		homepage.ReviewSummary = map[string]any{
			"averageRating": average,
			"ratingCount":   homepage.RatingCount,
			"highlightTags": highlightTags,
			"dimensionScores": []map[string]any{
				{"label": "环境", "score": average},
				{"label": "体验", "score": average - 0.1},
				{"label": "推荐度", "score": average + 0.1},
			},
		}
	}
	if len(homepage.ContentPreview) == 0 {
		homepage.ContentPreview = []map[string]any{
			{
				"postId":            homepage.ID + "_post_1",
				"title":             homepage.Title + " 的打卡笔记",
				"summary":           "从主页上下文快速进入真实内容沉淀。",
				"contentType":       "article",
				"coverUrl":          homepage.CoverURL,
				"primaryHomepageId": homepage.ID,
			},
			{
				"postId":            homepage.ID + "_post_2",
				"title":             homepage.Title + " 的体验作品",
				"summary":           "支持内容挂载后的聚合预览。",
				"contentType":       "image",
				"coverUrl":          homepage.CoverURL,
				"primaryHomepageId": homepage.ID,
			},
		}
	}
	if len(homepage.QuestionPreview) == 0 {
		homepage.QuestionPreview = []map[string]any{
			{
				"postId":  homepage.ID + "_question_1",
				"title":   homepage.Title + " 值得什么时候去？",
				"summary": "问题聚合视图会收敛到同一主页语境。",
			},
		}
	}
	if len(homepage.RelatedGroups) == 0 {
		homepage.RelatedGroups = []map[string]any{
			{
				"circleId":            homepage.ID + "_circle_1",
				"name":                homepage.Title + " 讨论群",
				"memberCount":         homepage.RatingCount/2 + 12,
				"linkedHomepageId":    homepage.ID,
				"linkedHomepageTitle": homepage.Title,
			},
		}
	}
	if strings.TrimSpace(homepage.CanonicalEntityID) == "" {
		homepage.CanonicalEntityID = canonicalEntityID(homepage.ID, "")
	}
	if strings.TrimSpace(homepage.ObjectPageTemplate) == "" {
		homepage.ObjectPageTemplate = objectPageTemplate(homepage.HomepageType, "")
	}
	if len(homepage.RelationEdges) == 0 {
		homepage.RelationEdges = defaultRelationEdges(homepage)
	}
	if homepage.AssistantContext == nil {
		homepage.AssistantContext = defaultAssistantContext(homepage, "", "", "", "", "")
	}
}

func validateHomepageInput(input HomepageInput) error {
	if strings.TrimSpace(input.Title) == "" {
		return newAppError(400, codeClaimMaterialMissing, "主页标题不能为空", "homepage title is empty")
	}
	switch normalize(input.HomepageType) {
	// 闭集与 contracts/metadata/_shared/types.yaml HomepageType 枚举同源；
	// 地点类新增值与数据工程 Entity/地点 试点 scope 对齐（裁决 6）。
	case "vehicle", "hotel", "restaurant", "sight", "university", "travel_photo",
		"museum", "heritage_site", "ancient_town", "religious_site",
		"check_in_spot", "natural_landscape", "park", "hot_spring", "theme_park":
		return nil
	default:
		return newAppError(400, codeInvalidHomepageType, "不支持的主页类型", "unsupported homepage type")
	}
}

func buildObjectPageBundle(
	ctx context.Context,
	viewerID string,
	homepage *Homepage,
	referralSource string,
	feedRequestID string,
	recommendationTraceID string,
	experimentBucket string,
	rolloutCohort string,
) *ObjectPageBundle {
	applyDefaultShellData(homepage)
	relationEdges := cloneObjectSlice(homepage.RelationEdges)
	assistantContext := defaultAssistantContext(
		homepage,
		referralSource,
		feedRequestID,
		recommendationTraceID,
		experimentBucket,
		rolloutCohort,
	)
	rolloutContext := map[string]any{
		"enabled":                   true,
		"cohort":                    nonEmpty(rolloutCohort, "object-homepage-alpha"),
		"region":                    "",
		"city":                      homepage.City,
		"campus":                    campusFromHomepage(homepage),
		"appVersion":                "",
		"experimentBucket":          experimentBucket,
		"objectType":                homepage.HomepageType,
		"assistantProactiveEnabled": true,
		"relationEvidenceEnabled":   true,
	}
	intersectionReasons := resolveObjectPageIntersections(ctx, viewerID, homepage, relationEdges)
	return &ObjectPageBundle{
		ObjectType:         "homepage",
		ObjectID:           homepage.ID,
		CanonicalEntityID:  homepage.CanonicalEntityID,
		Title:              homepage.Title,
		Subtitle:           homepage.Subtitle,
		CoverURL:           homepage.CoverURL,
		ObjectPageTemplate: homepage.ObjectPageTemplate,
		TagRefs:            cloneStrings(homepage.CategoryTags),
		Stats: map[string]any{
			"ratingCount":       homepage.RatingCount,
			"relatedGroupCount": len(homepage.RelatedGroups),
			"highlightCount":    len(homepage.ContentPreview),
		},
		IntersectionReasons: intersectionReasons,
		HighlightItems:      cloneObjectSlice(homepage.ContentPreview),
		ContentSections: map[string]any{
			"home":    cloneObjectSlice(homepage.ContentPreview),
			"reviews": cloneMap(homepage.ReviewSummary),
			"related": cloneObjectSlice(homepage.RelatedGroups),
		},
		RelatedObjects:   cloneObjectSlice(homepage.RelatedGroups),
		RelationEdges:    relationEdges,
		AssistantContext: assistantContext,
		RolloutContext:   rolloutContext,
	}
}

func buildHomepageImpactSummary(homepage *Homepage) *HomepageImpactSummaryView {
	applyDefaultShellData(homepage)
	target := homepageImpactTarget(homepage)
	items := make([]map[string]any, 0, 3)

	relatedMembers := 0
	for _, group := range homepage.RelatedGroups {
		if n, ok := anyInt(group["memberCount"]); ok && n > 0 {
			relatedMembers += n
		}
	}
	if relatedMembers == 0 && homepage.FollowerCount > 0 {
		relatedMembers = homepage.FollowerCount
	}
	if relatedMembers > 0 {
		items = append(items, buildHomepageImpactItem(
			homepage,
			target,
			rtimpact.HelpRelationship,
			"establish_connection",
			"relationship",
			"homepage_related_groups",
			relatedMembers,
			"相关圈子里的真实成员在这里继续认识彼此、建立连接。",
		))
	}
	if homepage.RatingCount > 0 {
		items = append(items, buildHomepageImpactItem(
			homepage,
			target,
			rtimpact.HelpCommunity,
			"start_discussion",
			"content",
			"homepage_reviews",
			homepage.RatingCount,
			"评分、记录与问答会继续沉淀围绕这个对象的真实讨论。",
		))
	}
	if homepage.FollowerCount > 0 {
		items = append(items, buildHomepageImpactItem(
			homepage,
			target,
			rtimpact.HelpSpread,
			"active_participation",
			"relationship",
			"homepage_followers",
			homepage.FollowerCount,
			"持续关注这个对象的人会把内容和关系继续扩散出去。",
		))
	}

	total := 0
	for _, item := range items {
		if n, ok := item["count"].(int); ok {
			total += n
		}
	}
	return &HomepageImpactSummaryView{
		HomepageID: homepage.ID,
		Total:      total,
		Items:      items,
	}
}

func buildHomepageImpactItem(
	homepage *Homepage,
	target map[string]any,
	helpType string,
	action string,
	dimension string,
	source string,
	count int,
	subtitle string,
) map[string]any {
	primaryText := rtimpact.PrimaryText(helpType, action, int64(count), rtimpact.ActorTA)
	summaryAction := rtimpact.DefaultSummaryAction
	if actionHint, ok := rtimpact.SummaryActionByHelpType[helpType]; ok {
		summaryAction = actionHint
	}
	iconKey := rtimpact.DefaultIconKey
	if key, ok := rtimpact.IconKeyByHelpType[helpType]; ok && strings.TrimSpace(key) != "" {
		iconKey = key
	}
	item := map[string]any{
		"helpType":              helpType,
		"action":                action,
		"intersectionDimension": dimension,
		"tagRef":                "",
		"source":                source,
		"count":                 count,
		"primaryText":           primaryText,
		"subtitleText":          subtitle,
		"impactId":              homepage.ID + "_" + source,
		"primarySpans": []map[string]any{
			{"text": primaryText, "role": "plain"},
		},
		"sampleVisuals": []map[string]any{},
		"actionHints": []map[string]any{
			{
				"actionKey":          summaryAction.Key,
				"label":              summaryAction.Label,
				"target":             target,
				"isPrimary":          true,
				"priority":           1,
				"actionTier":         "light",
				"requiredGates":      []string{},
				"targetAvailability": "available",
				"dispatch":           "navigate",
			},
		},
		"countTarget":        target,
		"evidenceSnapshotId": homepage.ID + "_" + source + "_summary",
		"countObjectKind":    "person",
		"iconKey":            iconKey,
	}
	if strings.TrimSpace(homepage.CoverURL) != "" {
		item["sampleVisuals"] = []map[string]any{
			{
				"assetKind":   "image",
				"imageUrl":    homepage.CoverURL,
				"displayName": homepage.Title,
				"target":      target,
			},
		}
	}
	return item
}

func homepageImpactTarget(homepage *Homepage) map[string]any {
	return map[string]any{
		"objectId":   homepage.ID,
		"objectKind": homepageImpactObjectKind(homepage.HomepageType),
		"routeId":    "homepageDetail",
	}
}

func homepageImpactObjectKind(homepageType string) string {
	switch normalize(homepageType) {
	case "university", "school":
		return "school"
	case "travel_route", "route":
		return "route"
	case "photo_spot", "travel_spot":
		return "photo_spot"
	case "gear", "travel_gear":
		return "gear"
	default:
		return "place"
	}
}

func defaultRelationEdges(homepage *Homepage) []map[string]any {
	edges := make([]map[string]any, 0, 1+len(homepage.RelatedGroups))
	for i, group := range homepage.RelatedGroups {
		circleID, _ := group["circleId"].(string)
		if strings.TrimSpace(circleID) == "" {
			continue
		}
		edges = append(edges, map[string]any{
			"edgeId":            fmt.Sprintf("%s_circle_%d", homepage.ID, i+1),
			"edgeType":          "circle_under_entity",
			"sourceObjectType":  "circle",
			"sourceObjectId":    circleID,
			"targetObjectType":  "homepage",
			"targetObjectId":    homepage.ID,
			"canonicalEntityId": homepage.CanonicalEntityID,
			"tagRefs":           cloneStrings(homepage.CategoryTags),
			"evidenceRefs":      []string{circleID, homepage.ID},
			"confidence":        0.92,
			"createdAt":         homepage.UpdatedAt,
		})
	}
	if len(edges) == 0 {
		edges = append(edges, map[string]any{
			"edgeId":            homepage.ID + "_co_tagged",
			"edgeType":          "co_tagged",
			"sourceObjectType":  "homepage",
			"sourceObjectId":    homepage.ID,
			"targetObjectType":  "homepage",
			"targetObjectId":    homepage.ID,
			"canonicalEntityId": homepage.CanonicalEntityID,
			"tagRefs":           cloneStrings(homepage.CategoryTags),
			"evidenceRefs":      []string{homepage.ID},
			"confidence":        0.72,
			"createdAt":         homepage.UpdatedAt,
		})
	}
	return edges
}

func intersectionDimensionLabel(homepage *Homepage) (dimension string, shortLabel string, evidenceLabel string) {
	switch homepage.HomepageType {
	case "university":
		return "identity", "同校", "你和这所学校有校园交集"
	case "travel_photo", "sight",
		"museum", "heritage_site", "ancient_town", "religious_site",
		"check_in_spot", "natural_landscape", "park", "hot_spring", "theme_park":
		return "location", "同游", "你们都到过这里"
	default:
		return "interest", "同好", "你们都关注这些内容"
	}
}

// defaultIntersectionReasons 生成对象页交集理由（事实通道）。
// 保鲜期：identity/location 取较长保鲜（30 天），interest 取较短（7 天）。
// strength 由标签命中数与关系边数推导，避免硬编码单一分值。
func defaultIntersectionReasons(homepage *Homepage, edges []map[string]any) []map[string]any {
	dimension, _, evidenceLabel := intersectionDimensionLabel(homepage)
	tagShared := len(homepage.CategoryTags)
	tagStrength := intersectionStrengthFromCount(tagShared, 6)
	freshTTL := 7 * 24 * time.Hour
	if dimension == "identity" || dimension == "location" {
		freshTTL = 30 * 24 * time.Hour
	}
	now := time.Now().UTC()
	reasons := []map[string]any{
		{
			"intersectionId":    homepage.ID + "_" + dimension,
			"intersectionClass": "fact",
			"dimension":         dimension,
			"tagRefs":           cloneStrings(homepage.CategoryTags),
			"relationKind":      "mutual",
			"relationObjectId":  homepage.ID,
			"displayName":       homepage.Title,
			"avatarUrl":         homepage.CoverURL,
			"totalPointCount":   tagShared,
			"strength":          tagStrength,
			"primaryText":       evidenceLabel,
			"confidenceLabel":   "",
			"actionType":        "view_object",
			"actionTargetId":    homepage.ID,
			"source":            "tagRef",
			"freshAt":           now.Format(time.RFC3339),
			"expiresAt":         now.Add(freshTTL).Format(time.RFC3339),
		},
	}
	if relObj := relationObjectID(edges); strings.TrimSpace(relObj) != "" {
		reasons = append(reasons, map[string]any{
			"intersectionId":    homepage.ID + "_relationship",
			"intersectionClass": "fact",
			"dimension":         "relationship",
			"tagRefs":           cloneStrings(homepage.CategoryTags),
			"relationKind":      "mutual",
			"relationObjectId":  relObj,
			"displayName":       "相关圈子里有你的连接",
			"avatarUrl":         "",
			"totalPointCount":   len(edges),
			"strength":          intersectionStrengthFromCount(len(edges), 4),
			"primaryText":       "这里有你可能想加入的相关圈子",
			"confidenceLabel":   "",
			"actionType":        "join",
			"actionTargetId":    relObj,
			"source":            "followEdge",
			"freshAt":           now.Format(time.RFC3339),
			"expiresAt":         now.Add(7 * 24 * time.Hour).Format(time.RFC3339),
		})
	}
	return reasons
}

func intersectionStrengthFromCount(count int, saturate int) float64 {
	if saturate <= 0 {
		saturate = 1
	}
	if count <= 0 {
		return 0.5
	}
	v := 0.5 + 0.5*float64(count)/float64(saturate)
	if v > 1.0 {
		return 1.0
	}
	return v
}

func defaultAssistantContext(
	homepage *Homepage,
	referralSource string,
	feedRequestID string,
	recommendationTraceID string,
	experimentBucket string,
	rolloutCohort string,
) map[string]any {
	relationEdges := homepage.RelationEdges
	if len(relationEdges) == 0 {
		relationEdges = defaultRelationEdges(homepage)
	}
	edgeIDs := make([]string, 0, len(relationEdges))
	for _, edge := range relationEdges {
		if id, _ := edge["edgeId"].(string); id != "" {
			edgeIDs = append(edgeIDs, id)
		}
	}
	entityRefs := []string{}
	if canonical := strings.TrimSpace(homepage.CanonicalEntityID); canonical != "" {
		entityRefs = []string{canonical}
	}
	return map[string]any{
		"objectType":            "homepage",
		"objectId":              homepage.ID,
		"canonicalEntityId":     homepage.CanonicalEntityID,
		"tagRefs":               cloneStrings(homepage.CategoryTags),
		"entityRefs":            entityRefs,
		"relationEdgeIds":       edgeIDs,
		"referralSource":        referralSource,
		"feedRequestId":         feedRequestID,
		"recommendationTraceId": recommendationTraceID,
		"experimentBucket":      experimentBucket,
		"rolloutCohort":         rolloutCohort,
	}
}

func relationObjectID(edges []map[string]any) string {
	for _, edge := range edges {
		if id, _ := edge["sourceObjectId"].(string); id != "" {
			return id
		}
	}
	return ""
}

func objectPageTemplate(homepageType string, explicit string) string {
	if trimmed := strings.TrimSpace(explicit); trimmed != "" {
		return trimmed
	}
	switch normalize(homepageType) {
	case "university":
		return "campus"
	case "travel_photo", "sight",
		"museum", "heritage_site", "ancient_town", "religious_site",
		"check_in_spot", "natural_landscape", "park", "hot_spring", "theme_park":
		return "travel_photo"
	default:
		return "standard"
	}
}

func campusFromHomepage(homepage *Homepage) string {
	if homepage.HomepageType == "university" {
		return homepage.Title
	}
	return ""
}

func nonEmpty(value, fallback string) string {
	if strings.TrimSpace(value) != "" {
		return value
	}
	return fallback
}

func newAppError(status int, code, userMessage, debugMessage string) *AppError {
	return &AppError{
		StatusCode:   status,
		Code:         code,
		UserMessage:  userMessage,
		DebugMessage: debugMessage,
	}
}

// ReloadHomepageStateResult 汇报免停服重载结果（ops 触发后用于导入审计）。
type ReloadHomepageStateResult struct {
	HomepagesBefore int `json:"homepagesBefore"`
	HomepagesAfter  int `json:"homepagesAfter"`
	SnapshotSize    int `json:"snapshotSize"`
}

// ReloadHomepageState 免停服重载：数据工程 homepage importer 直写 homepage_state
// 集合后由 ops 触发本方法，把存储快照合并进内存主档（同 ID 覆盖、新 ID 追加），
// 运行期的关注/认领/上报状态不清空。sequence 只前进不回退，避免重载覆盖运行期
// 已推进的分配序列造成 ID 冲突。
func (s *HomepageService) ReloadHomepageState(ctx context.Context) (ReloadHomepageStateResult, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.ReloadHomepageState")
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	if s.store == nil {
		err = errors.New("homepage state store not configured")
		return ReloadHomepageStateResult{}, err
	}
	snapshot, err := s.store.Load(ctx)
	if err != nil {
		return ReloadHomepageStateResult{}, err
	}
	if snapshot == nil {
		err = errors.New("homepage state snapshot is empty")
		return ReloadHomepageStateResult{}, err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	result := ReloadHomepageStateResult{
		HomepagesBefore: len(s.homepages),
		SnapshotSize:    len(snapshot.Homepages),
	}
	current := atomic.LoadUint64(&s.sequence)
	s.applySnapshot(snapshot)
	if current > atomic.LoadUint64(&s.sequence) {
		atomic.StoreUint64(&s.sequence, current)
	}
	result.HomepagesAfter = len(s.homepages)
	return result, nil
}

func (s *HomepageService) applySnapshot(snapshot *HomepageStateSnapshot) {
	if snapshot == nil {
		return
	}
	for i := range snapshot.Homepages {
		homepage := cloneHomepage(&snapshot.Homepages[i])
		s.homepages[homepage.ID] = &homepage
	}
	for homepageID, followers := range snapshot.Followers {
		homepageID = strings.TrimSpace(homepageID)
		if homepageID == "" {
			continue
		}
		if s.followers[homepageID] == nil {
			s.followers[homepageID] = map[string]bool{}
		}
		for _, viewerID := range followers {
			viewerID = strings.TrimSpace(viewerID)
			if viewerID != "" {
				s.followers[homepageID][viewerID] = true
			}
		}
	}
	for i := range snapshot.ClaimRequests {
		request := snapshot.ClaimRequests[i]
		s.claimRequests[request.ID] = &request
	}
	for i := range snapshot.StatusReports {
		report := snapshot.StatusReports[i]
		s.statusReports[report.ID] = &report
	}
	atomic.StoreUint64(&s.sequence, snapshot.Sequence)
}

func (s *HomepageService) snapshotLocked() HomepageStateSnapshot {
	homepages := make([]Homepage, 0, len(s.homepages))
	for _, homepage := range s.homepages {
		out := cloneHomepage(homepage)
		homepages = append(homepages, out)
	}
	sort.Slice(homepages, func(i, j int) bool {
		return homepages[i].ID < homepages[j].ID
	})

	followers := make(map[string][]string, len(s.followers))
	for homepageID, set := range s.followers {
		if len(set) == 0 {
			continue
		}
		viewerIDs := make([]string, 0, len(set))
		for viewerID := range set {
			viewerIDs = append(viewerIDs, viewerID)
		}
		sort.Strings(viewerIDs)
		followers[homepageID] = viewerIDs
	}

	claimRequests := make([]HomepageClaimRequest, 0, len(s.claimRequests))
	for _, request := range s.claimRequests {
		if request != nil {
			claimRequests = append(claimRequests, *request)
		}
	}
	sort.Slice(claimRequests, func(i, j int) bool {
		return claimRequests[i].ID < claimRequests[j].ID
	})

	statusReports := make([]HomepageStatusReport, 0, len(s.statusReports))
	for _, report := range s.statusReports {
		if report != nil {
			statusReports = append(statusReports, *report)
		}
	}
	sort.Slice(statusReports, func(i, j int) bool {
		return statusReports[i].ID < statusReports[j].ID
	})

	return HomepageStateSnapshot{
		Homepages:     homepages,
		Followers:     followers,
		ClaimRequests: claimRequests,
		StatusReports: statusReports,
		Sequence:      atomic.LoadUint64(&s.sequence),
		UpdatedAt:     time.Now().UTC(),
	}
}

func (s *HomepageService) persistLocked(ctx context.Context) error {
	if s.store == nil {
		return nil
	}
	if err := s.store.Save(ctx, s.snapshotLocked()); err != nil {
		return newAppError(500, codeInternalError, "主页数据暂时不可保存，请稍后重试", err.Error())
	}
	return nil
}

func (s *HomepageService) nextID(prefix string) string {
	value := atomic.AddUint64(&s.sequence, 1)
	return fmt.Sprintf("%s_%d", prefix, value)
}
