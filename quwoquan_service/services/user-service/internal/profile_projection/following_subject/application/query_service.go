package following_subject

import (
	"context"
	"log/slog"
	"strings"
	"time"

	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

// PersonaDisplayReader 提供 persona 主体的展示信息（同域 named reader）。
type PersonaDisplayReader interface {
	FindByPersonaID(ctx context.Context, personaID string) (*usermodel.Persona, error)
}

// SubjectDisplay 是跨域主体（homepage/circle）的展示快照。
type SubjectDisplay struct {
	DisplayName string
	AvatarURL   string
	CoverURL    string
	Subtitle    string
}

// SubjectDisplayResolver 解析跨域主体展示信息。实现消费目标域的公开只读
// 合同；解析失败不阻塞列表（降级为标识占位）。
type SubjectDisplayResolver interface {
	ResolveHomepages(ctx context.Context, homepageIDs []string) (map[string]SubjectDisplay, error)
}

// FollowingSubjectItem 与 metadata FollowingSubjectItemView wire 1:1。
type FollowingSubjectItem struct {
	SubjectID          string `json:"subjectId"`
	SubjectType        string `json:"subjectType"`
	DisplayName        string `json:"displayName"`
	AvatarURL          string `json:"avatarUrl"`
	CoverURL           string `json:"coverUrl"`
	Subtitle           string `json:"subtitle"`
	TargetRouteID      string `json:"targetRouteId"`
	TargetObjectID     string `json:"targetObjectId"`
	FollowedAt         string `json:"followedAt"`
	LastVisitedAt      string `json:"lastVisitedAt"`
	LatestChangedAt    string `json:"latestChangedAt"`
	UnreadChangeCount  int64  `json:"unreadChangeCount"`
	HasUnreadChanges   bool   `json:"hasUnreadChanges"`
	LatestChangeReason string `json:"latestChangeReason"`
}

// targetRouteIDBySubjectType 的值域来自 metadata ui_config route ids；与
// alpha fixture following_subject_core 同源。
var targetRouteIDBySubjectType = map[string]string{
	"persona":  "user_profile",
	"circle":   "circle_detail",
	"homepage": "homepage_detail",
}

type QueryService struct {
	store    ProjectionReader
	personas PersonaDisplayReader
	resolver SubjectDisplayResolver
}

func NewQueryService(
	store ProjectionReader,
	personas PersonaDisplayReader,
	resolver SubjectDisplayResolver,
) *QueryService {
	if store == nil {
		panic("following subject store is required")
	}
	return &QueryService{store: store, personas: personas, resolver: resolver}
}

func (s *QueryService) ListFollowingSubjects(
	ctx context.Context,
	personaID, subjectType string,
	limit int,
) ([]FollowingSubjectItem, error) {
	rows, err := s.store.List(ctx, personaID, subjectType, limit)
	if err != nil {
		return nil, err
	}
	items := make([]FollowingSubjectItem, 0, len(rows))
	homepageIDs := make([]string, 0)
	for _, row := range rows {
		if row.SubjectType == "homepage" {
			homepageIDs = append(homepageIDs, row.SubjectID)
		}
	}
	homepageDisplays := map[string]SubjectDisplay{}
	if len(homepageIDs) > 0 && s.resolver != nil {
		displays, err := s.resolver.ResolveHomepages(ctx, homepageIDs)
		if err != nil {
			// 展示信息降级为标识占位；列表本体（关注关系）仍然可用。
			slog.WarnContext(ctx, "following subject homepage enrichment failed", "err", err)
		} else {
			homepageDisplays = displays
		}
	}
	for _, row := range rows {
		item := FollowingSubjectItem{
			SubjectID:          row.SubjectID,
			SubjectType:        row.SubjectType,
			TargetRouteID:      targetRouteIDBySubjectType[row.SubjectType],
			TargetObjectID:     row.SubjectID,
			FollowedAt:         formatTime(&row.FollowedAt),
			LastVisitedAt:      formatTime(row.LastVisitedAt),
			LatestChangedAt:    formatTime(row.LatestChangedAt),
			UnreadChangeCount:  row.UnreadChangeCount,
			HasUnreadChanges:   row.UnreadChangeCount > 0,
			LatestChangeReason: row.LatestChangeReason,
		}
		switch row.SubjectType {
		case "persona":
			s.enrichPersona(ctx, &item)
		case "homepage":
			if display, ok := homepageDisplays[row.SubjectID]; ok {
				item.DisplayName = display.DisplayName
				item.AvatarURL = display.AvatarURL
				item.CoverURL = display.CoverURL
				item.Subtitle = display.Subtitle
			}
		}
		if strings.TrimSpace(item.DisplayName) == "" {
			item.DisplayName = row.SubjectID
		}
		items = append(items, item)
	}
	return items, nil
}

func (s *QueryService) enrichPersona(ctx context.Context, item *FollowingSubjectItem) {
	if s.personas == nil {
		return
	}
	persona, err := s.personas.FindByPersonaID(ctx, item.SubjectID)
	if err != nil || persona == nil {
		return
	}
	item.DisplayName = persona.DisplayName
	item.AvatarURL = persona.AvatarURL
}

func formatTime(value *time.Time) string {
	if value == nil || value.IsZero() {
		return ""
	}
	return value.UTC().Format(time.RFC3339)
}
