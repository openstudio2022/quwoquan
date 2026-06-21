package application

import (
	"context"
	"math"
	"strings"
	"time"

	commentdomain "quwoquan_service/services/content-service/internal/domain/comment"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

// commentReplyPreviewCount mirrors content_app_config_client.yaml#comment_defaults
// (reply_preview_count). Kept as a single source consumed by both the wire
// projection and the preview prefetch so they never drift.
const commentReplyPreviewCount = 1

// commentTopLevelModel reports whether a comment is a top-level comment (no
// parent / reply target). Mirrors the prior commentParentID(map) == "" check.
func commentTopLevelModel(c postmodel.Comment) bool {
	return strings.TrimSpace(c.ParentCommentId) == "" && strings.TrimSpace(c.ReplyToCommentId) == ""
}

// commentDeletedAtWire renders the nullable deletedAt timestamp: RFC3339 for
// soft-deleted records (retained for audit / delta counting), empty string for
// live comments (the NULLABLE contract default).
func commentDeletedAtWire(c postmodel.Comment) string {
	if c.DeletedAt.IsZero() {
		return ""
	}
	return c.DeletedAt.UTC().Format(time.RFC3339)
}

// commentParentOfModel returns the effective parent id of a comment (explicit
// parentCommentId first, else the reply target id).
func commentParentOfModel(c postmodel.Comment) string {
	if parent := strings.TrimSpace(c.ParentCommentId); parent != "" {
		return parent
	}
	return strings.TrimSpace(c.ReplyToCommentId)
}

// commentRecommendedScoreModel is the strong-typed twin of the prior
// commentRecommendedScoreAt(map): deterministic write-time score combining Wilson
// quality lower bound, log-damped engagement, report penalty and 48h freshness
// decay. Given (stats, createdAt, now) it is fully deterministic so Mongo and the
// in-memory store rank identically.
func commentRecommendedScoreModel(c postmodel.Comment, now time.Time) float64 {
	likes := c.LikeCount
	dislikes := c.DislikeCount
	replies := c.ReplyCount
	const reports int64 = 0 // reportCount is not yet mutated anywhere (always 0)

	quality := wilsonLowerBound(likes, likes+dislikes)
	engagement := math.Log1p(float64(maxInt64(likes, 0)))*12.0 +
		math.Log1p(float64(maxInt64(replies, 0)))*8.0
	penalty := float64(maxInt64(reports, 0)) * 20.0

	ageHours := now.Sub(c.CreatedAt).Hours()
	if ageHours < 0 {
		ageHours = 0
	}
	freshness := 30.0 * math.Exp(-ageHours/48.0)

	return quality*60.0 + engagement - penalty + freshness
}

// commentReactionLookup carries pre-resolved reactions for a batch of comments so
// the wire builder performs zero per-comment storage I/O (avoids N+1, R25).
type commentReactionLookup struct {
	viewer map[string]commentdomain.Reaction // commentID -> viewer's reaction
	author map[string]commentdomain.Reaction // commentID -> post author's reaction
}

func (l commentReactionLookup) viewerReaction(commentID string) string {
	if l.viewer == nil {
		return string(commentdomain.ReactionNone)
	}
	if r, ok := l.viewer[commentID]; ok && r != commentdomain.ReactionNone {
		return string(r)
	}
	return string(commentdomain.ReactionNone)
}

func (l commentReactionLookup) authorLiked(commentID string) bool {
	if l.author == nil {
		return false
	}
	return l.author[commentID] == commentdomain.ReactionLike
}

// commentPostSummary is the small denormalized post header embedded in each
// projected comment (postSummary). Empty when the post cannot be resolved.
type commentPostContext struct {
	authorID string
	summary  map[string]any
}

func (s *PostService) resolvePostContext(ctx context.Context, postID string) commentPostContext {
	post, ok := s.store.FindByID(ctx, strings.TrimSpace(postID))
	if !ok {
		return commentPostContext{}
	}
	return commentPostContext{
		authorID: strings.TrimSpace(post.AuthorId),
		summary: map[string]any{
			"postId":      post.ID,
			"contentType": post.ContentType,
			"title":       defaultString(strings.TrimSpace(post.Title), strings.TrimSpace(post.Summary)),
			"coverUrl":    post.CoverUrl,
			"status":      post.Status,
			"visibility":  post.Visibility,
			"authorId":    post.AuthorId,
		},
	}
}

// anySliceOrEmpty normalizes attachment/mention list fields so the wire always
// exposes an array (never null), matching the prior create-time defaults.
func anySliceOrEmpty(v any) any {
	switch typed := v.(type) {
	case nil:
		return []any{}
	case []string:
		if typed == nil {
			return []string{}
		}
		return typed
	case []map[string]any:
		if typed == nil {
			return []map[string]any{}
		}
		return typed
	case []any:
		if typed == nil {
			return []any{}
		}
		return typed
	default:
		return v
	}
}

// buildCommentWire renders a postmodel.Comment into the wire map shape consumed by
// the App. Derived fields (viewerReaction/authorLiked/canPin/...) come from the
// pre-resolved lookup + post context so this is pure and storage-free.
func buildCommentWire(
	c postmodel.Comment,
	viewerID string,
	lookup commentReactionLookup,
	postCtx commentPostContext,
	includePreview bool,
	previewReplies []map[string]any,
	hasMoreReplies bool,
) map[string]any {
	viewerID = strings.TrimSpace(viewerID)
	projected := map[string]any{
		"_id":                   c.ID,
		"postId":                c.PostId,
		"authorId":              c.AuthorId,
		"personaContextVersion": c.PersonaContextVersion,
		"content":               c.Content,
		"ipLocation":            c.IpLocation,
		"replyToCommentId":      c.ReplyToCommentId,
		"replyToUserId":         c.ReplyToUserId,
		"parentCommentId":       c.ParentCommentId,
		"attachmentMediaIds":    anySliceOrEmpty(c.AttachmentMediaIds),
		"attachments":           anySliceOrEmpty(c.Attachments),
		"mentions":              anySliceOrEmpty(c.Mentions),
		"assistantMentioned":    c.AssistantMentioned,
		"replyCount":            c.ReplyCount,
		"likeCount":             c.LikeCount,
		"dislikeCount":          c.DislikeCount,
		"reportCount":           int64(0),
		"recommendedScore":      c.RecommendedScore,
		"status":                c.Status,
		"createdAt":             c.CreatedAt.UTC().Format(time.RFC3339),
		"deletedAt":             commentDeletedAtWire(c),
		"viewerReaction":        lookup.viewerReaction(c.ID),
		"isAuthor":              viewerID != "" && viewerID == strings.TrimSpace(c.AuthorId),
		"canDelete":             viewerID != "" && viewerID == strings.TrimSpace(c.AuthorId),
		"canReply":              strings.TrimSpace(c.Status) != "deleted",
		"canReport":             viewerID != "" && viewerID != strings.TrimSpace(c.AuthorId),
		"authorLiked":           lookup.authorLiked(c.ID),
		"isPinned":              c.IsPinned,
	}
	if !c.PinnedAt.IsZero() {
		projected["pinnedAt"] = c.PinnedAt.UTC().Format(time.RFC3339)
	}
	projected["canPin"] = postCtx.authorID != "" &&
		viewerID == postCtx.authorID &&
		commentTopLevelModel(c) &&
		strings.TrimSpace(c.Status) != "deleted"
	if len(postCtx.summary) > 0 {
		projected["postSummary"] = postCtx.summary
	}
	if !includePreview {
		projected["replyPreview"] = []map[string]any{}
		projected["replyNextCursor"] = ""
		return projected
	}
	if previewReplies == nil {
		previewReplies = []map[string]any{}
	}
	projected["replyPreview"] = previewReplies
	if hasMoreReplies && len(previewReplies) > 0 {
		projected["replyNextCursor"] = asString(previewReplies[len(previewReplies)-1]["_id"])
	} else {
		projected["replyNextCursor"] = ""
	}
	return projected
}

// projectCommentSingle projects one comment, resolving post context, the viewer's
// and author's reactions, and (optionally) the reply preview directly from
// storage. Used by single-mutation paths (add / react / pin).
func (s *PostService) projectCommentSingle(
	ctx context.Context, c postmodel.Comment, viewerID string, includePreview bool,
) map[string]any {
	postCtx := s.resolvePostContext(ctx, c.PostId)
	lookup := s.resolveReactionLookup(ctx, viewerID, postCtx.authorID, []string{c.ID})

	var previewReplies []map[string]any
	hasMore := false
	if includePreview {
		previewReplies, hasMore = s.buildReplyPreview(ctx, c.PostId, c.ID, viewerID, postCtx)
	}
	return buildCommentWire(c, viewerID, lookup, postCtx, includePreview, previewReplies, hasMore)
}

// buildReplyPreview fetches up to commentReplyPreviewCount newest replies for a
// parent and projects them (without nested previews), reporting whether more
// replies exist beyond the preview window.
func (s *PostService) buildReplyPreview(
	ctx context.Context, postID, parentID, viewerID string, postCtx commentPostContext,
) ([]map[string]any, bool) {
	page, err := s.commentStore.ListReplies(ctx, postID, parentID, "", commentReplyPreviewCount+1)
	if err != nil {
		s.logger.Warn("comment_projection: reply preview fetch failed", "error", err.Error())
		return []map[string]any{}, false
	}
	hasMore := len(page.Comments) > commentReplyPreviewCount
	shown := page.Comments
	if len(shown) > commentReplyPreviewCount {
		shown = shown[:commentReplyPreviewCount]
	}
	ids := make([]string, 0, len(shown))
	for _, r := range shown {
		ids = append(ids, r.ID)
	}
	lookup := s.resolveReactionLookup(ctx, viewerID, postCtx.authorID, ids)
	out := make([]map[string]any, 0, len(shown))
	for _, r := range shown {
		out = append(out, buildCommentWire(r, viewerID, lookup, postCtx, false, nil, false))
	}
	return out, hasMore
}

// resolveReactionLookup batch-loads the viewer's and (when distinct) the post
// author's reactions across the supplied comment ids.
func (s *PostService) resolveReactionLookup(
	ctx context.Context, viewerID, postAuthorID string, commentIDs []string,
) commentReactionLookup {
	lookup := commentReactionLookup{
		viewer: map[string]commentdomain.Reaction{},
		author: map[string]commentdomain.Reaction{},
	}
	if len(commentIDs) == 0 {
		return lookup
	}
	viewerID = strings.TrimSpace(viewerID)
	postAuthorID = strings.TrimSpace(postAuthorID)
	if viewerID != "" {
		if m, err := s.commentReactionStore.ReactionsForUser(ctx, viewerID, commentIDs); err == nil {
			lookup.viewer = m
		} else {
			s.logger.Warn("comment_projection: viewer reactions fetch failed", "error", err.Error())
		}
	}
	if postAuthorID != "" {
		if postAuthorID == viewerID {
			lookup.author = lookup.viewer
		} else if m, err := s.commentReactionStore.ReactionsForUser(ctx, postAuthorID, commentIDs); err == nil {
			lookup.author = m
		} else {
			s.logger.Warn("comment_projection: author reactions fetch failed", "error", err.Error())
		}
	}
	return lookup
}

// projectCommentPage projects a page of comments with batched reaction + reply
// preview resolution (no N+1). All comments are assumed to belong to postID.
func (s *PostService) projectCommentPage(
	ctx context.Context, postID string, comments []postmodel.Comment, viewerID string, includePreview bool,
) []map[string]any {
	out := make([]map[string]any, 0, len(comments))
	if len(comments) == 0 {
		return out
	}
	postCtx := s.resolvePostContext(ctx, postID)

	parentIDs := make([]string, 0, len(comments))
	for _, c := range comments {
		parentIDs = append(parentIDs, c.ID)
	}

	// Batch the reply previews for the whole page in one query.
	previewByParent := map[string][]postmodel.Comment{}
	moreByParent := map[string]bool{}
	if includePreview {
		grouped, err := s.commentStore.RepliesForParents(ctx, postID, parentIDs, commentReplyPreviewCount+1)
		if err != nil {
			s.logger.Warn("comment_projection: reply preview batch failed", "error", err.Error())
		} else {
			for parent, replies := range grouped {
				moreByParent[parent] = len(replies) > commentReplyPreviewCount
				if len(replies) > commentReplyPreviewCount {
					replies = replies[:commentReplyPreviewCount]
				}
				previewByParent[parent] = replies
			}
		}
	}

	// Collect every comment id (page + preview replies) for a single reaction load.
	allIDs := make([]string, 0, len(comments))
	allIDs = append(allIDs, parentIDs...)
	for _, replies := range previewByParent {
		for _, r := range replies {
			allIDs = append(allIDs, r.ID)
		}
	}
	lookup := s.resolveReactionLookup(ctx, viewerID, postCtx.authorID, allIDs)

	for _, c := range comments {
		var previewWire []map[string]any
		hasMore := false
		if includePreview {
			replies := previewByParent[c.ID]
			previewWire = make([]map[string]any, 0, len(replies))
			for _, r := range replies {
				previewWire = append(previewWire, buildCommentWire(r, viewerID, lookup, postCtx, false, nil, false))
			}
			hasMore = moreByParent[c.ID]
		}
		out = append(out, buildCommentWire(c, viewerID, lookup, postCtx, includePreview, previewWire, hasMore))
	}
	return out
}

// projectCommentsAcrossPosts projects comments that may span multiple posts (my
// comments / received comments / profile activity). Reply previews are omitted
// (these surfaces render flat rows). Post context is resolved per distinct post.
func (s *PostService) projectCommentsAcrossPosts(
	ctx context.Context, comments []postmodel.Comment, viewerID string,
) []map[string]any {
	out := make([]map[string]any, 0, len(comments))
	if len(comments) == 0 {
		return out
	}
	postCtxByID := map[string]commentPostContext{}
	ids := make([]string, 0, len(comments))
	for _, c := range comments {
		ids = append(ids, c.ID)
		if _, ok := postCtxByID[c.PostId]; !ok {
			postCtxByID[c.PostId] = s.resolvePostContext(ctx, c.PostId)
		}
	}
	// One viewer reaction load across all ids; author-liked is per-post so we
	// resolve it lazily per comment from its post context author.
	viewerLookup := commentReactionLookup{viewer: map[string]commentdomain.Reaction{}}
	if strings.TrimSpace(viewerID) != "" {
		if m, err := s.commentReactionStore.ReactionsForUser(ctx, strings.TrimSpace(viewerID), ids); err == nil {
			viewerLookup.viewer = m
		}
	}
	// Author-liked across posts: gather per post-author reactions in batch.
	authorReactionByID := map[string]commentdomain.Reaction{}
	authorIDToComments := map[string][]string{}
	for _, c := range comments {
		if author := postCtxByID[c.PostId].authorID; author != "" {
			authorIDToComments[author] = append(authorIDToComments[author], c.ID)
		}
	}
	for author, cIDs := range authorIDToComments {
		if m, err := s.commentReactionStore.ReactionsForUser(ctx, author, cIDs); err == nil {
			for id, r := range m {
				authorReactionByID[id] = r
			}
		}
	}
	for _, c := range comments {
		lookup := commentReactionLookup{viewer: viewerLookup.viewer, author: authorReactionByID}
		out = append(out, buildCommentWire(c, viewerID, lookup, postCtxByID[c.PostId], false, nil, false))
	}
	return out
}
