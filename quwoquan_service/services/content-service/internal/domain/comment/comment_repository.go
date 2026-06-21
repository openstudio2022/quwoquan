// Package comment defines the storage-agnostic domain contract for post
// comments. Interfaces live in the domain layer (R01); concrete Mongo / Redis /
// in-memory implementations live in infrastructure and must never leak storage
// drivers back into this package (R10).
package comment

import (
	"context"
	"time"

	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

// SortMode enumerates the ordering strategy for top-level comment listing.
// Pinned comments always precede non-pinned ones regardless of the mode.
type SortMode string

const (
	// SortRecommended orders by the write-time recommendedScore snapshot.
	SortRecommended SortMode = "recommended"
	// SortLatest orders by createdAt descending.
	SortLatest SortMode = "latest"
	// SortMostLiked orders by likeCount descending (createdAt tiebreak).
	SortMostLiked SortMode = "most_liked"
)

// NormalizeSortMode maps a raw client value to a known SortMode (default
// recommended), keeping the single source of truth in the domain layer.
func NormalizeSortMode(raw string) SortMode {
	switch SortMode(raw) {
	case SortLatest:
		return SortLatest
	case SortMostLiked:
		return SortMostLiked
	default:
		return SortRecommended
	}
}

// Reaction is the three-state per-user comment reaction.
type Reaction string

const (
	ReactionNone    Reaction = "none"
	ReactionLike    Reaction = "like"
	ReactionDislike Reaction = "dislike"
)

// NormalizeReaction coerces a raw value into a valid Reaction, reporting whether
// the input was a recognized state.
func NormalizeReaction(raw string) (Reaction, bool) {
	switch Reaction(raw) {
	case ReactionLike:
		return ReactionLike, true
	case ReactionDislike:
		return ReactionDislike, true
	case ReactionNone, "":
		return ReactionNone, true
	default:
		return ReactionNone, false
	}
}

// Page is one progressive page of comments plus the next-page cursor.
// TotalCount is reported separately by the count APIs so it always reflects the
// authoritative DB count (single source of truth).
type Page struct {
	Comments   []postmodel.Comment
	NextCursor string
}

// Reader covers single-document reads and authoritative counts.
type Reader interface {
	FindByID(ctx context.Context, id string) (*postmodel.Comment, bool)
	// CountByPost counts every non-deleted comment (top-level and replies) for a
	// post. This is the authoritative source for Post.commentCount and
	// ListComments.totalCount.
	CountByPost(ctx context.Context, postID string) (int64, error)
	// CountReplies counts non-deleted replies under a top-level comment. This is
	// the authoritative source for ListCommentReplies.totalCount.
	CountReplies(ctx context.Context, postID, parentID string) (int64, error)
	// CountCreatedBetween counts comments created in the half-open window
	// (since, until] regardless of current status (a comment created then later
	// deleted still counts as "created since"). Backs GetCommentCountsDelta's
	// createdSinceCount. since.IsZero() means "from the beginning".
	CountCreatedBetween(ctx context.Context, postID string, since, until time.Time) (int64, error)
	// CountDeletedBetween counts soft-deleted comments whose deletedAt falls in
	// the half-open window (since, until]. Backs GetCommentCountsDelta's
	// deletedSinceCount. since.IsZero() means "from the beginning".
	CountDeletedBetween(ctx context.Context, postID string, since, until time.Time) (int64, error)
}

// Writer covers all comment mutations. recommendedScore is computed by the
// application layer (domain ranking logic) and passed in, so storage stays dumb.
type Writer interface {
	Create(ctx context.Context, c *postmodel.Comment) error
	// SoftDelete marks the comment deleted (status=deleted) and returns the
	// pre-delete snapshot so callers can reconcile parent/post bookkeeping.
	SoftDelete(ctx context.Context, id string, deletedAt time.Time) (*postmodel.Comment, bool, error)
	// SetPinned toggles pin state for a top-level comment.
	SetPinned(ctx context.Context, id string, pinned bool, pinnedAt time.Time) (bool, error)
	// AdjustReplyCount atomically applies delta to replyCount and stores the
	// supplied recommendedScore, returning the updated document.
	AdjustReplyCount(ctx context.Context, id string, delta int64, recommendedScore float64) (*postmodel.Comment, bool, error)
	// SetReactionState stores authoritative like/dislike counts plus the new
	// recommendedScore snapshot for one comment.
	SetReactionState(ctx context.Context, id string, likeCount, dislikeCount int64, recommendedScore float64) (bool, error)
	// SetAttachments stores attachment ids and snapshots (late media binding).
	SetAttachments(ctx context.Context, id string, attachmentIDs []string, attachments []map[string]any) (bool, error)
}

// Query covers list/projection reads. Kept separate from Reader/Writer so no
// single interface exceeds the size budget (R02).
type Query interface {
	// ListTopLevel returns top-level comments for a post, pinned-first then by
	// mode, paginated by the previous page's last comment id.
	ListTopLevel(ctx context.Context, postID string, mode SortMode, cursor string, limit int) (Page, error)
	// ListReplies returns non-deleted replies under a top-level comment,
	// newest-first, paginated by the previous page's last reply id.
	ListReplies(ctx context.Context, postID, parentID, cursor string, limit int) (Page, error)
	// RepliesForParents batch-fetches up to perParent newest replies for each
	// parent id in a single query (reply-preview fill without N+1).
	RepliesForParents(ctx context.Context, postID string, parentIDs []string, perParent int) (map[string][]postmodel.Comment, error)
	// ListByAuthor lists a user's own non-deleted comments, newest-first.
	ListByAuthor(ctx context.Context, authorID, cursor string, limit int) (Page, error)
	// ListReceivedByPostAuthor lists non-deleted comments on the given posts
	// authored by someone other than postAuthorID, newest-first.
	ListReceivedByPostAuthor(ctx context.Context, postAuthorID string, postIDs []string, cursor string, limit int) (Page, error)
	// ListByPostForActivity returns every non-deleted comment on a post for the
	// profile interaction feed (bounded by the caller's limit downstream).
	ListByPostForActivity(ctx context.Context, postID string) ([]postmodel.Comment, error)
}

// Store is the composite comment repository injected into the application layer.
type Store interface {
	Reader
	Writer
	Query
}

// ReactionStore persists three-state per-user comment reactions. Membership is
// authoritative here; per-comment like/dislike counts are derived via Counts.
type ReactionStore interface {
	// Set upserts (like/dislike) or removes (none) the user's reaction.
	Set(ctx context.Context, commentID, userID string, reaction Reaction) error
	// Get returns a user's current reaction for a comment.
	Get(ctx context.Context, commentID, userID string) (Reaction, error)
	// Counts returns authoritative like/dislike counts for a comment.
	Counts(ctx context.Context, commentID string) (like int64, dislike int64, err error)
	// ReactionsForUser batch-resolves a user's reactions across comment ids.
	ReactionsForUser(ctx context.Context, userID string, commentIDs []string) (map[string]Reaction, error)
	// PurgeComment removes all reactions for a hard/soft-deleted comment.
	PurgeComment(ctx context.Context, commentID string) error
}
