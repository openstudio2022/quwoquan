package circle

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrNotFound            = errors.New("Circle not found")
	ErrArchived            = errors.New("Circle is archived")
	ErrInvalidChange       = errors.New("invalid Circle change")
	ErrVersionConflict     = errors.New("Circle version conflict")
	ErrIdempotencyConflict = errors.New("Circle idempotency conflict")
)

type ChangeKind string

const (
	ChangeCreate   ChangeKind = "create"
	ChangeUpdate   ChangeKind = "update"
	ChangeArchive  ChangeKind = "archive"
	ChangeSections ChangeKind = "sections"
)

const (
	maxCircleNameRunes        = 60
	maxCircleDescriptionRunes = 2000
	maxCircleRulesRunes       = 2000
	maxCircleWelcomeRunes     = 500
	maxSectionConfigEntries   = 16
	defaultStorageQuotaBytes  = int64(1024 * 1024 * 1024)
)

// ChangeSet 是 Circle 聚合唯一的变更输入。路径身份与 actor 由 application
// Facade 解析后注入；调用方版本字段不进入公开请求，ExpectedVersion 由服务端
// 加载当前版本填充（内部 CAS）。
type ChangeSet struct {
	Kind            ChangeKind
	CircleID        string
	ExpectedVersion int64
	OwnerPersonaID  string

	Name                *string
	Description         *string
	RulesText           *string
	WelcomeMessage      *string
	CoverUrl            *string
	IconUrl             *string
	Category            *string
	SubCategory         *string
	Tags                []string
	TagsSet             bool
	Visibility          *CircleVisibility
	JoinPolicy          *CircleJoinPolicy
	Kind_               *CircleKind
	DisplaySubjectType  *CircleDisplaySubjectType
	FollowEnabled       *bool
	AutoSyncChat        *bool
	LinkedHomepageID    *string
	LinkedHomepageType  *HomepageType
	LinkedHomepageTitle *string

	Sections []CircleSectionConfig

	OccurredAt time.Time
}

// Apply 在纯领域层执行 Circle 命名状态迁移。
func Apply(current *Circle, change ChangeSet) (Circle, error) {
	switch change.Kind {
	case ChangeCreate:
		if current != nil || change.ExpectedVersion != 0 {
			return Circle{}, ErrVersionConflict
		}
		return createCircle(change)
	case ChangeUpdate:
		if current == nil {
			return Circle{}, ErrNotFound
		}
		if current.Version != change.ExpectedVersion {
			return Circle{}, ErrVersionConflict
		}
		if current.Status != CircleStatusActive {
			return Circle{}, ErrArchived
		}
		return updateCircle(*current, change)
	case ChangeArchive:
		if current == nil {
			return Circle{}, ErrNotFound
		}
		if current.Version != change.ExpectedVersion {
			return Circle{}, ErrVersionConflict
		}
		if current.Status == CircleStatusArchived {
			return Circle{}, ErrArchived
		}
		next := *current
		next.Version++
		next.Status = CircleStatusArchived
		next.UpdatedAt = change.OccurredAt.UTC()
		return next, nil
	case ChangeSections:
		if current == nil {
			return Circle{}, ErrNotFound
		}
		if current.Version != change.ExpectedVersion {
			return Circle{}, ErrVersionConflict
		}
		if current.Status != CircleStatusActive {
			return Circle{}, ErrArchived
		}
		sections, err := normalizeSections(change.Sections)
		if err != nil {
			return Circle{}, err
		}
		next := *current
		next.Version++
		next.SectionConfig = sections
		next.UpdatedAt = change.OccurredAt.UTC()
		return next, nil
	default:
		return Circle{}, ErrInvalidChange
	}
}

func createCircle(change ChangeSet) (Circle, error) {
	circleID := strings.TrimSpace(change.CircleID)
	owner := strings.TrimSpace(change.OwnerPersonaID)
	if circleID == "" || owner == "" || change.OccurredAt.IsZero() || change.Name == nil {
		return Circle{}, ErrInvalidChange
	}
	name := strings.TrimSpace(*change.Name)
	if name == "" || len([]rune(name)) > maxCircleNameRunes {
		return Circle{}, ErrInvalidChange
	}
	description := ""
	if change.Description != nil {
		description = strings.TrimSpace(*change.Description)
	}
	if len([]rune(description)) > maxCircleDescriptionRunes {
		return Circle{}, ErrInvalidChange
	}
	rulesText, err := normalizedBoundedText(change.RulesText, maxCircleRulesRunes)
	if err != nil {
		return Circle{}, err
	}
	welcomeMessage, err := normalizedBoundedText(
		change.WelcomeMessage,
		maxCircleWelcomeRunes,
	)
	if err != nil {
		return Circle{}, err
	}
	visibility := CircleVisibilityPublic
	if change.Visibility != nil {
		if !validCircleVisibility(*change.Visibility) {
			return Circle{}, ErrInvalidChange
		}
		visibility = *change.Visibility
	}
	joinPolicy := CircleJoinPolicyOpen
	if change.JoinPolicy != nil {
		if !validCircleJoinPolicy(*change.JoinPolicy) {
			return Circle{}, ErrInvalidChange
		}
		joinPolicy = *change.JoinPolicy
	}
	kind := CircleKindInterest
	if change.Kind_ != nil {
		if !validCircleKind(*change.Kind_) {
			return Circle{}, ErrInvalidChange
		}
		kind = *change.Kind_
	}
	displaySubjectType := CircleDisplaySubjectTypeCircle
	if change.DisplaySubjectType != nil {
		displaySubjectType = *change.DisplaySubjectType
	}
	now := change.OccurredAt.UTC()
	next := Circle{
		ID: circleID, Version: 1, Name: name, Description: description,
		RulesText: rulesText, WelcomeMessage: welcomeMessage,
		OwnerID: owner, Status: CircleStatusActive,
		Visibility: visibility, JoinPolicy: joinPolicy,
		Kind: kind, DisplaySubjectType: displaySubjectType,
		AutoSyncChat: true, StorageQuotaBytes: defaultStorageQuotaBytes,
		SectionConfig: defaultSectionConfig(),
		CreatedAt:     now, UpdatedAt: now,
	}
	if change.CoverUrl != nil {
		next.CoverUrl = strings.TrimSpace(*change.CoverUrl)
	}
	if change.IconUrl != nil {
		next.IconUrl = strings.TrimSpace(*change.IconUrl)
	}
	if change.Category != nil {
		next.Category = strings.TrimSpace(*change.Category)
		next.DomainID = next.Category
	}
	if change.SubCategory != nil {
		next.SubCategory = strings.TrimSpace(*change.SubCategory)
	}
	if change.TagsSet {
		next.Tags = normalizeTags(change.Tags)
	}
	if change.FollowEnabled != nil {
		next.FollowEnabled = *change.FollowEnabled
	}
	if change.AutoSyncChat != nil {
		next.AutoSyncChat = *change.AutoSyncChat
	}
	applyLinkedHomepage(&next, change)
	return next, nil
}

func updateCircle(next Circle, change ChangeSet) (Circle, error) {
	changed := false
	if change.Name != nil {
		name := strings.TrimSpace(*change.Name)
		if name == "" || len([]rune(name)) > maxCircleNameRunes {
			return Circle{}, ErrInvalidChange
		}
		next.Name, changed = name, true
	}
	if change.Description != nil {
		description := strings.TrimSpace(*change.Description)
		if len([]rune(description)) > maxCircleDescriptionRunes {
			return Circle{}, ErrInvalidChange
		}
		next.Description, changed = description, true
	}
	if change.RulesText != nil {
		rulesText, err := normalizedBoundedText(
			change.RulesText,
			maxCircleRulesRunes,
		)
		if err != nil {
			return Circle{}, err
		}
		next.RulesText, changed = rulesText, true
	}
	if change.WelcomeMessage != nil {
		welcomeMessage, err := normalizedBoundedText(
			change.WelcomeMessage,
			maxCircleWelcomeRunes,
		)
		if err != nil {
			return Circle{}, err
		}
		next.WelcomeMessage, changed = welcomeMessage, true
	}
	if change.CoverUrl != nil {
		next.CoverUrl, changed = strings.TrimSpace(*change.CoverUrl), true
	}
	if change.IconUrl != nil {
		next.IconUrl, changed = strings.TrimSpace(*change.IconUrl), true
	}
	if change.Category != nil {
		category := strings.TrimSpace(*change.Category)
		next.Category, next.DomainID, changed = category, category, true
	}
	if change.SubCategory != nil {
		next.SubCategory, changed = strings.TrimSpace(*change.SubCategory), true
	}
	if change.TagsSet {
		next.Tags, changed = normalizeTags(change.Tags), true
	}
	if change.Visibility != nil {
		if !validCircleVisibility(*change.Visibility) {
			return Circle{}, ErrInvalidChange
		}
		next.Visibility, changed = *change.Visibility, true
	}
	if change.JoinPolicy != nil {
		if !validCircleJoinPolicy(*change.JoinPolicy) {
			return Circle{}, ErrInvalidChange
		}
		next.JoinPolicy, changed = *change.JoinPolicy, true
	}
	if change.Kind_ != nil {
		if !validCircleKind(*change.Kind_) {
			return Circle{}, ErrInvalidChange
		}
		next.Kind, changed = *change.Kind_, true
	}
	if change.DisplaySubjectType != nil {
		next.DisplaySubjectType, changed = *change.DisplaySubjectType, true
	}
	if change.FollowEnabled != nil {
		next.FollowEnabled, changed = *change.FollowEnabled, true
	}
	if change.AutoSyncChat != nil {
		next.AutoSyncChat, changed = *change.AutoSyncChat, true
	}
	if change.LinkedHomepageID != nil || change.LinkedHomepageType != nil || change.LinkedHomepageTitle != nil {
		applyLinkedHomepage(&next, change)
		changed = true
	}
	if !changed {
		return Circle{}, ErrInvalidChange
	}
	next.Version++
	next.UpdatedAt = change.OccurredAt.UTC()
	return next, nil
}

func normalizedBoundedText(value *string, maxRunes int) (string, error) {
	if value == nil {
		return "", nil
	}
	normalized := strings.TrimSpace(*value)
	if len([]rune(normalized)) > maxRunes {
		return "", ErrInvalidChange
	}
	return normalized, nil
}

func applyLinkedHomepage(next *Circle, change ChangeSet) {
	if change.LinkedHomepageID != nil {
		next.LinkedHomepageID = strings.TrimSpace(*change.LinkedHomepageID)
	}
	if change.LinkedHomepageType != nil {
		next.LinkedHomepageType = *change.LinkedHomepageType
	}
	if change.LinkedHomepageTitle != nil {
		next.LinkedHomepageTitle = strings.TrimSpace(*change.LinkedHomepageTitle)
	}
}

// defaultSectionConfig 与 metadata ui_config circle_sections 闭集一致
// （works/members/chat/storage）。
func defaultSectionConfig() []CircleSectionConfig {
	return []CircleSectionConfig{
		{SectionType: CircleSectionTypeWorks, Visible: true, Order: 0},
		{SectionType: CircleSectionTypeMembers, Visible: true, Order: 1},
		{SectionType: CircleSectionTypeChat, Visible: true, Order: 2},
		{SectionType: CircleSectionTypeStorage, Visible: true, Order: 3},
	}
}

func normalizeSections(sections []CircleSectionConfig) ([]CircleSectionConfig, error) {
	if len(sections) == 0 || len(sections) > maxSectionConfigEntries {
		return nil, ErrInvalidChange
	}
	seenTypes := make(map[CircleSectionType]struct{}, len(sections))
	seenOrders := make(map[int64]struct{}, len(sections))
	normalized := make([]CircleSectionConfig, 0, len(sections))
	for _, section := range sections {
		if !validSectionType(section.SectionType) {
			return nil, ErrInvalidChange
		}
		if _, duplicate := seenTypes[section.SectionType]; duplicate {
			return nil, ErrInvalidChange
		}
		if section.Order < 0 || section.Order >= int64(len(sections)) {
			return nil, ErrInvalidChange
		}
		if _, duplicate := seenOrders[section.Order]; duplicate {
			return nil, ErrInvalidChange
		}
		seenTypes[section.SectionType] = struct{}{}
		seenOrders[section.Order] = struct{}{}
		normalized = append(normalized, CircleSectionConfig{
			SectionType: section.SectionType,
			Visible:     section.Visible,
			Order:       section.Order,
			CustomTitle: strings.TrimSpace(section.CustomTitle),
		})
	}
	return normalized, nil
}

func normalizeTags(tags []string) []string {
	normalized := make([]string, 0, len(tags))
	seen := make(map[string]struct{}, len(tags))
	for _, tag := range tags {
		tag = strings.TrimSpace(tag)
		if tag == "" {
			continue
		}
		if _, duplicate := seen[tag]; duplicate {
			continue
		}
		seen[tag] = struct{}{}
		normalized = append(normalized, tag)
	}
	return normalized
}

func validCircleVisibility(value CircleVisibility) bool {
	return value == CircleVisibilityPublic || value == CircleVisibilityPrivate || value == CircleVisibilityInviteOnly
}

func validCircleJoinPolicy(value CircleJoinPolicy) bool {
	return value == CircleJoinPolicyOpen || value == CircleJoinPolicyApproval || value == CircleJoinPolicyInviteOnly
}

func validCircleKind(value CircleKind) bool {
	return value == CircleKindInterest || value == CircleKindOrganization
}

func validSectionType(value CircleSectionType) bool {
	switch value {
	case CircleSectionTypeWorks, CircleSectionTypeMembers, CircleSectionTypeChat,
		CircleSectionTypeStorage, CircleSectionTypeCustom:
		return true
	default:
		return false
	}
}
