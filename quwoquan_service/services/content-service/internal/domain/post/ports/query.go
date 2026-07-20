package ports

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

const (
	DefaultPostQueryPageSize = 20
	MaxPostQueryPageSize     = 100
)

// PostID、PersonaID 与内容枚举是 canonical Post 查询面的窄值类型。
// 查询面不会把聚合或动态 payload 作为跨层参数传递。
type (
	PostID          string
	PersonaID       string
	ContentIdentity string
	ContentType     string
	PostVisibility  string
	PostStatus      string
)

func NewPostID(raw string) PostID {
	return PostID(strings.TrimSpace(raw))
}

func NewPersonaID(raw string) PersonaID {
	return PersonaID(strings.TrimSpace(raw))
}

// PostRevisionSlice 是跨对象审核入口唯一允许读取的 Post 快照。
// 它刻意不暴露正文、作者、互动计数或完整聚合，避免 Report consumer
// 为绑定审核 revision 而依赖 postmodel.Post。
type PostRevisionSlice struct {
	PostID        PostID `bson:"_id"`
	Version       int64  `bson:"version"`
	ContentDigest string `bson:"contentDigest"`
}

// PostRevisionSliceReader 对“未找到”和“读取/解码失败”作严格区分。
// consumer 只能在 found=false 时确认事实；任一 error 必须阻止 checkpoint 推进。
type PostRevisionSliceReader interface {
	FindPostRevision(
		ctx context.Context,
		postID PostID,
	) (PostRevisionSlice, bool, error)
}

// PostFeedReadRequest 是首页/发现流读取已发布 Post 卡片的具名查询。
// identity/type 在进入 Reader 前已由 Feed application 归一；cursor 只允许
// 引用上一页最后一个 Post，不能承载任意 Mongo filter 或排序表达式。
type PostFeedReadRequest struct {
	identity     ContentIdentity
	contentType  ContentType
	cursorPostID PostID
	limit        int
}

func NewPostFeedReadRequest(
	identity ContentIdentity,
	contentType ContentType,
	cursorPostID PostID,
	limit int,
) PostFeedReadRequest {
	return PostFeedReadRequest{
		identity:     ContentIdentity(strings.TrimSpace(string(identity))),
		contentType:  ContentType(strings.TrimSpace(string(contentType))),
		cursorPostID: NewPostID(string(cursorPostID)),
		limit:        limit,
	}
}

func (q PostFeedReadRequest) Identity() ContentIdentity { return q.identity }
func (q PostFeedReadRequest) ContentType() ContentType  { return q.contentType }
func (q PostFeedReadRequest) CursorPostID() PostID      { return q.cursorPostID }
func (q PostFeedReadRequest) Limit() int                { return q.limit }

// ViewerContext 是只读查询的认证主体。Post 只判断作者所有权以及
// public/private 可见性；Circle 分发和成员授权由 CirclePostPlacement 查询面负责。
type ViewerContext struct {
	personaID PersonaID
}

func NewViewerContext(personaID PersonaID) ViewerContext {
	return ViewerContext{
		personaID: NewPersonaID(string(personaID)),
	}
}

func (v ViewerContext) PersonaID() PersonaID {
	return v.personaID
}

func (v ViewerContext) IsAuthenticated() bool {
	return v.personaID != ""
}

func (v ViewerContext) IsOwner(author PersonaID) bool {
	return v.personaID != "" && v.personaID == NewPersonaID(string(author))
}

// PostDetailQuery 是 GetPost 的 immutable 输入。
type PostDetailQuery struct {
	postID PostID
	viewer ViewerContext
}

func NewPostDetailQuery(postID PostID, viewer ViewerContext) PostDetailQuery {
	return PostDetailQuery{
		postID: NewPostID(string(postID)),
		viewer: viewer,
	}
}

func (q PostDetailQuery) PostID() PostID {
	return q.postID
}

func (q PostDetailQuery) Viewer() ViewerContext {
	return q.viewer
}

// AuthorPostPageQuery 是 ListUserPosts 的 transport-neutral 输入。cursor 保留
// wire 值，进入 reader 前必须由 application 解析为 AuthorPostCursor。
type AuthorPostPageQuery struct {
	authorPersonaID PersonaID
	viewer          ViewerContext
	identity        ContentIdentity
	contentType     ContentType
	visibility      PostVisibility
	cursor          string
	limit           int
}

func NewAuthorPostPageQuery(
	authorPersonaID PersonaID,
	viewer ViewerContext,
	identity ContentIdentity,
	contentType ContentType,
	visibility PostVisibility,
	cursor string,
	limit int,
) AuthorPostPageQuery {
	return AuthorPostPageQuery{
		authorPersonaID: NewPersonaID(string(authorPersonaID)),
		viewer:          viewer,
		identity:        ContentIdentity(strings.TrimSpace(string(identity))),
		contentType:     ContentType(strings.TrimSpace(string(contentType))),
		visibility:      PostVisibility(strings.TrimSpace(string(visibility))),
		cursor:          strings.TrimSpace(cursor),
		limit:           limit,
	}
}

func (q AuthorPostPageQuery) AuthorPersonaID() PersonaID {
	return q.authorPersonaID
}

func (q AuthorPostPageQuery) Viewer() ViewerContext {
	return q.viewer
}

func (q AuthorPostPageQuery) Identity() ContentIdentity {
	return q.identity
}

func (q AuthorPostPageQuery) ContentType() ContentType {
	return q.contentType
}

func (q AuthorPostPageQuery) Visibility() PostVisibility {
	return q.visibility
}

func (q AuthorPostPageQuery) Cursor() string {
	return q.cursor
}

func (q AuthorPostPageQuery) Limit() int {
	return q.limit
}

// PostCreatorDisclosureSlice 是用户可见的虚拟创作者披露，排除作者质量和
// 风险调度等内部信号。
type PostCreatorDisclosureSlice struct {
	Type        string `json:"type,omitempty" bson:"type,omitempty"`
	DisplayText string `json:"displayText,omitempty" bson:"displayText,omitempty"`
	Visible     bool   `json:"visible" bson:"visible"`
}

// PostSemanticMentionSlice 是语义标注的可读白名单。候选或审核扩展字段不
// 会越过这个 Slice。
type PostSemanticMentionSlice struct {
	MentionID   string `json:"mentionId,omitempty" bson:"mentionId,omitempty"`
	Kind        string `json:"kind,omitempty" bson:"kind,omitempty"`
	Surface     string `json:"surface,omitempty" bson:"surface,omitempty"`
	Location    string `json:"location,omitempty" bson:"location,omitempty"`
	RangeStart  int64  `json:"rangeStart,omitempty" bson:"rangeStart,omitempty"`
	RangeEnd    int64  `json:"rangeEnd,omitempty" bson:"rangeEnd,omitempty"`
	Status      string `json:"status,omitempty" bson:"status,omitempty"`
	CandidateID string `json:"candidateId,omitempty" bson:"candidateId,omitempty"`
	TargetRef   string `json:"targetRef,omitempty" bson:"targetRef,omitempty"`
}

// PostMediaItemSlice 对齐 Work Browser 的统一媒体序列。
type PostMediaItemSlice struct {
	Kind                    string `json:"kind" bson:"kind"`
	MediaAssetID            string `json:"mediaAssetId,omitempty" bson:"mediaAssetId,omitempty"`
	MediaAssetVersion       int64  `json:"mediaAssetVersion,omitempty" bson:"mediaAssetVersion,omitempty"`
	URL                     string `json:"url" bson:"url"`
	CoverURL                string `json:"coverUrl,omitempty" bson:"coverUrl,omitempty"`
	DurationMS              int64  `json:"durationMs,omitempty" bson:"durationMs,omitempty"`
	Width                   int64  `json:"width,omitempty" bson:"width,omitempty"`
	Height                  int64  `json:"height,omitempty" bson:"height,omitempty"`
	PreviewTrackManifestURL string `json:"previewTrackManifestUrl,omitempty" bson:"previewTrackManifestUrl,omitempty"`
	PreviewTrackVersion     int64  `json:"previewTrackVersion,omitempty" bson:"previewTrackVersion,omitempty"`
	Title                   string `json:"title,omitempty" bson:"title,omitempty"`
}

// PostArticleAssetSlice 是文章 manifest 中可被客户端消费的资源信息。
type PostArticleAssetSlice struct {
	AssetID              string `json:"assetId" bson:"assetId"`
	Kind                 string `json:"kind,omitempty" bson:"kind,omitempty"`
	ObjectKey            string `json:"objectKey,omitempty" bson:"objectKey,omitempty"`
	CDNURL               string `json:"cdnUrl,omitempty" bson:"cdnUrl,omitempty"`
	SHA256               string `json:"sha256,omitempty" bson:"sha256,omitempty"`
	MimeType             string `json:"mimeType,omitempty" bson:"mimeType,omitempty"`
	SourceOriginalSHA256 string `json:"sourceOriginalSha256,omitempty" bson:"sourceOriginalSha256,omitempty"`
	Caption              string `json:"caption,omitempty" bson:"caption,omitempty"`
	Role                 string `json:"role,omitempty" bson:"role,omitempty"`
	Width                int64  `json:"width,omitempty" bson:"width,omitempty"`
	Height               int64  `json:"height,omitempty" bson:"height,omitempty"`
	DurationMS           int64  `json:"durationMs,omitempty" bson:"durationMs,omitempty"`
	ThumbnailURL         string `json:"thumbnailUrl,omitempty" bson:"thumbnailUrl,omitempty"`
	CoverURL             string `json:"coverUrl,omitempty" bson:"coverUrl,omitempty"`
	CoverStrategy        string `json:"coverStrategy,omitempty" bson:"coverStrategy,omitempty"`
	CoverFrameTimeMS     int64  `json:"coverFrameTimeMs,omitempty" bson:"coverFrameTimeMs,omitempty"`
	SourceCollectionID   string `json:"sourceCollectionId,omitempty" bson:"sourceCollectionId,omitempty"`
}

type PostArticleAssetManifestSlice struct {
	Schema                int64                   `json:"schema,omitempty" bson:"schema,omitempty"`
	MarkdownDialect       string                  `json:"markdownDialect,omitempty" bson:"markdownDialect,omitempty"`
	ArticleMarkdownDigest string                  `json:"articleMarkdownDigest,omitempty" bson:"articleMarkdownDigest,omitempty"`
	DocumentSHA256        string                  `json:"documentSha256,omitempty" bson:"documentSha256,omitempty"`
	AssetManifestSHA256   string                  `json:"assetManifestSha256,omitempty" bson:"assetManifestSha256,omitempty"`
	DocumentVersionSHA256 string                  `json:"documentVersionSha256,omitempty" bson:"documentVersionSha256,omitempty"`
	Assets                []PostArticleAssetSlice `json:"assets,omitempty" bson:"assets,omitempty"`
}

type PostArticleRenderProfileSlice struct {
	Template       string `json:"template,omitempty" bson:"template,omitempty"`
	FontPreset     string `json:"fontPreset,omitempty" bson:"fontPreset,omitempty"`
	PaperThemeMode string `json:"paperThemeMode,omitempty" bson:"paperThemeMode,omitempty"`
	PaperTexture   string `json:"paperTexture,omitempty" bson:"paperTexture,omitempty"`
}

type PostEntityMentionSlice struct {
	SubjectType string `json:"subjectType" bson:"subjectType"`
	SubjectID   string `json:"subjectId" bson:"subjectId"`
	HomepageID  string `json:"homepageId" bson:"homepageId"`
	DisplayName string `json:"displayName" bson:"displayName"`
	RangeStart  int64  `json:"rangeStart" bson:"rangeStart"`
	RangeEnd    int64  `json:"rangeEnd" bson:"rangeEnd"`
}

type PostLocationSlice struct {
	Latitude  float64 `json:"latitude" bson:"latitude"`
	Longitude float64 `json:"longitude" bson:"longitude"`
}

type PostHomepageSnapshotSlice struct {
	CanonicalEntityID string `json:"canonicalEntityId,omitempty" bson:"canonicalEntityId,omitempty"`
	Title             string `json:"title,omitempty" bson:"title,omitempty"`
	Subtitle          string `json:"subtitle,omitempty" bson:"subtitle,omitempty"`
	CoverURL          string `json:"coverUrl,omitempty" bson:"coverUrl,omitempty"`
}

// PostDetailSlice 是 GetPost 的显式 read model。它有意不含 Version、
// embedding、contentDigest、authorQualitySignals 以及 PII 发布位置/设备信息，
// 不能被误作 Post 聚合继续写回。ModerationStatus 只供 application 做
// 服务端可见性判定，json:"-" 保证它不进入任何客户端响应。
type PostDetailSlice struct {
	PostID                  PostID                         `json:"postId" bson:"_id"`
	AuthorPersonaID         PersonaID                      `json:"authorId" bson:"authorId"`
	CreatorProfileID        string                         `json:"creatorProfileId,omitempty" bson:"creatorProfileId,omitempty"`
	CreatorArchetype        string                         `json:"creatorArchetype,omitempty" bson:"creatorArchetype,omitempty"`
	CreatorProfileVersion   string                         `json:"creatorProfileVersion,omitempty" bson:"creatorProfileVersion,omitempty"`
	CreatorDisclosure       *PostCreatorDisclosureSlice    `json:"creatorDisclosure,omitempty" bson:"creatorDisclosure,omitempty"`
	ExperienceClaimMode     string                         `json:"experienceClaimMode,omitempty" bson:"experienceClaimMode,omitempty"`
	AuthorDisplayName       string                         `json:"authorDisplayNameSnapshot,omitempty" bson:"authorDisplayNameSnapshot,omitempty"`
	AuthorAvatarURL         string                         `json:"authorAvatarUrlSnapshot,omitempty" bson:"authorAvatarUrlSnapshot,omitempty"`
	PersonaContextVersion   int64                          `json:"personaContextVersion,omitempty" bson:"personaContextVersion,omitempty"`
	ContentType             ContentType                    `json:"contentType" bson:"contentType"`
	ContentIdentity         ContentIdentity                `json:"contentIdentity,omitempty" bson:"contentIdentity,omitempty"`
	Title                   string                         `json:"title,omitempty" bson:"title,omitempty"`
	Body                    string                         `json:"body,omitempty" bson:"body,omitempty"`
	Summary                 string                         `json:"summary,omitempty" bson:"summary,omitempty"`
	TagRefs                 []string                       `json:"tagRefs,omitempty" bson:"tagRefs,omitempty"`
	EntityRefs              []string                       `json:"entityRefs,omitempty" bson:"entityRefs,omitempty"`
	SemanticMentions        []PostSemanticMentionSlice     `json:"semanticMentions,omitempty" bson:"semanticMentions,omitempty"`
	MediaAssetIDs           []string                       `json:"mediaAssetIds,omitempty" bson:"mediaAssetIds,omitempty"`
	MediaURLs               []string                       `json:"mediaUrls,omitempty" bson:"mediaUrls,omitempty"`
	MediaItems              []PostMediaItemSlice           `json:"mediaItems,omitempty" bson:"mediaItems,omitempty"`
	CoverURL                string                         `json:"coverUrl,omitempty" bson:"coverUrl,omitempty"`
	ThumbnailURL            string                         `json:"thumbnailUrl,omitempty" bson:"thumbnailUrl,omitempty"`
	Width                   int64                          `json:"width,omitempty" bson:"width,omitempty"`
	Height                  int64                          `json:"height,omitempty" bson:"height,omitempty"`
	DurationMS              int64                          `json:"durationMs,omitempty" bson:"durationMs,omitempty"`
	ArticleMarkdown         string                         `json:"articleMarkdown,omitempty" bson:"articleMarkdown,omitempty"`
	MarkdownDialect         string                         `json:"markdownDialect,omitempty" bson:"markdownDialect,omitempty"`
	ArticleMarkdownDigest   string                         `json:"articleMarkdownDigest,omitempty" bson:"articleMarkdownDigest,omitempty"`
	ArticleAssetManifest    *PostArticleAssetManifestSlice `json:"articleAssetManifest,omitempty" bson:"articleAssetManifest,omitempty"`
	ArticleRenderProfile    *PostArticleRenderProfileSlice `json:"articleRenderProfile,omitempty" bson:"articleRenderProfile,omitempty"`
	ContentVertical         string                         `json:"contentVertical,omitempty" bson:"contentVertical,omitempty"`
	EntityMentions          []PostEntityMentionSlice       `json:"entityMentions,omitempty" bson:"entityMentions,omitempty"`
	ArticleTemplate         string                         `json:"articleTemplate,omitempty" bson:"articleTemplate,omitempty"`
	ArticleFontPreset       string                         `json:"articleFontPreset,omitempty" bson:"articleFontPreset,omitempty"`
	VideoURL                string                         `json:"videoUrl,omitempty" bson:"videoUrl,omitempty"`
	CoverStrategy           string                         `json:"coverStrategy,omitempty" bson:"coverStrategy,omitempty"`
	CoverFrameTimeMS        int64                          `json:"coverFrameTimeMs,omitempty" bson:"coverFrameTimeMs,omitempty"`
	Location                *PostLocationSlice             `json:"location,omitempty" bson:"location,omitempty"`
	LocationName            string                         `json:"locationName,omitempty" bson:"locationName,omitempty"`
	PrimaryHomepageID       string                         `json:"primaryHomepageId,omitempty" bson:"primaryHomepageId,omitempty"`
	CanonicalEntityID       string                         `json:"canonicalEntityId,omitempty" bson:"canonicalEntityId,omitempty"`
	PrimaryHomepageType     string                         `json:"primaryHomepageType,omitempty" bson:"primaryHomepageType,omitempty"`
	PrimaryHomepageSnapshot *PostHomepageSnapshotSlice     `json:"primaryHomepageSnapshot,omitempty" bson:"primaryHomepageSnapshot,omitempty"`
	Status                  PostStatus                     `json:"status" bson:"status"`
	Visibility              PostVisibility                 `json:"visibility" bson:"visibility"`
	ModerationStatus        string                         `json:"-" bson:"moderationStatus"`
	AssistantUsePolicy      string                         `json:"assistantUsePolicy,omitempty" bson:"assistantUsePolicy,omitempty"`
	SourcePostID            string                         `json:"sourcePostId,omitempty" bson:"sourcePostId,omitempty"`
	SourceType              string                         `json:"sourceType,omitempty" bson:"sourceType,omitempty"`
	IllustrationAssetID     string                         `json:"illustrationAssetId,omitempty" bson:"illustrationAssetId,omitempty"`
	LikeCount               int64                          `json:"likeCount" bson:"likeCount"`
	CommentCount            int64                          `json:"commentCount" bson:"commentCount"`
	PinnedCommentID         string                         `json:"pinnedCommentId,omitempty" bson:"pinnedCommentId,omitempty"`
	ShareCount              int64                          `json:"shareCount" bson:"shareCount"`
	ViewCount               int64                          `json:"viewCount" bson:"viewCount"`
	HelperReadSummary       string                         `json:"helperReadSummary,omitempty" bson:"helperReadSummary,omitempty"`
	CreatedAt               time.Time                      `json:"createdAt" bson:"createdAt"`
	UpdatedAt               time.Time                      `json:"updatedAt" bson:"updatedAt"`
	PublishedAt             time.Time                      `json:"publishedAt,omitempty" bson:"publishedAt,omitempty"`
	LastActiveAt            time.Time                      `json:"lastActiveAt,omitempty" bson:"lastActiveAt,omitempty"`
	SourceTaskID            string                         `json:"sourceTaskId,omitempty" bson:"sourceTaskId,omitempty"`
}

// AuthorPostItemSlice 是个人主页创作页的紧凑卡片白名单。它不会载入详情
// 正文 Markdown、manifest 或其他大字段。
type AuthorPostItemSlice struct {
	PostID                PostID          `json:"postId" bson:"_id"`
	AuthorPersonaID       PersonaID       `json:"authorId" bson:"authorId"`
	ContentType           ContentType     `json:"contentType" bson:"contentType"`
	ContentIdentity       ContentIdentity `json:"contentIdentity,omitempty" bson:"contentIdentity,omitempty"`
	Title                 string          `json:"title,omitempty" bson:"title,omitempty"`
	Body                  string          `json:"body,omitempty" bson:"body,omitempty"`
	Summary               string          `json:"summary,omitempty" bson:"summary,omitempty"`
	CoverURL              string          `json:"coverUrl,omitempty" bson:"coverUrl,omitempty"`
	ThumbnailURL          string          `json:"thumbnailUrl,omitempty" bson:"thumbnailUrl,omitempty"`
	MediaURLs             []string        `json:"mediaUrls,omitempty" bson:"mediaUrls,omitempty"`
	VideoURL              string          `json:"videoUrl,omitempty" bson:"videoUrl,omitempty"`
	ArticleTemplate       string          `json:"articleTemplate,omitempty" bson:"articleTemplate,omitempty"`
	ArticleFontPreset     string          `json:"articleFontPreset,omitempty" bson:"articleFontPreset,omitempty"`
	ContentVertical       string          `json:"contentVertical,omitempty" bson:"contentVertical,omitempty"`
	LocationName          string          `json:"locationName,omitempty" bson:"locationName,omitempty"`
	PrimaryHomepageID     string          `json:"primaryHomepageId,omitempty" bson:"primaryHomepageId,omitempty"`
	CanonicalEntityID     string          `json:"canonicalEntityId,omitempty" bson:"canonicalEntityId,omitempty"`
	Status                PostStatus      `json:"status" bson:"status"`
	Visibility            PostVisibility  `json:"visibility" bson:"visibility"`
	LikeCount             int64           `json:"likeCount" bson:"likeCount"`
	CommentCount          int64           `json:"commentCount" bson:"commentCount"`
	ShareCount            int64           `json:"shareCount" bson:"shareCount"`
	ViewCount             int64           `json:"viewCount" bson:"viewCount"`
	CreatedAt             time.Time       `json:"createdAt" bson:"createdAt"`
	UpdatedAt             time.Time       `json:"updatedAt" bson:"updatedAt"`
	PublishedAt           time.Time       `json:"publishedAt,omitempty" bson:"publishedAt,omitempty"`
	LastActiveAt          time.Time       `json:"lastActiveAt,omitempty" bson:"lastActiveAt,omitempty"`
	AuthorDisplayName     string          `json:"authorDisplayNameSnapshot,omitempty" bson:"authorDisplayNameSnapshot,omitempty"`
	AuthorAvatarURL       string          `json:"authorAvatarUrlSnapshot,omitempty" bson:"authorAvatarUrlSnapshot,omitempty"`
	PersonaContextVersion int64           `json:"personaContextVersion,omitempty" bson:"personaContextVersion,omitempty"`
}

type AuthorPostPageSlice struct {
	Items      []AuthorPostItemSlice `json:"items"`
	NextCursor string                `json:"nextCursor,omitempty"`
	HasMore    bool                  `json:"hasMore"`
}

// PostFeedItemSlice 是 Feed application 唯一可读取的 Post 卡片投影。
// 它不暴露聚合 Version、幂等 receipt、outbox、审核内部字段、设备原始信息或
// 动态 Map；媒体尺寸在 persistence adapter 内归一为显式数值。
type PostFeedItemSlice struct {
	PostID             PostID          `json:"postId" bson:"_id"`
	AuthorPersonaID    PersonaID       `json:"authorId" bson:"authorId"`
	AuthorDisplayName  string          `json:"authorDisplayName,omitempty" bson:"authorDisplayNameSnapshot,omitempty"`
	AuthorAvatarURL    string          `json:"authorAvatarUrl,omitempty" bson:"authorAvatarUrlSnapshot,omitempty"`
	ContentType        ContentType     `json:"contentType" bson:"contentType"`
	ContentIdentity    ContentIdentity `json:"contentIdentity,omitempty" bson:"contentIdentity,omitempty"`
	AssistantUsePolicy string          `json:"assistantUsePolicy,omitempty" bson:"assistantUsePolicy,omitempty"`
	Title              string          `json:"title,omitempty" bson:"title,omitempty"`
	Body               string          `json:"body,omitempty" bson:"body,omitempty"`
	Summary            string          `json:"summary,omitempty" bson:"summary,omitempty"`
	MediaURLs          []string        `json:"mediaUrls,omitempty" bson:"mediaUrls,omitempty"`
	VideoURL           string          `json:"videoUrl,omitempty" bson:"videoUrl,omitempty"`
	CoverURL           string          `json:"coverUrl,omitempty" bson:"coverUrl,omitempty"`
	ThumbnailURL       string          `json:"thumbnailUrl,omitempty" bson:"thumbnailUrl,omitempty"`
	CoverStrategy      string          `json:"coverStrategy,omitempty" bson:"coverStrategy,omitempty"`
	CoverFrameTimeMS   int64           `json:"coverFrameTimeMs,omitempty" bson:"coverFrameTimeMs,omitempty"`
	DurationMS         int64           `json:"durationMs,omitempty" bson:"-"`
	Width              int64           `json:"width,omitempty" bson:"-"`
	Height             int64           `json:"height,omitempty" bson:"-"`
	TagRefs            []string        `json:"tagRefs,omitempty" bson:"tagRefs,omitempty"`
	EntityRefs         []string        `json:"entityRefs,omitempty" bson:"entityRefs,omitempty"`
	Visibility         PostVisibility  `json:"visibility,omitempty" bson:"visibility,omitempty"`
	ContentVertical    string          `json:"contentVertical,omitempty" bson:"contentVertical,omitempty"`
	SourceTaskID       string          `json:"sourceTaskId,omitempty" bson:"sourceTaskId,omitempty"`
	LikeCount          int64           `json:"likeCount" bson:"likeCount"`
	CommentCount       int64           `json:"commentCount" bson:"commentCount"`
	ShareCount         int64           `json:"shareCount" bson:"shareCount"`
	CreatedAt          time.Time       `json:"createdAt" bson:"createdAt"`
	UpdatedAt          time.Time       `json:"updatedAt" bson:"updatedAt"`
	PublishedAt        time.Time       `json:"publishedAt,omitempty" bson:"publishedAt,omitempty"`
}

type PostFeedSlice struct {
	Items []PostFeedItemSlice
}

// PostDetailReader 与 AuthorPostReader 是两个独立 query port。Post
// aggregate store 只能服务命令路径，不能替代任何一个 reader。
type PostDetailReader interface {
	FindPostDetail(ctx context.Context, postID PostID) (PostDetailSlice, bool, error)
}

type AuthorPostReader interface {
	ListAuthorPosts(ctx context.Context, request AuthorPostReadRequest) (AuthorPostPageSlice, error)
}

// ViewerBlockReader 暴露 user 域 PersonaBlocked 事实投影的只读判定，用于
// 作者读路径的服务端 block 强制。它不信任客户端 header，也不回读 user 域存储。
type ViewerBlockReader interface {
	IsBlockedBetween(ctx context.Context, viewer PersonaID, author PersonaID) (bool, error)
}

// PostFeedReader 只读取公开且已发布的 Feed 卡片 Slice。生产实现必须在存储侧
// 应用 identity/type/keyset 条件；禁止先扫 ListPublished 再在内存中过滤。
type PostFeedReader interface {
	FindPublishedFeedPost(ctx context.Context, postID PostID) (PostFeedItemSlice, bool, error)
	// FindPublishedFeedPosts 按 ids 批量读取（N3-1 消除 feed 装配 N+1）：
	// 生产实现必须单次 $in 查询取回；返回 map 以 PostID 为键，未命中
	// （不存在/未发布/不可见）的 id 直接缺席，调用方按召回顺序自行装配。
	FindPublishedFeedPosts(ctx context.Context, postIDs []PostID) (map[PostID]PostFeedItemSlice, error)
	ListPublishedFeedPosts(ctx context.Context, request PostFeedReadRequest) (PostFeedSlice, error)
}

type AuthorPostAccessScope string

const (
	AuthorPostAccessPublic AuthorPostAccessScope = "public"
	AuthorPostAccessOwner  AuthorPostAccessScope = "owner"
)

// AuthorPostCursor 为作者列表的 keyset cursor。cursor scope 绑定 author、
// access scope 与过滤条件，不能跨查询复用。
type AuthorPostCursor struct {
	scope  string
	sortAt time.Time
	postID PostID
}

func NewAuthorPostCursor(scope string, sortAt time.Time, postID PostID) AuthorPostCursor {
	return AuthorPostCursor{
		scope:  strings.TrimSpace(scope),
		sortAt: sortAt.UTC(),
		postID: NewPostID(string(postID)),
	}
}

func (c AuthorPostCursor) IsSet() bool {
	return c.scope != ""
}

func (c AuthorPostCursor) Scope() string {
	return c.scope
}

func (c AuthorPostCursor) SortAt() time.Time {
	return c.sortAt
}

func (c AuthorPostCursor) PostID() PostID {
	return c.postID
}

type authorPostCursorWire struct {
	Version        int    `json:"v"`
	Scope          string `json:"s"`
	SortAtUnixNano int64  `json:"t"`
	PostID         string `json:"i"`
}

func (c AuthorPostCursor) Encode() string {
	if !c.IsSet() {
		return ""
	}
	wire, _ := json.Marshal(authorPostCursorWire{
		Version:        1,
		Scope:          c.scope,
		SortAtUnixNano: c.sortAt.UnixNano(),
		PostID:         string(c.postID),
	})
	return base64.RawURLEncoding.EncodeToString(wire)
}

func ParseAuthorPostCursor(raw string) (AuthorPostCursor, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return AuthorPostCursor{}, nil
	}
	if len(raw) > 1024 {
		return AuthorPostCursor{}, fmt.Errorf("author post cursor exceeds maximum length")
	}
	payload, err := base64.RawURLEncoding.DecodeString(raw)
	if err != nil {
		return AuthorPostCursor{}, fmt.Errorf("decode author post cursor: %w", err)
	}
	var wire authorPostCursorWire
	if err := json.Unmarshal(payload, &wire); err != nil {
		return AuthorPostCursor{}, fmt.Errorf("decode author post cursor payload: %w", err)
	}
	if wire.Version != 1 ||
		strings.TrimSpace(wire.Scope) == "" ||
		wire.SortAtUnixNano <= 0 ||
		strings.TrimSpace(wire.PostID) == "" {
		return AuthorPostCursor{}, fmt.Errorf("author post cursor has invalid shape")
	}
	return NewAuthorPostCursor(
		wire.Scope,
		time.Unix(0, wire.SortAtUnixNano).UTC(),
		NewPostID(wire.PostID),
	), nil
}

// AuthorPostReadRequest 只承载 application 已验证的过滤值和 cursor。
type AuthorPostReadRequest struct {
	authorPersonaID PersonaID
	accessScope     AuthorPostAccessScope
	identity        ContentIdentity
	contentType     ContentType
	visibility      PostVisibility
	cursor          AuthorPostCursor
	limit           int
}

func NewAuthorPostReadRequest(
	authorPersonaID PersonaID,
	accessScope AuthorPostAccessScope,
	identity ContentIdentity,
	contentType ContentType,
	visibility PostVisibility,
	cursor AuthorPostCursor,
	limit int,
) AuthorPostReadRequest {
	return AuthorPostReadRequest{
		authorPersonaID: NewPersonaID(string(authorPersonaID)),
		accessScope:     accessScope,
		identity:        identity,
		contentType:     contentType,
		visibility:      visibility,
		cursor:          cursor,
		limit:           limit,
	}
}

func (r AuthorPostReadRequest) AuthorPersonaID() PersonaID {
	return r.authorPersonaID
}

func (r AuthorPostReadRequest) AccessScope() AuthorPostAccessScope {
	return r.accessScope
}

func (r AuthorPostReadRequest) Identity() ContentIdentity {
	return r.identity
}

func (r AuthorPostReadRequest) ContentType() ContentType {
	return r.contentType
}

func (r AuthorPostReadRequest) Visibility() PostVisibility {
	return r.visibility
}

func (r AuthorPostReadRequest) Cursor() AuthorPostCursor {
	return r.cursor
}

func (r AuthorPostReadRequest) Limit() int {
	return r.limit
}

func (r AuthorPostReadRequest) SortField() string {
	if r.accessScope == AuthorPostAccessOwner {
		return "updatedAt"
	}
	return "publishedAt"
}

func (r AuthorPostReadRequest) CursorScope() string {
	return cursorScope(
		"author-posts",
		string(r.authorPersonaID),
		string(r.accessScope),
		string(r.identity),
		string(r.contentType),
		string(r.visibility),
	)
}

func cursorScope(parts ...string) string {
	hash := sha256.New()
	for _, part := range parts {
		_, _ = hash.Write([]byte(part))
		_, _ = hash.Write([]byte{0})
	}
	return hex.EncodeToString(hash.Sum(nil))
}
