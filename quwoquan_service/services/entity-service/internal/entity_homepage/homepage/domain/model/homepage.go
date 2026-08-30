// Package model 包含 Homepage 主档聚合。
//
// Homepage 只拥有 candidate -> published -> offline 生命周期、主档与认领结果。
// 评价摘要、内容预览、关系边和关注状态均是独立读投影，不进入本聚合。
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

// InRange 判定坐标是否落在 WGS84 合法域内。0,0 是几内亚湾公海，对旅游实体而言
// 只可能来自缺省值，因此按非法处理，避免「未知位置」被 2dsphere 当成真实点召回。
func (g GeoPoint) InRange() bool {
	if g.Latitude < -90 || g.Latitude > 90 || g.Longitude < -180 || g.Longitude > 180 {
		return false
	}
	return g.Latitude != 0 || g.Longitude != 0
}

type IntroductionAsset struct {
	AssetID string `json:"assetId" bson:"assetId"`
	URL     string `json:"url" bson:"url"`
	// AccessMode 是媒体交付访问模式（DEC-033，契约
	// projections/homepage_introduction_asset.yaml accessMode，enum 唯一真相源
	// contracts/metadata/_shared/types.yaml MediaDeliveryAccessMode）。
	// signed_grant 时 URL 为相对私有引用，App 必须按 assetId 换取短签；
	// 空串表示缺席（契约 NULLABLE），只允许出现在存量 public 交付。
	AccessMode string `json:"accessMode,omitempty" bson:"accessMode,omitempty"`
	Caption    string `json:"caption,omitempty" bson:"caption,omitempty"`
	Role       string `json:"role,omitempty" bson:"role,omitempty"`
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
	OwnerPersonaID       string
	ManagerPersonaIDs    []string
	Verified             bool
	EstablishedYear      *int
	IntroductionMarkdown string
	IntroductionAssets   []IntroductionAsset
	StructuredFacts      *StructuredFacts
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
	StructuredFacts      *StructuredFacts
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
	Location             *GeoPoint
	IntroductionMarkdown string
	IntroductionAssets   []IntroductionAsset
	StructuredFacts      *StructuredFacts
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
	ownerPersonaID       string
	managerPersonaIDs    []string
	verified             bool
	establishedYear      *int
	introductionMarkdown string
	introductionAssets   []IntroductionAsset
	structuredFacts      *StructuredFacts
	droppedFactFields    []string
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
	homepage.structuredFacts, homepage.droppedFactFields = SanitizeStructuredFacts(params.StructuredFacts)
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
		ownerPersonaID:       strings.TrimSpace(snapshot.OwnerPersonaID),
		managerPersonaIDs:    cloneStrings(snapshot.ManagerPersonaIDs),
		verified:             snapshot.Verified,
		establishedYear:      cloneInt(snapshot.EstablishedYear),
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
	// 存量文档可能早于留证要求写入，或被旁路直改过，因此读回时重跑一次收敛，
	// 保证「无 factSource 的字段不可见」在任何持久化状态下都成立。
	homepage.structuredFacts, homepage.droppedFactFields = SanitizeStructuredFacts(snapshot.StructuredFacts)
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

func (h *Homepage) ApplyClaimApproved(ownerUserID, ownerPersonaID string, approved bool, now time.Time) error {
	if h == nil {
		return ErrInvalidHomepage
	}
	if approved {
		h.claimStatus = "claimed"
		h.ownerUserID = strings.TrimSpace(ownerUserID)
		h.ownerPersonaID = strings.TrimSpace(ownerPersonaID)
	} else {
		h.claimStatus = "rejected"
		h.ownerUserID = ""
		h.ownerPersonaID = ""
		h.managerPersonaIDs = nil
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
	h.structuredFacts, h.droppedFactFields = SanitizeStructuredFacts(projection.StructuredFacts)
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
		// 坐标只由数据发布线提供；认领后由商家在 UpdateClaimedBasics 里维护，
		// 因此与 title/city 同处 claimStatus != claimed 分支。
		if projection.Location != nil {
			h.location = cloneGeo(projection.Location)
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
	// location 是 NULLABLE，但一旦存在必须是可被 2dsphere 索引的合法坐标；
	// 越界坐标会在 Mongo 建键时才失败，聚合层先拦住更容易归因。
	if h.location != nil && !h.location.InRange() {
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

// StructuredFactsView 返回已收敛的事实投影，nil 表示无可展示事实。
func (h *Homepage) StructuredFactsView() *StructuredFacts {
	if h == nil {
		return nil
	}
	return cloneStructuredFacts(h.structuredFacts)
}

// DroppedStructuredFactFields 返回最近一次收敛丢弃的字段与原因，供导入流水线落日志。
func (h *Homepage) DroppedStructuredFactFields() []string {
	if h == nil {
		return nil
	}
	return cloneStrings(h.droppedFactFields)
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
		OwnerPersonaID:       h.ownerPersonaID,
		ManagerPersonaIDs:    cloneStrings(h.managerPersonaIDs),
		Verified:             h.verified,
		EstablishedYear:      cloneInt(h.establishedYear),
		IntroductionMarkdown: h.introductionMarkdown,
		IntroductionAssets:   cloneAssets(h.introductionAssets),
		StructuredFacts:      cloneStructuredFacts(h.structuredFacts),
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

// homepageTypes 与 _shared/types.yaml 的 HomepageType 同集，由
// verify_homepage_type_contract.py 守住两侧一致；新增取值必须同时出现在这里，
// 否则该类型会在 Intake 阶段被判定为非法而无法建立主页。
var homepageTypes = []string{
	"vehicle", "hotel", "restaurant", "sight", "university", "school", "travel_photo",
	"museum", "heritage_site", "ancient_town", "religious_site",
	"check_in_spot", "natural_landscape", "park", "hot_spring", "theme_park",
	"transport_hub", "city", "route", "photo_spot", "gear",
}

var homepageTypeSet = func() map[string]struct{} {
	set := make(map[string]struct{}, len(homepageTypes))
	for _, value := range homepageTypes {
		set[value] = struct{}{}
	}
	return set
}()

// HomepageTypes 返回闭集副本，供校验与装配读取，不暴露内部切片。
func HomepageTypes() []string {
	return append([]string(nil), homepageTypes...)
}

func ValidHomepageType(value string) bool {
	_, ok := homepageTypeSet[strings.TrimSpace(value)]
	return ok
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

// ObjectPageTemplate 是主页类型到对象页模板的唯一映射。route 停留在 standard，
// 因为它是多站点序列而非单一地点，套用以单张封面为主的 travel_photo 会错位。
func ObjectPageTemplate(homepageType, explicit string) string {
	if value := strings.TrimSpace(explicit); value != "" {
		return value
	}
	switch strings.TrimSpace(homepageType) {
	case "university", "school":
		return "campus"
	case "travel_photo", "sight", "museum", "heritage_site", "ancient_town",
		"religious_site", "check_in_spot", "natural_landscape", "park", "hot_spring", "theme_park",
		"transport_hub", "city", "photo_spot":
		return "travel_photo"
	default:
		return "standard"
	}
}

func resolveObjectPageTemplate(homepageType, explicit string) string {
	return ObjectPageTemplate(homepageType, explicit)
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
