package ports

import (
	"context"
	"time"

	activitymodel "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/domain/model"
)

type Cursor struct {
	OccurredAt time.Time
	ActivityID string
}

type PageRequest struct {
	OwnerPersonaID string
	Direction      string
	ActivityType   string
	Cursor         Cursor
	Limit          int
}

type Page struct {
	Items   []activitymodel.Activity
	HasMore bool
}

type PostSlice struct {
	ID                        string
	Version                   int64
	AuthorPersonaID           string
	AuthorDisplayNameSnapshot string
	AuthorAvatarURLSnapshot   string
	ContentType               string
	Title                     string
	Body                      string
	Summary                   string
	CoverURL                  string
	MediaURLs                 []string
	// 媒体条目的 typed 交付声明（DEC-033）：预览图在 research 相位是相对私有
	// CAS 引用，投影必须把配对的资产标识与访问模式一并交出。
	MediaItems []PostMediaSlice
	Status     string
	Visibility string
	DeletedAt  time.Time
}

// PostMediaSlice 是投影所需的媒体条目最小事实：URL 与其配对的交付声明。
type PostMediaSlice struct {
	URL          string
	CoverURL     string
	MediaAssetID string
	CoverAssetID string
	AccessMode   string
}

type CommentSlice struct {
	ID                        string
	Version                   int64
	PostID                    string
	AuthorPersonaID           string
	AuthorDisplayNameSnapshot string
	AuthorAvatarURLSnapshot   string
	Content                   string
	ReplyToCommentID          string
	ReplyToPersonaID          string
	ParentCommentID           string
	Status                    string
	CreatedAt                 time.Time
}

// ProjectionSourceReader is used only by durable outbox consumers. HTTP query
// paths never receive this port and therefore cannot join source write models.
type ProjectionSourceReader interface {
	FindPost(context.Context, string) (PostSlice, bool, error)
	FindComment(context.Context, string) (CommentSlice, bool, error)
}

type ActivityReader interface {
	List(context.Context, PageRequest) (Page, error)
	CanAppendReadFact(
		ctx context.Context,
		ownerPersonaID string,
		activityID string,
	) (bool, error)
}

type ActivityProjectionWriter interface {
	Upsert(context.Context, activitymodel.Activity) error
	DeactivateActivity(
		ctx context.Context,
		activityID string,
		sourceVersion int64,
	) error
	SetCommentViewerReaction(
		ctx context.Context,
		commentID string,
		ownerPersonaID string,
		reaction string,
		sourceVersion int64,
	) error
	MarkTargetUnavailable(
		ctx context.Context,
		postID string,
		targetVersion int64,
		at time.Time,
	) error
	ApplyReadState(
		ctx context.Context,
		ownerPersonaID string,
		activityID string,
		state string,
		at time.Time,
	) error
}
