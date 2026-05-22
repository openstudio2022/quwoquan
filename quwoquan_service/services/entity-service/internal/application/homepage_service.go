package application

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
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
	ID              string           `json:"_id"`
	Title           string           `json:"title"`
	Subtitle        string           `json:"subtitle,omitempty"`
	HomepageType    string           `json:"homepageType"`
	Status          string           `json:"status"`
	SourceType      string           `json:"sourceType"`
	ClaimStatus     string           `json:"claimStatus"`
	CategoryTags    []string         `json:"categoryTags,omitempty"`
	CoverURL        string           `json:"coverUrl,omitempty"`
	Address         string           `json:"address,omitempty"`
	City            string           `json:"city,omitempty"`
	Location        *GeoPoint        `json:"location,omitempty"`
	OwnerUserID     string           `json:"ownerUserId,omitempty"`
	AverageRating   *float64         `json:"averageRating,omitempty"`
	RatingCount     int              `json:"ratingCount"`
	ReviewSummary   map[string]any   `json:"reviewSummary,omitempty"`
	ContentPreview  []map[string]any `json:"contentPreview,omitempty"`
	QuestionPreview []map[string]any `json:"questionPreview,omitempty"`
	RelatedGroups   []map[string]any `json:"relatedGroups,omitempty"`
	CreatedAt       time.Time        `json:"createdAt"`
	UpdatedAt       time.Time        `json:"updatedAt"`
	PublishedAt     *time.Time       `json:"publishedAt,omitempty"`
	OfflineAt       *time.Time       `json:"offlineAt,omitempty"`
}

type HomepageSearchItemView struct {
	HomepageID    string   `json:"homepageId"`
	Title         string   `json:"title"`
	Subtitle      string   `json:"subtitle,omitempty"`
	HomepageType  string   `json:"homepageType"`
	CoverURL      string   `json:"coverUrl,omitempty"`
	City          string   `json:"city,omitempty"`
	Address       string   `json:"address,omitempty"`
	Status        string   `json:"status"`
	AverageRating *float64 `json:"averageRating,omitempty"`
	RatingCount   int      `json:"ratingCount"`
}

type HomepageShellView struct {
	Homepage        Homepage         `json:"homepage"`
	ReviewSummary   map[string]any   `json:"reviewSummary,omitempty"`
	ContentPreview  []map[string]any `json:"contentPreview,omitempty"`
	QuestionPreview []map[string]any `json:"questionPreview,omitempty"`
	RelatedGroups   []map[string]any `json:"relatedGroups,omitempty"`
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
	Title        string    `json:"title"`
	Subtitle     string    `json:"subtitle"`
	HomepageType string    `json:"homepageType"`
	CategoryTags []string  `json:"categoryTags"`
	CoverURL     string    `json:"coverUrl"`
	Address      string    `json:"address"`
	City         string    `json:"city"`
	Location     *GeoPoint `json:"location"`
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
	mu            sync.RWMutex
	homepages     map[string]*Homepage
	claimRequests map[string]*HomepageClaimRequest
	statusReports map[string]*HomepageStatusReport
	sequence      uint64
}

func NewHomepageService() *HomepageService {
	svc := &HomepageService{
		homepages:     map[string]*Homepage{},
		claimRequests: map[string]*HomepageClaimRequest{},
		statusReports: map[string]*HomepageStatusReport{},
	}
	svc.seed()
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
	needle := normalize(query)
	filterType := normalize(homepageType)
	filterCity := normalize(city)
	filterStatus := normalize(status)
	if limit <= 0 || limit > 50 {
		limit = 20
	}

	items := make([]HomepageSearchItemView, 0, len(s.homepages))
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
		if needle != "" {
			haystack := normalize(strings.Join([]string{
				homepage.Title,
				homepage.Subtitle,
				homepage.Address,
				homepage.City,
				strings.Join(homepage.CategoryTags, " "),
			}, " "))
			if !strings.Contains(haystack, needle) {
				continue
			}
		}
		items = append(items, HomepageSearchItemView{
			HomepageID:    homepage.ID,
			Title:         homepage.Title,
			Subtitle:      homepage.Subtitle,
			HomepageType:  homepage.HomepageType,
			CoverURL:      homepage.CoverURL,
			City:          homepage.City,
			Address:       homepage.Address,
			Status:        homepage.Status,
			AverageRating: homepage.AverageRating,
			RatingCount:   homepage.RatingCount,
		})
	}
	sort.Slice(items, func(i, j int) bool {
		leftScore := items[i].RatingCount
		rightScore := items[j].RatingCount
		if leftScore == rightScore {
			return items[i].Title < items[j].Title
		}
		return leftScore > rightScore
	})
	if len(items) > limit {
		items = items[:limit]
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
		ID:           id,
		Title:        strings.TrimSpace(input.Title),
		Subtitle:     strings.TrimSpace(input.Subtitle),
		HomepageType: strings.TrimSpace(input.HomepageType),
		Status:       "candidate",
		SourceType:   sourceType,
		ClaimStatus:  "unclaimed",
		CategoryTags: cloneStrings(input.CategoryTags),
		CoverURL:     strings.TrimSpace(input.CoverURL),
		Address:      strings.TrimSpace(input.Address),
		City:         strings.TrimSpace(input.City),
		Location:     cloneGeoPoint(input.Location),
		CreatedAt:    now,
		UpdatedAt:    now,
	}
	s.mu.Lock()
	s.homepages[id] = homepage
	s.mu.Unlock()
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

	s.mu.Lock()
	defer s.mu.Unlock()
	homepage, ok := s.homepages[homepageID]
	if !ok {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "homepage not found")
		return nil, err
	}
	now := time.Now().UTC()
	homepage.Status = "published"
	homepage.SourceType = "official_seed"
	homepage.UpdatedAt = now
	homepage.PublishedAt = &now
	applyDefaultShellData(homepage)
	out := cloneHomepage(homepage)
	return &out, nil
}

func (s *HomepageService) GetHomepage(ctx context.Context, homepageID string) (*Homepage, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.GetHomepage",
		attribute.String("homepage.id", homepageID))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()

	s.mu.RLock()
	defer s.mu.RUnlock()
	homepage, ok := s.homepages[homepageID]
	if !ok {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "homepage not found")
		return nil, err
	}
	out := cloneHomepage(homepage)
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
	highlightTags, _ := homepage.ReviewSummary["highlightTags"].([]string)
	dimensionScores, _ := homepage.ReviewSummary["dimensionScores"].([]map[string]any)
	return &HomepageReviewSummaryView{
		AverageRating:   homepage.AverageRating,
		RatingCount:     homepage.RatingCount,
		HighlightTags:   cloneStrings(highlightTags),
		DimensionScores: cloneObjectSlice(dimensionScores),
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
	homepage, ok := s.homepages[homepageID]
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
		HomepageID:           homepageID,
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
	request, ok := s.claimRequests[claimRequestID]
	if !ok || request.HomepageID != homepageID {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "claim request not found")
		return nil, err
	}
	homepage, ok := s.homepages[homepageID]
	if !ok {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "homepage not found")
		return nil, err
	}
	now := time.Now().UTC()
	status := normalize(input.Status)
	switch status {
	case "approved":
		request.Status = "approved"
		homepage.ClaimStatus = "claimed"
		homepage.OwnerUserID = request.RequesterUserID
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

	s.mu.Lock()
	defer s.mu.Unlock()
	homepage, ok := s.homepages[homepageID]
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
	out := cloneHomepage(homepage)
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
	if _, ok := s.homepages[homepageID]; !ok {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "homepage not found")
		return nil, err
	}
	report := &HomepageStatusReport{
		ID:             s.nextID("report"),
		HomepageID:     homepageID,
		ReporterUserID: strings.TrimSpace(input.ReporterUserID),
		Reason:         strings.TrimSpace(input.Reason),
		Description:    strings.TrimSpace(input.Description),
		EvidenceURLs:   cloneStrings(input.EvidenceURLs),
		Status:         "pending_review",
		CreatedAt:      time.Now().UTC(),
	}
	s.statusReports[report.ID] = report
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

	s.mu.Lock()
	defer s.mu.Unlock()
	report, ok := s.statusReports[reportID]
	if !ok || report.HomepageID != homepageID {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "status report not found")
		return nil, err
	}
	homepage, ok := s.homepages[homepageID]
	if !ok {
		err = newAppError(404, codeHomepageNotFound, "主页不存在或已下线", "homepage not found")
		return nil, err
	}
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
		ID:            "homepage_sight_west_lake",
		Title:         "西湖景区",
		Subtitle:      "杭州西湖核心游览区",
		HomepageType:  "sight",
		Status:        "published",
		SourceType:    "official_seed",
		ClaimStatus:   "unclaimed",
		CategoryTags:  []string{"景点", "城市地标", "赏景"},
		CoverURL:      "https://images.unsplash.com/photo-1506744038136-46273834b3fb",
		Address:       "浙江省杭州市西湖区",
		City:          "杭州",
		Location:      &GeoPoint{Latitude: 30.2431, Longitude: 120.1500},
		AverageRating: &ratingA,
		RatingCount:   328,
		CreatedAt:     now.Add(-10 * 24 * time.Hour),
		UpdatedAt:     now.Add(-2 * time.Hour),
		PublishedAt:   &pubA,
	})
	add(&Homepage{
		ID:            "homepage_hotel_bamboo_inn",
		Title:         "竹隐民宿",
		Subtitle:      "近景区山景庭院房",
		HomepageType:  "hotel",
		Status:        "published",
		SourceType:    "owner_created",
		ClaimStatus:   "claimed",
		OwnerUserID:   "owner_bamboo",
		CategoryTags:  []string{"民宿", "山景", "亲子"},
		CoverURL:      "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85",
		Address:       "浙江省杭州市西湖区龙井路 18 号",
		City:          "杭州",
		Location:      &GeoPoint{Latitude: 30.2250, Longitude: 120.1160},
		AverageRating: &ratingB,
		RatingCount:   96,
		CreatedAt:     now.Add(-7 * 24 * time.Hour),
		UpdatedAt:     now.Add(-3 * time.Hour),
		PublishedAt:   &pubB,
	})
	add(&Homepage{
		ID:            "homepage_restaurant_night_market",
		Title:         "夜巷小馆",
		Subtitle:      "本地人常去的深夜小馆",
		HomepageType:  "restaurant",
		Status:        "published",
		SourceType:    "imported",
		ClaimStatus:   "unclaimed",
		CategoryTags:  []string{"餐厅", "夜宵", "本地推荐"},
		CoverURL:      "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4",
		Address:       "浙江省杭州市上城区河坊街 66 号",
		City:          "杭州",
		Location:      &GeoPoint{Latitude: 30.2486, Longitude: 120.1709},
		AverageRating: &ratingC,
		RatingCount:   157,
		CreatedAt:     now.Add(-12 * 24 * time.Hour),
		UpdatedAt:     now.Add(-90 * time.Minute),
		PublishedAt:   &pubC,
	})
	add(&Homepage{
		ID:           "homepage_vehicle_modelx_candidate",
		Title:        "Model X 2026 款",
		Subtitle:     "纯电中大型 SUV 候选主页",
		HomepageType: "vehicle",
		Status:       "candidate",
		SourceType:   "user_suggested",
		ClaimStatus:  "unclaimed",
		CategoryTags: []string{"汽车", "新能源"},
		CoverURL:     "https://images.unsplash.com/photo-1494976388531-d1058494cdd8",
		City:         "上海",
		CreatedAt:    now.Add(-5 * time.Hour),
		UpdatedAt:    now.Add(-5 * time.Hour),
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
	if homepage.ReviewSummary == nil {
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
}

func validateHomepageInput(input HomepageInput) error {
	if strings.TrimSpace(input.Title) == "" {
		return newAppError(400, codeClaimMaterialMissing, "主页标题不能为空", "homepage title is empty")
	}
	switch normalize(input.HomepageType) {
	case "vehicle", "hotel", "restaurant", "sight":
		return nil
	default:
		return newAppError(400, codeInvalidHomepageType, "不支持的主页类型", "unsupported homepage type")
	}
}

func newAppError(status int, code, userMessage, debugMessage string) *AppError {
	return &AppError{
		StatusCode:   status,
		Code:         code,
		UserMessage:  userMessage,
		DebugMessage: debugMessage,
	}
}

func normalize(raw string) string {
	return strings.ToLower(strings.TrimSpace(raw))
}

func cloneHomepage(in *Homepage) Homepage {
	if in == nil {
		return Homepage{}
	}
	out := *in
	out.CategoryTags = cloneStrings(in.CategoryTags)
	out.Location = cloneGeoPoint(in.Location)
	out.ReviewSummary = cloneMap(in.ReviewSummary)
	out.ContentPreview = cloneObjectSlice(in.ContentPreview)
	out.QuestionPreview = cloneObjectSlice(in.QuestionPreview)
	out.RelatedGroups = cloneObjectSlice(in.RelatedGroups)
	return out
}

func cloneStrings(values []string) []string {
	if len(values) == 0 {
		return nil
	}
	out := make([]string, len(values))
	copy(out, values)
	return out
}

func cloneGeoPoint(point *GeoPoint) *GeoPoint {
	if point == nil {
		return nil
	}
	out := *point
	return &out
}

func cloneMap(in map[string]any) map[string]any {
	if len(in) == 0 {
		return nil
	}
	out := make(map[string]any, len(in))
	for key, value := range in {
		out[key] = value
	}
	return out
}

func cloneObjectSlice(items []map[string]any) []map[string]any {
	if len(items) == 0 {
		return nil
	}
	out := make([]map[string]any, len(items))
	for i := range items {
		out[i] = cloneMap(items[i])
	}
	return out
}

func (s *HomepageService) nextID(prefix string) string {
	value := atomic.AddUint64(&s.sequence, 1)
	return fmt.Sprintf("%s_%d", prefix, value)
}
