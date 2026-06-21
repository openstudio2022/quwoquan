package persistence

import (
	"context"
	"sort"
	"strings"
	"sync"
	"time"

	commentdomain "quwoquan_service/services/content-service/internal/domain/comment"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

// MemoryCommentStore is the in-memory implementation of commentdomain.Store used
// by alpha/dev and unit tests. Ordering, cursor and count semantics mirror
// MongoCommentStore exactly so the two are behaviourally interchangeable. It is
// safe for concurrent use (mirrors the previous PostService comment locking).
type MemoryCommentStore struct {
	mu       sync.RWMutex
	comments map[string]postmodel.Comment
}

// NewMemoryCommentStore returns an empty in-memory comment store, optionally
// pre-seeded with read-only fixture comments (alpha degrade path).
func NewMemoryCommentStore(seed ...postmodel.Comment) *MemoryCommentStore {
	s := &MemoryCommentStore{comments: make(map[string]postmodel.Comment, len(seed))}
	for _, c := range seed {
		s.comments[c.ID] = c
	}
	return s
}

var _ commentdomain.Store = (*MemoryCommentStore)(nil)

func commentParentOf(c postmodel.Comment) string {
	if parent := strings.TrimSpace(c.ParentCommentId); parent != "" {
		return parent
	}
	return strings.TrimSpace(c.ReplyToCommentId)
}

func commentIsDeleted(c postmodel.Comment) bool {
	return strings.TrimSpace(c.Status) == "deleted"
}

// mainScoreOf returns the mode score key used by the non-pinned ranked segment.
func mainScoreOf(c postmodel.Comment, mode commentdomain.SortMode) float64 {
	switch mode {
	case commentdomain.SortMostLiked:
		return float64(c.LikeCount)
	case commentdomain.SortRecommended:
		return c.RecommendedScore
	default:
		return 0
	}
}

// lessMain mirrors MongoCommentStore.mainSortSpec: score desc (mode), createdAt
// desc, _id desc.
func lessMain(a, b postmodel.Comment, mode commentdomain.SortMode) bool {
	if mode != commentdomain.SortLatest {
		sa, sb := mainScoreOf(a, mode), mainScoreOf(b, mode)
		if sa != sb {
			return sa > sb
		}
	}
	if !a.CreatedAt.Equal(b.CreatedAt) {
		return a.CreatedAt.After(b.CreatedAt)
	}
	return a.ID > b.ID
}

// lessPinned mirrors MongoCommentStore.pinnedSortSpec: pinnedAt desc, _id desc.
func lessPinned(a, b postmodel.Comment) bool {
	if !a.PinnedAt.Equal(b.PinnedAt) {
		return a.PinnedAt.After(b.PinnedAt)
	}
	return a.ID > b.ID
}

// lessFlat mirrors MongoCommentStore.flatSortSpec: createdAt desc, _id desc.
func lessFlat(a, b postmodel.Comment) bool {
	if !a.CreatedAt.Equal(b.CreatedAt) {
		return a.CreatedAt.After(b.CreatedAt)
	}
	return a.ID > b.ID
}

// afterMainCursor reports whether c falls strictly after cur in the main DESC
// keyset order (mirrors MongoCommentStore.keysetAfter for score modes).
func afterMainCursor(c postmodel.Comment, cur commentdomain.Cursor, mode commentdomain.SortMode) bool {
	if cur.HasScore {
		cs := mainScoreOf(c, mode)
		if cs != cur.Score {
			return cs < cur.Score
		}
	}
	if cn := c.CreatedAt.UnixNano(); cn != cur.TimeUnixNano {
		return cn < cur.TimeUnixNano
	}
	return c.ID < cur.ID
}

func afterPinnedCursor(c postmodel.Comment, cur commentdomain.Cursor) bool {
	if pn := c.PinnedAt.UnixNano(); pn != cur.TimeUnixNano {
		return pn < cur.TimeUnixNano
	}
	return c.ID < cur.ID
}

func afterFlatCursor(c postmodel.Comment, cur commentdomain.Cursor) bool {
	if cn := c.CreatedAt.UnixNano(); cn != cur.TimeUnixNano {
		return cn < cur.TimeUnixNano
	}
	return c.ID < cur.ID
}

func commentIsPinned(c postmodel.Comment) bool { return c.IsPinned }

func (s *MemoryCommentStore) Create(_ context.Context, c *postmodel.Comment) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.comments[c.ID] = *c
	return nil
}

func (s *MemoryCommentStore) FindByID(_ context.Context, id string) (*postmodel.Comment, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	c, ok := s.comments[strings.TrimSpace(id)]
	if !ok {
		return nil, false
	}
	cp := c
	return &cp, true
}

// ListTopLevel mirrors MongoCommentStore.ListTopLevel: pinned segment first
// (pinnedAt desc keyset), then the non-pinned ranked segment (mode key keyset),
// with explicit phase transition so a page boundary never re-scans or drops rows.
func (s *MemoryCommentStore) ListTopLevel(
	_ context.Context, postID string, mode commentdomain.SortMode, cursor string, limit int,
) (commentdomain.Page, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	postID = strings.TrimSpace(postID)
	if limit <= 0 {
		limit = 20
	}
	cur, hasCursor := commentdomain.DecodeCursor(cursor)

	var pinned, main []postmodel.Comment
	for _, c := range s.comments {
		if c.PostId != postID || commentIsDeleted(c) || commentParentOf(c) != "" {
			continue
		}
		if commentIsPinned(c) {
			pinned = append(pinned, c)
		} else {
			main = append(main, c)
		}
	}
	sort.SliceStable(pinned, func(i, j int) bool { return lessPinned(pinned[i], pinned[j]) })
	sort.SliceStable(main, func(i, j int) bool { return lessMain(main[i], main[j], mode) })

	result := make([]postmodel.Comment, 0, limit)

	// Phase 1: pinned segment.
	if !hasCursor || cur.Phase == commentdomain.PhasePinned {
		seg := pinned
		if hasCursor && cur.Phase == commentdomain.PhasePinned {
			seg = filterComments(pinned, func(c postmodel.Comment) bool { return afterPinnedCursor(c, cur) })
		}
		if len(seg) > limit {
			page := append([]postmodel.Comment{}, seg[:limit]...)
			return commentdomain.Page{Comments: page, NextCursor: commentdomain.EncodeCursor(pinnedCursorFor(page[len(page)-1]))}, nil
		}
		result = append(result, seg...)
		cur = commentdomain.Cursor{Phase: commentdomain.PhaseMain}
	}

	// Phase 2: non-pinned ranked segment.
	seg := main
	if cur.Phase == commentdomain.PhaseMain && cur.ID != "" {
		seg = filterComments(main, func(c postmodel.Comment) bool { return afterMainCursor(c, cur, mode) })
	}
	need := limit - len(result)
	if need <= 0 {
		next := ""
		if len(seg) > 0 {
			next = commentdomain.EncodeCursor(commentdomain.Cursor{Phase: commentdomain.PhaseMain})
		}
		return commentdomain.Page{Comments: result, NextCursor: next}, nil
	}
	if len(seg) > need {
		result = append(result, seg[:need]...)
		return commentdomain.Page{Comments: result, NextCursor: commentdomain.EncodeCursor(mainCursorFor(result[len(result)-1], mode))}, nil
	}
	result = append(result, seg...)
	return commentdomain.Page{Comments: result, NextCursor: ""}, nil
}

// listFlat is the shared (createdAt desc, _id desc) keyset page used by replies,
// author and received feeds, mirroring MongoCommentStore.listFlat.
func listFlatMemory(candidates []postmodel.Comment, cursor string, limit int) commentdomain.Page {
	if limit <= 0 {
		limit = 20
	}
	sort.SliceStable(candidates, func(i, j int) bool { return lessFlat(candidates[i], candidates[j]) })
	if cur, ok := commentdomain.DecodeCursor(cursor); ok && cur.ID != "" {
		candidates = filterComments(candidates, func(c postmodel.Comment) bool { return afterFlatCursor(c, cur) })
	}
	next := ""
	if len(candidates) > limit {
		candidates = candidates[:limit]
		next = commentdomain.EncodeCursor(flatCursorFor(candidates[len(candidates)-1]))
	}
	page := append([]postmodel.Comment{}, candidates...)
	return commentdomain.Page{Comments: page, NextCursor: next}
}

func filterComments(in []postmodel.Comment, keep func(postmodel.Comment) bool) []postmodel.Comment {
	out := make([]postmodel.Comment, 0, len(in))
	for _, c := range in {
		if keep(c) {
			out = append(out, c)
		}
	}
	return out
}

func (s *MemoryCommentStore) ListReplies(
	_ context.Context, postID, parentID, cursor string, limit int,
) (commentdomain.Page, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	postID = strings.TrimSpace(postID)
	parentID = strings.TrimSpace(parentID)
	if limit <= 0 {
		limit = 10
	}
	candidates := make([]postmodel.Comment, 0)
	for _, c := range s.comments {
		if c.PostId != postID || commentIsDeleted(c) || commentParentOf(c) != parentID {
			continue
		}
		candidates = append(candidates, c)
	}
	return listFlatMemory(candidates, cursor, limit), nil
}

func (s *MemoryCommentStore) RepliesForParents(
	_ context.Context, postID string, parentIDs []string, perParent int,
) (map[string][]postmodel.Comment, error) {
	if perParent <= 0 {
		perParent = 1
	}
	want := map[string]bool{}
	for _, id := range parentIDs {
		if id = strings.TrimSpace(id); id != "" {
			want[id] = true
		}
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	postID = strings.TrimSpace(postID)
	grouped := map[string][]postmodel.Comment{}
	for _, c := range s.comments {
		if c.PostId != postID || commentIsDeleted(c) {
			continue
		}
		parent := commentParentOf(c)
		if !want[parent] {
			continue
		}
		grouped[parent] = append(grouped[parent], c)
	}
	for parent, list := range grouped {
		sort.SliceStable(list, func(i, j int) bool {
			return lessFlat(list[i], list[j])
		})
		if len(list) > perParent {
			list = list[:perParent]
		}
		grouped[parent] = list
	}
	return grouped, nil
}

func (s *MemoryCommentStore) ListByAuthor(
	_ context.Context, authorID, cursor string, limit int,
) (commentdomain.Page, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	authorID = strings.TrimSpace(authorID)
	candidates := make([]postmodel.Comment, 0)
	for _, c := range s.comments {
		if c.AuthorId != authorID || commentIsDeleted(c) {
			continue
		}
		candidates = append(candidates, c)
	}
	return listFlatMemory(candidates, cursor, limit), nil
}

func (s *MemoryCommentStore) ListReceivedByPostAuthor(
	_ context.Context, postAuthorID string, postIDs []string, cursor string, limit int,
) (commentdomain.Page, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	postAuthorID = strings.TrimSpace(postAuthorID)
	postSet := map[string]bool{}
	for _, id := range postIDs {
		if id = strings.TrimSpace(id); id != "" {
			postSet[id] = true
		}
	}
	candidates := make([]postmodel.Comment, 0)
	for _, c := range s.comments {
		if !postSet[c.PostId] || commentIsDeleted(c) || c.AuthorId == postAuthorID {
			continue
		}
		candidates = append(candidates, c)
	}
	return listFlatMemory(candidates, cursor, limit), nil
}

func (s *MemoryCommentStore) ListByPostForActivity(_ context.Context, postID string) ([]postmodel.Comment, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	postID = strings.TrimSpace(postID)
	out := make([]postmodel.Comment, 0)
	for _, c := range s.comments {
		if c.PostId != postID || commentIsDeleted(c) {
			continue
		}
		out = append(out, c)
	}
	return out, nil
}

// SoftDelete marks the comment deleted and records deletedAt, mirroring
// MongoCommentStore. An already-deleted comment is treated as not found so the
// delete is idempotent (no double counter decrement).
func (s *MemoryCommentStore) SoftDelete(
	_ context.Context, id string, deletedAt time.Time,
) (*postmodel.Comment, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	id = strings.TrimSpace(id)
	c, ok := s.comments[id]
	if !ok || commentIsDeleted(c) {
		return nil, false, nil
	}
	if deletedAt.IsZero() {
		deletedAt = time.Now().UTC()
	}
	snapshot := c
	c.Status = "deleted"
	c.DeletedAt = deletedAt.UTC()
	s.comments[id] = c
	return &snapshot, true, nil
}

func (s *MemoryCommentStore) SetPinned(
	_ context.Context, id string, pinned bool, pinnedAt time.Time,
) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	id = strings.TrimSpace(id)
	c, ok := s.comments[id]
	if !ok {
		return false, nil
	}
	c.IsPinned = pinned
	if pinned {
		c.PinnedAt = pinnedAt
	} else {
		c.PinnedAt = time.Time{}
	}
	s.comments[id] = c
	return true, nil
}

func (s *MemoryCommentStore) AdjustReplyCount(
	_ context.Context, id string, delta int64, recommendedScore float64,
) (*postmodel.Comment, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	id = strings.TrimSpace(id)
	c, ok := s.comments[id]
	if !ok {
		return nil, false, nil
	}
	c.ReplyCount += delta
	if c.ReplyCount < 0 {
		c.ReplyCount = 0
	}
	c.RecommendedScore = recommendedScore
	s.comments[id] = c
	cp := c
	return &cp, true, nil
}

func (s *MemoryCommentStore) SetReactionState(
	_ context.Context, id string, likeCount, dislikeCount int64, recommendedScore float64,
) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	id = strings.TrimSpace(id)
	c, ok := s.comments[id]
	if !ok {
		return false, nil
	}
	c.LikeCount = likeCount
	c.DislikeCount = dislikeCount
	c.RecommendedScore = recommendedScore
	s.comments[id] = c
	return true, nil
}

func (s *MemoryCommentStore) SetAttachments(
	_ context.Context, id string, attachmentIDs []string, attachments []map[string]any,
) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	id = strings.TrimSpace(id)
	c, ok := s.comments[id]
	if !ok {
		return false, nil
	}
	c.AttachmentMediaIds = attachmentIDs
	c.Attachments = attachments
	s.comments[id] = c
	return true, nil
}

func (s *MemoryCommentStore) CountByPost(_ context.Context, postID string) (int64, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	postID = strings.TrimSpace(postID)
	var n int64
	for _, c := range s.comments {
		if c.PostId == postID && !commentIsDeleted(c) {
			n++
		}
	}
	return n, nil
}

func (s *MemoryCommentStore) CountReplies(_ context.Context, postID, parentID string) (int64, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	postID = strings.TrimSpace(postID)
	parentID = strings.TrimSpace(parentID)
	var n int64
	for _, c := range s.comments {
		if c.PostId == postID && !commentIsDeleted(c) && commentParentOf(c) == parentID {
			n++
		}
	}
	return n, nil
}

func inWindow(t, since, until time.Time) bool {
	if t.IsZero() || t.After(until) {
		return false
	}
	if !since.IsZero() && !t.After(since) {
		return false
	}
	return true
}

func (s *MemoryCommentStore) CountCreatedBetween(_ context.Context, postID string, since, until time.Time) (int64, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	postID = strings.TrimSpace(postID)
	var n int64
	for _, c := range s.comments {
		if c.PostId == postID && inWindow(c.CreatedAt, since, until) {
			n++
		}
	}
	return n, nil
}

func (s *MemoryCommentStore) CountDeletedBetween(_ context.Context, postID string, since, until time.Time) (int64, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	postID = strings.TrimSpace(postID)
	var n int64
	for _, c := range s.comments {
		if c.PostId == postID && commentIsDeleted(c) && inWindow(c.DeletedAt, since, until) {
			n++
		}
	}
	return n, nil
}

// MemoryCommentReactionStore is the in-memory implementation of
// commentdomain.ReactionStore. Membership is authoritative; counts are derived.
type MemoryCommentReactionStore struct {
	mu        sync.RWMutex
	reactions map[string]map[string]commentdomain.Reaction // commentID -> userID -> reaction
}

func NewMemoryCommentReactionStore() *MemoryCommentReactionStore {
	return &MemoryCommentReactionStore{reactions: map[string]map[string]commentdomain.Reaction{}}
}

var _ commentdomain.ReactionStore = (*MemoryCommentReactionStore)(nil)

func (s *MemoryCommentReactionStore) Set(_ context.Context, commentID, userID string, reaction commentdomain.Reaction) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	commentID = strings.TrimSpace(commentID)
	userID = strings.TrimSpace(userID)
	byUser := s.reactions[commentID]
	if byUser == nil {
		byUser = map[string]commentdomain.Reaction{}
		s.reactions[commentID] = byUser
	}
	if reaction == commentdomain.ReactionNone {
		delete(byUser, userID)
		return nil
	}
	byUser[userID] = reaction
	return nil
}

func (s *MemoryCommentReactionStore) Get(_ context.Context, commentID, userID string) (commentdomain.Reaction, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if byUser := s.reactions[strings.TrimSpace(commentID)]; byUser != nil {
		if r, ok := byUser[strings.TrimSpace(userID)]; ok {
			return r, nil
		}
	}
	return commentdomain.ReactionNone, nil
}

func (s *MemoryCommentReactionStore) Counts(_ context.Context, commentID string) (int64, int64, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var like, dislike int64
	for _, r := range s.reactions[strings.TrimSpace(commentID)] {
		switch r {
		case commentdomain.ReactionLike:
			like++
		case commentdomain.ReactionDislike:
			dislike++
		}
	}
	return like, dislike, nil
}

func (s *MemoryCommentReactionStore) ReactionsForUser(
	_ context.Context, userID string, commentIDs []string,
) (map[string]commentdomain.Reaction, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	userID = strings.TrimSpace(userID)
	out := make(map[string]commentdomain.Reaction, len(commentIDs))
	for _, id := range commentIDs {
		id = strings.TrimSpace(id)
		if byUser := s.reactions[id]; byUser != nil {
			if r, ok := byUser[userID]; ok {
				out[id] = r
			}
		}
	}
	return out, nil
}

func (s *MemoryCommentReactionStore) PurgeComment(_ context.Context, commentID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.reactions, strings.TrimSpace(commentID))
	return nil
}
