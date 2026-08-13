package ports

import (
	"context"
	"strings"
)

// GatheringPostPageQuery 是 ListPostsByGathering 的 transport-neutral 输入。
// 聚合区只回答「这次共同行动沉淀了哪些公开回顾」，因此没有 viewer 维度的
// 私有分支：作者删除、转私密或未过审的内容一律不进入聚合区。
type GatheringPostPageQuery struct {
	gatheringID string
	cursor      string
	limit       int
}

func NewGatheringPostPageQuery(
	gatheringID string,
	cursor string,
	limit int,
) GatheringPostPageQuery {
	return GatheringPostPageQuery{
		gatheringID: strings.TrimSpace(gatheringID),
		cursor:      strings.TrimSpace(cursor),
		limit:       limit,
	}
}

func (q GatheringPostPageQuery) GatheringID() string { return q.gatheringID }
func (q GatheringPostPageQuery) Cursor() string      { return q.cursor }
func (q GatheringPostPageQuery) Limit() int          { return q.limit }

// GatheringPostReadRequest 只承载 application 已验证的过滤值和 cursor。
// 排序沿用公开读 keyset（publishedAt desc, _id desc），与作者公开列表一致。
type GatheringPostReadRequest struct {
	gatheringID string
	cursor      AuthorPostCursor
	limit       int
}

func NewGatheringPostReadRequest(
	gatheringID string,
	cursor AuthorPostCursor,
	limit int,
) GatheringPostReadRequest {
	return GatheringPostReadRequest{
		gatheringID: strings.TrimSpace(gatheringID),
		cursor:      cursor,
		limit:       limit,
	}
}

func (r GatheringPostReadRequest) GatheringID() string      { return r.gatheringID }
func (r GatheringPostReadRequest) Cursor() AuthorPostCursor { return r.cursor }
func (r GatheringPostReadRequest) Limit() int               { return r.limit }

func (r GatheringPostReadRequest) SortField() string { return "publishedAt" }

func (r GatheringPostReadRequest) CursorScope() string {
	return cursorScope("gathering-posts", r.gatheringID)
}

// GatheringPostPageSlice 复用作者卡片白名单：聚合区展示的就是公开 Post 卡片。
type GatheringPostPageSlice struct {
	Items      []AuthorPostItemSlice `json:"items"`
	NextCursor string                `json:"nextCursor,omitempty"`
	HasMore    bool                  `json:"hasMore"`
}

// GatheringPostReader 只读取 public + published + approved 且作者主动写入
// gatheringRef 的内容；生产实现必须在存储侧应用全部条件。
type GatheringPostReader interface {
	ListGatheringPosts(
		ctx context.Context,
		request GatheringPostReadRequest,
	) (GatheringPostPageSlice, error)
}
