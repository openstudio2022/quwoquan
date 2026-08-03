package model

import (
	"encoding/base64"
	"encoding/json"
	"strings"
	"time"
)

// ReadModel 是具名读端结果，不是 Comment 聚合；它不提供变更方法，并在各层边界复制。
type ReadModel struct {
	ID                        string
	Version                   int64
	PostID                    string
	AuthorID                  string
	AuthorDisplayNameSnapshot string
	AuthorAvatarURLSnapshot   string
	PersonaContextVersion     int64
	Content                   string
	ReplyToCommentID          string
	ReplyToUserID             string
	ParentCommentID           string
	AttachmentMediaIDs        []string
	Mentions                  []Mention
	AssistantMentioned        bool
	AssistantReplySource      string
	AssistantCorrectionStatus string
	AuthorIPLocation          string
	Status                    Status
	IsPinned                  bool
	PinnedAt                  *time.Time
	// HotScore 是 hotScore relay 维护的确定性投影分，仅用于服务端 sort=hot keyset。
	HotScore  int64
	CreatedAt time.Time
	UpdatedAt time.Time
	DeletedAt *time.Time
}

func (r ReadModel) Clone() ReadModel {
	r.AttachmentMediaIDs = cloneStrings(r.AttachmentMediaIDs)
	r.Mentions = cloneMentions(r.Mentions)
	r.PinnedAt = cloneTime(r.PinnedAt)
	r.DeletedAt = cloneTime(r.DeletedAt)
	return r
}

// HotScoreFor 是 hotScore 投影分的唯一计算公式：
// (likeCount - dislikeCount) + 2 * replyCount。
// relay 增量更新与全量重算都必须经由本函数，保证可从权威数据重放。
func HotScoreFor(likeCount, dislikeCount, replyCount int64) int64 {
	return (likeCount - dislikeCount) + 2*replyCount
}

type Page struct {
	Items      []ReadModel
	NextCursor string
	Total      int64
}

// ReplySummary 是一级 Comment 的可重建线程投影；回复本身仍是独立 Comment，
// 这里只携带有界 preview 与继续分页所需游标。
type ReplySummary struct {
	Count      int64
	Preview    []ReadModel
	NextCursor string
}

type AttachmentProjection struct {
	MediaID   string
	MediaType string
	URL       string
	Width     int
	Height    int
	Available bool
}

func (s ReplySummary) Clone() ReplySummary {
	preview := make([]ReadModel, len(s.Preview))
	for index, item := range s.Preview {
		preview[index] = item.Clone()
	}
	return ReplySummary{
		Count:      s.Count,
		Preview:    preview,
		NextCursor: s.NextCursor,
	}
}

func (p Page) Clone() Page {
	items := make([]ReadModel, len(p.Items))
	for index, item := range p.Items {
		items[index] = item.Clone()
	}
	return Page{
		Items:      items,
		NextCursor: p.NextCursor,
		Total:      p.Total,
	}
}

// ReplyTarget 是仅用于规范化新回复的窄关系投影，不是 Comment 聚合。
type ReplyTarget struct {
	ID              string
	PostID          string
	AuthorID        string
	ParentCommentID string
	Status          Status
}

type PostOwnership struct {
	PostID   string
	AuthorID string
	Active   bool
}

type CountsDelta struct {
	PostID            string
	CreatedSinceCount int64
	DeletedSinceCount int64
	CurrentTotal      int64
	Since             time.Time
	Watermark         time.Time
}

// ViewerRelation 是 viewer 对评论作者的可证实关系事实投影
// （Comment 对象本地 PersonaRelationship 事件投影），不是推荐推断；未登录恒 none。
type ViewerRelation string

const (
	ViewerRelationNone ViewerRelation = "none"
	// ViewerRelationFollowing：viewer 单向关注评论作者。
	ViewerRelationFollowing ViewerRelation = "following"
	// ViewerRelationFriend：viewer 与评论作者互相关注。
	ViewerRelationFriend ViewerRelation = "friend"
)

// SortMode 是一级评论的服务端排序档位；排序真相源唯一在服务端。
type SortMode string

const (
	// SortHot 为默认档：isPinned desc, pinnedAt desc, hotScore desc, createdAt desc, id desc。
	SortHot SortMode = "hot"
	// SortLatest：isPinned desc, pinnedAt desc, createdAt desc, id desc。
	SortLatest SortMode = "latest"
)

// ParseSortMode 解析请求 sort 参数；空值默认 hot，未知值返回 false。
func ParseSortMode(raw string) (SortMode, bool) {
	switch strings.TrimSpace(strings.ToLower(raw)) {
	case "", string(SortHot):
		return SortHot, true
	case string(SortLatest):
		return SortLatest, true
	default:
		return "", false
	}
}

// Cursor 是强类型不透明 keyset 游标，携带 CommentPageReader 置顶优先排序需要的全部元组值。
// HotScore 仅在 sort=hot 档参与比较；latest 档忽略该字段。
type Cursor struct {
	Pinned        bool   `json:"p"`
	PinnedAtNano  int64  `json:"a"`
	HotScore      int64  `json:"h,omitempty"`
	CreatedAtNano int64  `json:"c"`
	ID            string `json:"i"`
}

func EncodeCursor(cursor Cursor) string {
	if strings.TrimSpace(cursor.ID) == "" {
		return ""
	}
	raw, err := json.Marshal(cursor)
	if err != nil {
		return ""
	}
	return base64.RawURLEncoding.EncodeToString(raw)
}

func DecodeCursor(raw string) (Cursor, bool) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return Cursor{}, false
	}
	decoded, err := base64.RawURLEncoding.DecodeString(raw)
	if err != nil {
		return Cursor{}, false
	}
	var cursor Cursor
	if err := json.Unmarshal(decoded, &cursor); err != nil || strings.TrimSpace(cursor.ID) == "" {
		return Cursor{}, false
	}
	return cursor, true
}

func CursorFor(item ReadModel) Cursor {
	pinnedAt := int64(0)
	if item.PinnedAt != nil {
		pinnedAt = item.PinnedAt.UTC().UnixNano()
	}
	return Cursor{
		Pinned:        item.IsPinned,
		PinnedAtNano:  pinnedAt,
		HotScore:      item.HotScore,
		CreatedAtNano: item.CreatedAt.UTC().UnixNano(),
		ID:            item.ID,
	}
}
