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
	Status                    Status
	IsPinned                  bool
	PinnedAt                  *time.Time
	CreatedAt                 time.Time
	UpdatedAt                 time.Time
	DeletedAt                 *time.Time
}

func (r ReadModel) Clone() ReadModel {
	r.AttachmentMediaIDs = cloneStrings(r.AttachmentMediaIDs)
	r.Mentions = cloneMentions(r.Mentions)
	r.PinnedAt = cloneTime(r.PinnedAt)
	r.DeletedAt = cloneTime(r.DeletedAt)
	return r
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

// Cursor 是强类型不透明 keyset 游标，携带 CommentPageReader 置顶优先排序需要的全部元组值。
type Cursor struct {
	Pinned        bool   `json:"p"`
	PinnedAtNano  int64  `json:"a"`
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
		CreatedAtNano: item.CreatedAt.UTC().UnixNano(),
		ID:            item.ID,
	}
}
