package behavior

import (
	"context"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
)

// FootprintEntry 我的足迹单条记录：行为事件 + hydrate 后的内容（可能已删除为 nil）。
type FootprintEntry struct {
	PostID     string
	Action     string
	OccurredAt time.Time
	Post       *postmodel.Post
}

// footprintTypeActions 足迹 type → 行为 action 集合的云侧唯一映射；
// 端侧只传 type 枚举字符串，不解析 action 语义（计算与展示均在云侧）。
func footprintTypeActions(footprintType string) []string {
	switch strings.TrimSpace(strings.ToLower(footprintType)) {
	case "viewed":
		return []string{"click", "dwell", "content_depth", "play_progress"}
	case "liked":
		return []string{"like"}
	case "commented":
		return []string{"comment"}
	case "shared":
		return []string{"share"}
	default:
		return []string{"click", "dwell", "content_depth", "play_progress", "like", "comment", "share"}
	}
}

// GetMyFootprint 我的足迹只读查询：复用既有行为边（rm_behavior_events），
// 无新写路径；仅本人可见、不产生交集与影响事实。cursor 为 RFC3339Nano 时间。
func (s *BehaviorService) GetMyFootprint(
	ctx context.Context,
	userID, footprintType, cursor string,
	limit int,
) ([]FootprintEntry, string, error) {
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return nil, "", rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"需要登录",
			"footprint requires authenticated user",
		)
	}
	if s.eventStore == nil {
		return nil, "", nil
	}
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	var before time.Time
	if trimmed := strings.TrimSpace(cursor); trimmed != "" {
		parsed, err := time.Parse(time.RFC3339Nano, trimmed)
		if err != nil {
			return nil, "", rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"无效的 cursor",
				"invalid footprint cursor",
			)
		}
		before = parsed
	}
	actions := footprintTypeActions(footprintType)
	// 多取一些以覆盖同一内容的重复行为（去重后可能不足一页）。
	events, err := s.eventStore.ListUserFootprint(ctx, userID, actions, before, limit*3)
	if err != nil {
		return nil, "", err
	}
	entries := make([]FootprintEntry, 0, limit)
	seen := make(map[string]struct{}, len(events))
	var lastSeen time.Time
	for _, ev := range events {
		lastSeen = ev.CreatedAt
		contentID := strings.TrimSpace(ev.ContentID)
		if contentID == "" {
			continue
		}
		if _, dup := seen[contentID]; dup {
			continue
		}
		seen[contentID] = struct{}{}
		post, _ := s.store.FindByID(ctx, contentID)
		entries = append(entries, FootprintEntry{
			PostID:     contentID,
			Action:     ev.Action,
			OccurredAt: ev.CreatedAt,
			Post:       post,
		})
		if len(entries) >= limit {
			break
		}
	}
	nextCursor := ""
	if len(events) >= limit*3 && !lastSeen.IsZero() {
		nextCursor = lastSeen.UTC().Format(time.RFC3339Nano)
	} else if len(entries) >= limit && !lastSeen.IsZero() {
		nextCursor = lastSeen.UTC().Format(time.RFC3339Nano)
	}
	return entries, nextCursor, nil
}
