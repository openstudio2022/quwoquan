// Package model 包含 Homepage 主档聚合。
//
// Homepage 只拥有 candidate -> published -> offline 生命周期、主档、认领结果与
// HomepageReview 摘要投影。关注关系属于 user.SubjectFollow，本聚合不保存关注明细。
package model

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"slices"
	"strings"
	"time"
	"unicode"
)

var (
	ErrInvalidHomepage       = errors.New("invalid homepage")
	ErrInvalidHomepageType   = errors.New("invalid homepage type")
	ErrInvalidTransition     = errors.New("invalid homepage lifecycle transition")
	ErrHomepageNotClaimed    = errors.New("homepage is not claimed")
	ErrCanonicalIdentityEdit = errors.New("homepage canonical identity is immutable")
)

type Status string

const (
	StatusCandidate Status = "candidate"
	StatusPublished Status = "published"
	StatusOffline   Status = "offline"
)

type GeoPoint struct {
	Latitude  float64 `json:"latitude" bson:"latitude"`
	Longitude float64 `json:"longitude" bson:"longitude"`
}

type IntroductionAsset struct {
	AssetID string `json:"assetId" bson:"assetId"`
	URL     string `json:"url" bson:"url"`
	Caption string `json:"caption,omitempty" bson:"caption,omitempty"`
	Role    string `json:"role,omitempty" bson:"role,omitempty"`
}

type Source struct {
	SourceKind     string `json:"sourceKind" bson:"sourceKind"`
	SourceURL      string `json:"sourceUrl" bson:"sourceUrl"`
	Title          string `json:"title" bson:"title"`
	FetchedAt      string `json:"fetchedAt" bson:"fetchedAt"`
	SnapshotHash   string `json:"snapshotHash" bson:"snapshotHash"`
	PolicyRevision string `json:"policyRevision" bson:"policyRevision"`
	SourceUseMode  string `json:"sourceUseMode" bson:"sourceUseMode"`
}

type ReviewSummary struct {
	AverageRating *float64 `json:"averageRating,omitempty" bson:"averageRating,omitempty"`
	RatingCount   int      `json:"ratingCount" bson:"ratingCount"`
	HighlightTags []string `json:"highlightTags,omitempty" bson:"highlightTags,omitempty"`
}

type ContentPreview struct {
	PostID              string            `json:"postId" bson:"postId"`
	Title               string            `json:"title" bson:"title"`
	Summary             string            `json:"summary,omitempty" bson:"summary,omitempty"`
	ContentType         string            `json:"contentType,omitempty" bson:"contentType,omitempty"`
	CoverURL            string            `json:"coverUrl,omitempty" bson:"coverUrl,omitempty"`
	AuthorName          string            `json:"authorName,omitempty" bson:"authorName,omitempty"`
	LikeCount           int               `json:"likeCount" bson:"likeCount"`
	PrimaryHomepageID   string            `json:"primaryHomepageId,omitempty" bson:"primaryHomepageId,omitempty"`
	IntersectionReasons []json.RawMessage `json:"intersectionReasons,omitempty" bson:"intersectionReasons,omitempty"`
}

type QuestionPreview struct {
	PostID  string `json:"postId" bson:"postId"`
	Title   string `json:"title" bson:"title"`
	Summary string `json:"summary,omitempty" bson:"summary,omitempty"`
}

type RelatedGroup struct {
	CircleID                 string `json:"circleId" bson:"circleId"`
	Name                     string `json:"name" bson:"name"`
	MemberCount              int    `json:"memberCount" bson:"memberCount"`
	LinkedHomepageID         string `json:"linkedHomepageId,omitempty" bson:"linkedHomepageId,omitempty"`
	LinkedHomepageTitle      string `json:"linkedHomepageTitle,omitempty" bson:"linkedHomepageTitle,omitempty"`
	OwnerUserID              string `json:"ownerUserId" bson:"ownerUserId"`
	OwnerDisplayNameSnapshot string `json:"ownerDisplayNameSnapshot" bson:"ownerDisplayNameSnapshot"`
	OwnerAvatarURLSnapshot   string `json:"ownerAvatarUrlSnapshot" bson:"ownerAvatarUrlSnapshot"`
	EvidenceSnapshotID       string `json:"evidenceSnapshotId" bson:"evidenceSnapshotId"`
}

// Snapshot 是 Homepage 唯一持久化边界。聚合内部字段保持私有，application 与
// infrastructure 只能通过 Restore/行为方法读写状态。
type Snapshot struct {
	ID                   string
	Version              int64
	Title                string
	Subtitle             string
	HomepageType         string
	CanonicalEntityID    string
	LookupAliases        []string
	ObjectPageTemplate   string
	Status               Status
	SourceType           string
	SourceOwner          string
	SourceEntityRef      string
	SourceReleaseID      string
	ClaimStatus          string
	CategoryTags         []string
	CoverURL             string
	Address              string
	City                 string
	Location             *GeoPoint
	OwnerUserID          string
	OwnerSubAccountID    string
	Verified             bool
	EstablishedYear      *int
	AverageRating        *float64
	RatingCount          int
	ReviewSummary        *ReviewSummary
	ContentPreview       []ContentPreview
	QuestionPreview      []QuestionPreview
	RelatedGroups        []RelatedGroup
	RelationEdges        []json.RawMessage
	AssistantContext     json.RawMessage
	IntroductionMarkdown string
	IntroductionAssets   []IntroductionAsset
	PrimarySource        *Source
	SourceURLs           []string
	CreatedAt            time.Time
	UpdatedAt            time.Time
	PublishedAt          *time.Time
	OfflineAt            *time.Time
}

type IntakeParams struct {
	ID                   string
	Title                string
	Subtitle             string
	HomepageType         string
	CanonicalEntityID    string
	LookupAliases        []string
	ObjectPageTemplate   string
	SourceType           string
	SourceOwner          string
	SourceEntityRef      string
	SourceReleaseID      string
	CategoryTags         []string
	CoverURL             string
	Address              string
	City                 string
	Location             *GeoPoint
	IntroductionMarkdown string
	IntroductionAssets   []IntroductionAsset
	PrimarySource        *Source
	SourceURLs           []string
	PublishImmediately   bool
	Now                  time.Time
}

type BasicChanges struct {
	Title           string
	Subtitle        string
	CategoryTags    []string
	CoverURL        string
	Address         string
	City            string
	Location        *GeoPoint
	Verified        *bool
	EstablishedYear *int
	Now             time.Time
}

type ImportedProjection struct {
	Title                string
	HomepageType         string
	City                 string
	IntroductionMarkdown string
	IntroductionAssets   []IntroductionAsset
	PrimarySource        *Source
	SourceURLs           []string
	CategoryTags         []string
	SourceOwner          string
	SourceEntityRef      string
	SourceReleaseID      string
	Now                  time.Time
}

type Homepage struct {
	id                   string
	version              int64
	title                string
	subtitle             string
	homepageType         string
	canonicalEntityID    string
	lookupAliases        []string
	objectPageTemplate   string
	status               Status
	sourceType           string
	sourceOwner          string
	sourceEntityRef      string
	sourceReleaseID      string
	claimStatus          string
	categoryTags         []string
	coverURL             string
	address              string
	city                 string
	location             *GeoPoint
	ownerUserID          string
	ownerSubAccountID    string
	verified             bool
	establishedYear      *int
	averageRating        *float64
	ratingCount          int
	reviewSummary        *ReviewSummary
	contentPreview       []ContentPreview
	questionPreview      []QuestionPreview
	relatedGroups        []RelatedGroup
	relationEdges        []json.RawMessage
	assistantContext     json.RawMessage
	introductionMarkdown string
	introductionAssets   []IntroductionAsset
	primarySource        *Source
	sourceURLs           []string
	createdAt            time.Time
	updatedAt            time.Time
	publishedAt          *time.Time
	offlineAt            *time.Time
}

func Intake(params IntakeParams) (*Homepage, error) {
	now := params.Now.UTC()
	if now.IsZero() {
		now = time.Now().UTC()
	}
	canonical := strings.TrimSpace(params.CanonicalEntityID)
	if canonical == "" {
		canonical = CanonicalEntityID(params.HomepageType, params.Title)
	}
	id := strings.TrimSpace(params.ID)
	if id == "" {
		id = StableID(canonical, params.SourceOwner, params.SourceEntityRef, params.HomepageType, params.Title)
	}
	status := StatusCandidate
	var publishedAt *time.Time
	if params.PublishImmediately {
		status = StatusPublished
		published := now
		publishedAt = &published
	}
	homepage := &Homepage{
		id:                   id,
		version:              1,
		title:                strings.TrimSpace(params.Title),
		subtitle:             strings.TrimSpace(params.Subtitle),
		homepageType:         strings.TrimSpace(params.HomepageType),
		canonicalEntityID:    canonical,
		lookupAliases:        normalizeAliases(params.LookupAliases, id, canonical, params.SourceEntityRef, params.Title),
		objectPageTemplate:   resolveObjectPageTemplate(params.HomepageType, params.ObjectPageTemplate),
		status:               status,
		sourceType:           strings.TrimSpace(params.SourceType),
		sourceOwner:          strings.TrimSpace(params.SourceOwner),
		sourceEntityRef:      strings.TrimSpace(params.SourceEntityRef),
		sourceReleaseID:      strings.TrimSpace(params.SourceReleaseID),
		claimStatus:          "unclaimed",
		categoryTags:         cloneStrings(params.CategoryTags),
		coverURL:             strings.TrimSpace(params.CoverURL),
		address:              strings.TrimSpace(params.Address),
		city:                 strings.TrimSpace(params.City),
		location:             cloneGeo(params.Location),
		introductionMarkdown: strings.TrimSpace(params.IntroductionMarkdown),
		introductionAssets:   cloneAssets(params.IntroductionAssets),
		primarySource:        cloneSource(params.PrimarySource),
		sourceURLs:           cloneStrings(params.SourceURLs),
		createdAt:            now,
		updatedAt:            now,
		publishedAt:          publishedAt,
	}
	if homepage.coverURL == "" {
		homepage.coverURL = coverFromAssets(homepage.introductionAssets)
	}
	if err := homepage.validate(); err != nil {
		return nil, err
	}
	return homepage, nil
}

func Restore(snapshot Snapshot) (*Homepage, error) {
	homepage := &Homepage{
		id:                   strings.TrimSpace(snapshot.ID),
		version:              snapshot.Version,
		title:                strings.TrimSpace(snapshot.Title),
		subtitle:             strings.TrimSpace(snapshot.Subtitle),
		homepageType:         strings.TrimSpace(snapshot.HomepageType),
		canonicalEntityID:    strings.TrimSpace(snapshot.CanonicalEntityID),
		lookupAliases:        normalizeAliases(snapshot.LookupAliases, snapshot.ID, snapshot.CanonicalEntityID, snapshot.SourceEntityRef, snapshot.Title),
		objectPageTemplate:   resolveObjectPageTemplate(snapshot.HomepageType, snapshot.ObjectPageTemplate),
		status:               snapshot.Status,
		sourceType:           strings.TrimSpace(snapshot.SourceType),
		sourceOwner:          strings.TrimSpace(snapshot.SourceOwner),
		sourceEntityRef:      strings.TrimSpace(snapshot.SourceEntityRef),
		sourceReleaseID:      strings.TrimSpace(snapshot.SourceReleaseID),
		claimStatus:          strings.TrimSpace(snapshot.ClaimStatus),
		categoryTags:         cloneStrings(snapshot.CategoryTags),
		coverURL:             strings.TrimSpace(snapshot.CoverURL),
		address:              strings.TrimSpace(snapshot.Address),
		city:                 strings.TrimSpace(snapshot.City),
		location:             cloneGeo(snapshot.Location),
		ownerUserID:          strings.TrimSpace(snapshot.OwnerUserID),
		ownerSubAccountID:    strings.TrimSpace(snapshot.OwnerSubAccountID),
		verified:             snapshot.Verified,
		establishedYear:      cloneInt(snapshot.EstablishedYear),
		averageRating:        cloneFloat(snapshot.AverageRating),
		ratingCount:          snapshot.RatingCount,
		reviewSummary:        cloneReviewSummary(snapshot.ReviewSummary),
		contentPreview:       slices.Clone(snapshot.ContentPreview),
		questionPreview:      slices.Clone(snapshot.QuestionPreview),
		relatedGroups:        slices.Clone(snapshot.RelatedGroups),
		relationEdges:        cloneRawSlice(snapshot.RelationEdges),
		assistantContext:     slices.Clone(snapshot.AssistantContext),
		introductionMarkdown: strings.TrimSpace(snapshot.IntroductionMarkdown),
		introductionAssets:   cloneAssets(snapshot.IntroductionAssets),
		primarySource:        cloneSource(snapshot.PrimarySource),
		sourceURLs:           cloneStrings(snapshot.SourceURLs),
		createdAt:            snapshot.CreatedAt.UTC(),
		updatedAt:            snapshot.UpdatedAt.UTC(),
		publishedAt:          cloneTime(snapshot.PublishedAt),
		offlineAt:            cloneTime(snapshot.OfflineAt),
	}
	if homepage.claimStatus == "" {
		homepage.claimStatus = "unclaimed"
	}
	if err := homepage.validate(); err != nil {
		return nil, err
	}
	return homepage, nil
}

func (h *Homepage) Publish(now time.Time) error {
	if h == nil || h.status != StatusCandidate {
		return ErrInvalidTransition
	}
	h.status = StatusPublished
	h.sourceType = nonEmpty(h.sourceType, "official_seed")
	next := normalizedTime(now, h.updatedAt)
	h.publishedAt = &next
	h.offlineAt = nil
	return h.advance(next)
}

func (h *Homepage) UpdateClaimedBasics(changes BasicChanges) error {
	if h == nil || h.claimStatus != "claimed" {
		return ErrHomepageNotClaimed
	}
	if value := strings.TrimSpace(changes.Title); value != "" {
		h.title = value
	}
	if changes.Subtitle != "" {
		h.subtitle = strings.TrimSpace(changes.Subtitle)
	}
	if len(changes.CategoryTags) > 0 {
		h.categoryTags = cloneStrings(changes.CategoryTags)
	}
	if changes.CoverURL != "" {
		h.coverURL = strings.TrimSpace(changes.CoverURL)
	}
	if changes.Address != "" {
		h.address = strings.TrimSpace(changes.Address)
	}
	if changes.City != "" {
		h.city = strings.TrimSpace(changes.City)
	}
	if changes.Location != nil {
		h.location = cloneGeo(changes.Location)
	}
	if changes.Verified != nil {
		h.verified = *changes.Verified
	}
	if changes.EstablishedYear != nil {
		h.establishedYear = cloneInt(changes.EstablishedYear)
	}
	h.lookupAliases = normalizeAliases(h.lookupAliases, h.id, h.canonicalEntityID, h.sourceEntityRef, h.title)
	return h.advance(changes.Now)
}

func (h *Homepage) ApplyClaimApproved(ownerUserID, ownerSubAccountID string, approved bool, now time.Time) error {
	if h == nil {
		return ErrInvalidHomepage
	}
	if approved {
		h.claimStatus = "claimed"
		h.ownerUserID = strings.TrimSpace(ownerUserID)
		h.ownerSubAccountID = strings.TrimSpace(ownerSubAccountID)
	} else {
		h.claimStatus = "rejected"
		h.ownerUserID = ""
		h.ownerSubAccountID = ""
	}
	return h.advance(now)
}

func (h *Homepage) ApplyClaimPending(now time.Time) error {
	if h == nil {
		return ErrInvalidHomepage
	}
	if h.claimStatus == "claimed" {
		return ErrHomepageNotClaimed
	}
	if h.claimStatus == "pending_review" {
		return nil
	}
	h.claimStatus = "pending_review"
	return h.advance(now)
}

func (h *Homepage) ApplyOffline(now time.Time) error {
	if h == nil {
		return ErrInvalidHomepage
	}
	if h.status == StatusOffline {
		return nil
	}
	if h.status != StatusPublished {
		return ErrInvalidTransition
	}
	h.status = StatusOffline
	offlineAt := normalizedTime(now, h.updatedAt)
	h.offlineAt = &offlineAt
	return h.advance(offlineAt)
}

func (h *Homepage) ApplyReviewSummary(average *float64, count int, tags []string, now time.Time) error {
	if h == nil || count < 0 {
		return ErrInvalidHomepage
	}
	h.averageRating = cloneFloat(average)
	h.ratingCount = count
	h.reviewSummary = &ReviewSummary{
		AverageRating: cloneFloat(average),
		RatingCount:   count,
		HighlightTags: cloneStrings(tags),
	}
	return h.advance(now)
}

// ApplyImportedProjection 更新来源拥有的投影字段，不覆盖已认领方维护的主档字段。
func (h *Homepage) ApplyImportedProjection(projection ImportedProjection) error {
	if h == nil {
		return ErrInvalidHomepage
	}
	if strings.TrimSpace(projection.HomepageType) != "" &&
		strings.TrimSpace(projection.HomepageType) != h.homepageType {
		return ErrCanonicalIdentityEdit
	}
	h.introductionMarkdown = strings.TrimSpace(projection.IntroductionMarkdown)
	h.introductionAssets = cloneAssets(projection.IntroductionAssets)
	h.primarySource = cloneSource(projection.PrimarySource)
	h.sourceURLs = cloneStrings(projection.SourceURLs)
	if len(projection.CategoryTags) > 0 {
		h.categoryTags = cloneStrings(projection.CategoryTags)
	}
	if h.claimStatus != "claimed" {
		if title := strings.TrimSpace(projection.Title); title != "" {
			h.title = title
		}
		if city := strings.TrimSpace(projection.City); city != "" {
			h.city = city
		}
		if cover := coverFromAssets(h.introductionAssets); cover != "" {
			h.coverURL = cover
		}
	}
	h.sourceOwner = strings.TrimSpace(projection.SourceOwner)
	h.sourceEntityRef = strings.TrimSpace(projection.SourceEntityRef)
	h.sourceReleaseID = strings.TrimSpace(projection.SourceReleaseID)
	h.sourceType = "official_seed"
	if h.status == StatusOffline {
		h.status = StatusPublished
		h.offlineAt = nil
	}
	if h.publishedAt == nil {
		published := normalizedTime(projection.Now, h.updatedAt)
		h.publishedAt = &published
	}
	h.lookupAliases = normalizeAliases(h.lookupAliases, h.id, h.canonicalEntityID, h.sourceEntityRef, h.title)
	return h.advance(projection.Now)
}

func (h *Homepage) advance(now time.Time) error {
	h.version++
	h.updatedAt = normalizedTime(now, h.updatedAt)
	return h.validate()
}

func (h *Homepage) validate() error {
	if h.id == "" || h.version < 1 || h.title == "" || h.canonicalEntityID == "" ||
		h.objectPageTemplate == "" || h.createdAt.IsZero() || h.updatedAt.IsZero() {
		return ErrInvalidHomepage
	}
	if !ValidHomepageType(h.homepageType) {
		return ErrInvalidHomepageType
	}
	switch h.status {
	case StatusCandidate, StatusPublished, StatusOffline:
	default:
		return ErrInvalidHomepage
	}
	if h.sourceOwner == "" != (h.sourceEntityRef == "") {
		return ErrInvalidHomepage
	}
	return nil
}

func (h *Homepage) ID() string {
	if h == nil {
		return ""
	}
	return h.id
}

func (h *Homepage) Version() int64 {
	if h == nil {
		return 0
	}
	return h.version
}

func (h *Homepage) Status() Status {
	if h == nil {
		return ""
	}
	return h.status
}

func (h *Homepage) Snapshot() Snapshot {
	if h == nil {
		return Snapshot{}
	}
	return Snapshot{
		ID:                   h.id,
		Version:              h.version,
		Title:                h.title,
		Subtitle:             h.subtitle,
		HomepageType:         h.homepageType,
		CanonicalEntityID:    h.canonicalEntityID,
		LookupAliases:        cloneStrings(h.lookupAliases),
		ObjectPageTemplate:   h.objectPageTemplate,
		Status:               h.status,
		SourceType:           h.sourceType,
		SourceOwner:          h.sourceOwner,
		SourceEntityRef:      h.sourceEntityRef,
		SourceReleaseID:      h.sourceReleaseID,
		ClaimStatus:          h.claimStatus,
		CategoryTags:         cloneStrings(h.categoryTags),
		CoverURL:             h.coverURL,
		Address:              h.address,
		City:                 h.city,
		Location:             cloneGeo(h.location),
		OwnerUserID:          h.ownerUserID,
		OwnerSubAccountID:    h.ownerSubAccountID,
		Verified:             h.verified,
		EstablishedYear:      cloneInt(h.establishedYear),
		AverageRating:        cloneFloat(h.averageRating),
		RatingCount:          h.ratingCount,
		ReviewSummary:        cloneReviewSummary(h.reviewSummary),
		ContentPreview:       slices.Clone(h.contentPreview),
		QuestionPreview:      slices.Clone(h.questionPreview),
		RelatedGroups:        slices.Clone(h.relatedGroups),
		RelationEdges:        cloneRawSlice(h.relationEdges),
		AssistantContext:     slices.Clone(h.assistantContext),
		IntroductionMarkdown: h.introductionMarkdown,
		IntroductionAssets:   cloneAssets(h.introductionAssets),
		PrimarySource:        cloneSource(h.primarySource),
		SourceURLs:           cloneStrings(h.sourceURLs),
		CreatedAt:            h.createdAt,
		UpdatedAt:            h.updatedAt,
		PublishedAt:          cloneTime(h.publishedAt),
		OfflineAt:            cloneTime(h.offlineAt),
	}
}

func StableID(canonicalEntityID, sourceOwner, sourceEntityRef, homepageType, title string) string {
	identity := strings.TrimSpace(canonicalEntityID)
	if owner := strings.TrimSpace(sourceOwner); owner != "" && strings.TrimSpace(sourceEntityRef) != "" {
		identity = "source\x00" + owner + "\x00" + strings.TrimSpace(sourceEntityRef)
	}
	if identity == "" {
		identity = "canonical\x00" + CanonicalEntityID(homepageType, title)
	}
	sum := sha256.Sum256([]byte(identity))
	return "hp_" + hex.EncodeToString(sum[:16])
}

func CanonicalEntityID(homepageType, title string) string {
	kind := strings.TrimSpace(homepageType)
	slug := canonicalSlug(title)
	if kind == "" || slug == "" {
		return ""
	}
	return "entity:" + kind + ":" + slug
}

func ValidHomepageType(value string) bool {
	switch strings.TrimSpace(value) {
	case "vehicle", "hotel", "restaurant", "sight", "university", "travel_photo",
		"museum", "heritage_site", "ancient_town", "religious_site",
		"check_in_spot", "natural_landscape", "park", "hot_spring", "theme_park":
		return true
	default:
		return false
	}
}

func NormalizeLookupAlias(value string) string {
	return strings.ToLower(strings.TrimSpace(strings.ReplaceAll(value, "\\", "/")))
}

func normalizeAliases(values []string, required ...string) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0, len(values)+len(required))
	appendValue := func(value string) {
		normalized := NormalizeLookupAlias(value)
		if normalized == "" {
			return
		}
		if _, exists := seen[normalized]; exists {
			return
		}
		seen[normalized] = struct{}{}
		out = append(out, normalized)
	}
	for _, value := range values {
		appendValue(value)
	}
	for _, value := range required {
		appendValue(value)
	}
	return out
}

func canonicalSlug(value string) string {
	var builder strings.Builder
	underscore := false
	for _, current := range strings.TrimSpace(value) {
		switch {
		case unicode.IsLetter(current) || unicode.IsDigit(current):
			builder.WriteRune(unicode.ToLower(current))
			underscore = false
		case current == '_' || current == '-' || current == '/' || unicode.IsSpace(current):
			if !underscore {
				builder.WriteByte('_')
				underscore = true
			}
		}
	}
	return strings.Trim(builder.String(), "_")
}

func resolveObjectPageTemplate(homepageType, explicit string) string {
	if value := strings.TrimSpace(explicit); value != "" {
		return value
	}
	switch strings.TrimSpace(homepageType) {
	case "university":
		return "campus"
	case "travel_photo", "sight", "museum", "heritage_site", "ancient_town",
		"religious_site", "check_in_spot", "natural_landscape", "park", "hot_spring", "theme_park":
		return "travel_photo"
	default:
		return "standard"
	}
}

func coverFromAssets(assets []IntroductionAsset) string {
	for _, asset := range assets {
		if asset.Role == "cover" && strings.TrimSpace(asset.URL) != "" {
			return strings.TrimSpace(asset.URL)
		}
	}
	return ""
}

func normalizedTime(value, floor time.Time) time.Time {
	result := value.UTC()
	if result.IsZero() {
		result = time.Now().UTC()
	}
	if result.Before(floor) {
		return floor
	}
	return result
}

func nonEmpty(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return strings.TrimSpace(value)
}

func cloneStrings(values []string) []string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			out = append(out, trimmed)
		}
	}
	if len(out) == 0 {
		return nil
	}
	return out
}

func cloneAssets(values []IntroductionAsset) []IntroductionAsset { return slices.Clone(values) }
func cloneRawSlice(values []json.RawMessage) []json.RawMessage {
	out := make([]json.RawMessage, 0, len(values))
	for _, value := range values {
		out = append(out, slices.Clone(value))
	}
	return out
}
func cloneGeo(value *GeoPoint) *GeoPoint {
	if value == nil {
		return nil
	}
	result := *value
	return &result
}
func cloneSource(value *Source) *Source {
	if value == nil {
		return nil
	}
	result := *value
	return &result
}
func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	result := value.UTC()
	return &result
}
func cloneInt(value *int) *int {
	if value == nil {
		return nil
	}
	result := *value
	return &result
}
func cloneFloat(value *float64) *float64 {
	if value == nil {
		return nil
	}
	result := *value
	return &result
}
func cloneReviewSummary(value *ReviewSummary) *ReviewSummary {
	if value == nil {
		return nil
	}
	return &ReviewSummary{
		AverageRating: cloneFloat(value.AverageRating),
		RatingCount:   value.RatingCount,
		HighlightTags: cloneStrings(value.HighlightTags),
	}
}
