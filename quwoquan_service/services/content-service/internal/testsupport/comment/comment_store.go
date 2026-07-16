package commenttestsupport

import (
	"context"
	"sort"
	"strings"
	"sync"
	"time"

	commentmodel "quwoquan_service/services/content-service/internal/domain/comment/model"
	commentports "quwoquan_service/services/content-service/internal/domain/comment/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

type Store struct {
	mu          sync.RWMutex
	comments    map[string]commentmodel.Snapshot
	receipts    map[string]receipt
	outbox      []commentports.OutboxEvent
	posts       map[string]commentmodel.PostOwnership
	checkpoints map[string]string
}

type receipt struct {
	commandName   string
	commandDigest string
	snapshot      commentmodel.Snapshot
	expiresAt     time.Time
}

func NewStore() *Store {
	return &Store{
		comments:    map[string]commentmodel.Snapshot{},
		receipts:    map[string]receipt{},
		posts:       map[string]commentmodel.PostOwnership{},
		checkpoints: map[string]string{},
	}
}

func (s *Store) SeedPost(postID string, authorID string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	postID = strings.TrimSpace(postID)
	s.posts[postID] = commentmodel.PostOwnership{
		PostID:   postID,
		AuthorID: strings.TrimSpace(authorID),
		Active:   true,
	}
}

func (s *Store) ValidateCommentAttachments(
	_ context.Context,
	_ string,
	mediaIDs []string,
) error {
	for _, mediaID := range mediaIDs {
		if strings.TrimSpace(mediaID) == "" {
			return contentgenerated.AppErrorFromInvalidArgument("empty Comment attachment id")
		}
	}
	return nil
}

func (s *Store) ReadCommentAttachments(
	_ context.Context,
	mediaIDs []string,
) (map[string]commentmodel.AttachmentProjection, error) {
	projections := make(map[string]commentmodel.AttachmentProjection, len(mediaIDs))
	for _, mediaID := range mediaIDs {
		mediaID = strings.TrimSpace(mediaID)
		if mediaID == "" {
			continue
		}
		projections[mediaID] = commentmodel.AttachmentProjection{
			MediaID:   mediaID,
			MediaType: "image",
			URL:       "https://comment-fixture.invalid/" + mediaID,
			Available: true,
		}
	}
	return projections, nil
}

func (s *Store) Load(
	_ context.Context,
	commentID string,
) (*commentmodel.Comment, bool, error) {
	s.mu.RLock()
	snapshot, found := s.comments[strings.TrimSpace(commentID)]
	s.mu.RUnlock()
	if !found {
		return nil, false, nil
	}
	aggregate, err := commentmodel.Restore(snapshot)
	if err != nil {
		return nil, false, err
	}
	return aggregate, true, nil
}

func (s *Store) FindReceipt(
	_ context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (commentports.CommitResult, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, found := s.receipts[strings.TrimSpace(idempotencyKey)]
	if !found {
		return commentports.CommitResult{}, false, nil
	}
	if !receipt.expiresAt.After(time.Now().UTC()) {
		delete(s.receipts, strings.TrimSpace(idempotencyKey))
		return commentports.CommitResult{}, false, nil
	}
	if receipt.commandName != commandName || receipt.commandDigest != commandDigest {
		return commentports.CommitResult{}, false,
			contentgenerated.AppErrorFromIdempotencyConflict(
				"test comment receipt digest mismatch",
			)
	}
	aggregate, err := commentmodel.Restore(receipt.snapshot)
	if err != nil {
		return commentports.CommitResult{}, false, err
	}
	return commentports.CommitResult{Aggregate: aggregate, Replayed: true}, true, nil
}

func (s *Store) Commit(
	_ context.Context,
	commit commentports.Commit,
) (commentports.CommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if receipt, found := s.receipts[commit.IdempotencyKey]; found {
		if !receipt.expiresAt.After(time.Now().UTC()) {
			delete(s.receipts, commit.IdempotencyKey)
		} else {
			if receipt.commandName != commit.CommandName ||
				receipt.commandDigest != commit.CommandDigest {
				return commentports.CommitResult{},
					contentgenerated.AppErrorFromIdempotencyConflict(
						"test comment receipt digest mismatch",
					)
			}
			replayed, err := commentmodel.Restore(receipt.snapshot)
			if err != nil {
				return commentports.CommitResult{}, err
			}
			return commentports.CommitResult{Aggregate: replayed, Replayed: true}, nil
		}
	}
	if err := validateCommit(commit); err != nil {
		return commentports.CommitResult{}, err
	}
	snapshot := commit.Aggregate.Snapshot()
	current, exists := s.comments[snapshot.ID]
	if commit.ExpectedVersion == 0 {
		if exists {
			return commentports.CommitResult{},
				contentgenerated.AppErrorFromVersionConflict("comment already exists")
		}
	} else if !exists || current.Version != commit.ExpectedVersion {
		return commentports.CommitResult{},
			contentgenerated.AppErrorFromVersionConflict("comment version changed")
	}
	s.comments[snapshot.ID] = cloneSnapshot(snapshot)
	expiresAt := commit.ReceiptExpiresAt.UTC()
	if expiresAt.IsZero() {
		expiresAt = time.Now().UTC().Add(24 * time.Hour)
	}
	s.receipts[commit.IdempotencyKey] = receipt{
		commandName:   commit.CommandName,
		commandDigest: commit.CommandDigest,
		snapshot:      cloneSnapshot(snapshot),
		expiresAt:     expiresAt,
	}
	events := cloneOutboxEvents(commit.Events)
	for index := range events {
		events[index].Checkpoint = events[index].EventID
	}
	s.outbox = append(s.outbox, events...)
	aggregate, err := commentmodel.Restore(snapshot)
	if err != nil {
		return commentports.CommitResult{}, err
	}
	return commentports.CommitResult{Aggregate: aggregate}, nil
}

func (s *Store) ListByPost(
	_ context.Context,
	postID string,
	request commentports.PageRequest,
) (commentmodel.Page, error) {
	s.mu.RLock()
	items := make([]commentmodel.ReadModel, 0)
	for _, snapshot := range s.comments {
		if snapshot.PostID == strings.TrimSpace(postID) &&
			snapshot.ParentCommentID == "" &&
			snapshot.Status == commentmodel.StatusActive {
			items = append(items, readModel(snapshot))
		}
	}
	s.mu.RUnlock()
	sort.Slice(items, func(i, j int) bool { return topLevelBefore(items[i], items[j]) })
	return pageFrom(items, request, topLevelAfter), nil
}

func (s *Store) ListReplies(
	_ context.Context,
	postID string,
	parentCommentID string,
	request commentports.PageRequest,
) (commentmodel.Page, error) {
	s.mu.RLock()
	items := make([]commentmodel.ReadModel, 0)
	for _, snapshot := range s.comments {
		if snapshot.PostID == strings.TrimSpace(postID) &&
			snapshot.ParentCommentID == strings.TrimSpace(parentCommentID) &&
			snapshot.Status == commentmodel.StatusActive {
			items = append(items, readModel(snapshot))
		}
	}
	s.mu.RUnlock()
	sort.Slice(items, func(i, j int) bool { return flatBefore(items[i], items[j]) })
	return pageFrom(items, request, flatAfter), nil
}

func (s *Store) ReadReplySummaries(
	_ context.Context,
	parentCommentIDs []string,
	previewLimit int,
) (map[string]commentmodel.ReplySummary, error) {
	parentSet := map[string]struct{}{}
	for _, parentCommentID := range parentCommentIDs {
		if parentCommentID = strings.TrimSpace(parentCommentID); parentCommentID != "" {
			parentSet[parentCommentID] = struct{}{}
		}
	}
	grouped := make(map[string][]commentmodel.ReadModel, len(parentSet))
	s.mu.RLock()
	for _, snapshot := range s.comments {
		if _, found := parentSet[snapshot.ParentCommentID]; !found || snapshot.Status != commentmodel.StatusActive {
			continue
		}
		grouped[snapshot.ParentCommentID] = append(grouped[snapshot.ParentCommentID], readModel(snapshot))
	}
	s.mu.RUnlock()
	if previewLimit <= 0 {
		previewLimit = 1
	}
	summaries := make(map[string]commentmodel.ReplySummary, len(grouped))
	for parentCommentID, items := range grouped {
		sort.Slice(items, func(i, j int) bool { return flatBefore(items[i], items[j]) })
		count := int64(len(items))
		nextCursor := ""
		if len(items) > previewLimit {
			items = items[:previewLimit]
			nextCursor = commentmodel.EncodeCursor(commentmodel.CursorFor(items[len(items)-1]))
		}
		summaries[parentCommentID] = commentmodel.ReplySummary{
			Count:      count,
			Preview:    items,
			NextCursor: nextCursor,
		}
	}
	return summaries, nil
}

func (s *Store) ListByAuthor(
	_ context.Context,
	authorID string,
	request commentports.PageRequest,
) (commentmodel.Page, error) {
	s.mu.RLock()
	items := make([]commentmodel.ReadModel, 0)
	for _, snapshot := range s.comments {
		if snapshot.AuthorID == strings.TrimSpace(authorID) &&
			snapshot.Status == commentmodel.StatusActive {
			items = append(items, readModel(snapshot))
		}
	}
	s.mu.RUnlock()
	sort.Slice(items, func(i, j int) bool { return flatBefore(items[i], items[j]) })
	return pageFrom(items, request, flatAfter), nil
}

func (s *Store) ListReceivedByPostAuthor(
	_ context.Context,
	postAuthorID string,
	postIDs []string,
	request commentports.PageRequest,
) (commentmodel.Page, error) {
	postSet := map[string]struct{}{}
	for _, postID := range postIDs {
		if postID = strings.TrimSpace(postID); postID != "" {
			postSet[postID] = struct{}{}
		}
	}
	s.mu.RLock()
	items := make([]commentmodel.ReadModel, 0)
	for _, snapshot := range s.comments {
		if _, found := postSet[snapshot.PostID]; found &&
			snapshot.AuthorID != strings.TrimSpace(postAuthorID) &&
			snapshot.Status == commentmodel.StatusActive {
			items = append(items, readModel(snapshot))
		}
	}
	s.mu.RUnlock()
	sort.Slice(items, func(i, j int) bool { return flatBefore(items[i], items[j]) })
	return pageFrom(items, request, flatAfter), nil
}

func (s *Store) CountByPost(_ context.Context, postID string) (int64, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var count int64
	for _, snapshot := range s.comments {
		if snapshot.PostID == strings.TrimSpace(postID) && snapshot.Status == commentmodel.StatusActive {
			count++
		}
	}
	return count, nil
}

func (s *Store) FindReplyTarget(
	_ context.Context,
	commentID string,
) (commentmodel.ReplyTarget, bool, error) {
	s.mu.RLock()
	snapshot, found := s.comments[strings.TrimSpace(commentID)]
	s.mu.RUnlock()
	if !found {
		return commentmodel.ReplyTarget{}, false, nil
	}
	return commentmodel.ReplyTarget{
		ID:              snapshot.ID,
		PostID:          snapshot.PostID,
		AuthorID:        snapshot.AuthorID,
		ParentCommentID: snapshot.ParentCommentID,
		Status:          snapshot.Status,
	}, true, nil
}

func (s *Store) FindPostOwnership(
	_ context.Context,
	postID string,
) (commentmodel.PostOwnership, bool, error) {
	s.mu.RLock()
	post, found := s.posts[strings.TrimSpace(postID)]
	s.mu.RUnlock()
	return post, found, nil
}

func (s *Store) ListOwnedPostIDs(
	_ context.Context,
	postAuthorID string,
) ([]string, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	postIDs := []string{}
	for postID, post := range s.posts {
		if post.Active && post.AuthorID == strings.TrimSpace(postAuthorID) {
			postIDs = append(postIDs, postID)
		}
	}
	sort.Strings(postIDs)
	return postIDs, nil
}

func (s *Store) FindPostOwnerships(
	_ context.Context,
	postIDs []string,
) (map[string]commentmodel.PostOwnership, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	ownerships := make(map[string]commentmodel.PostOwnership, len(postIDs))
	for _, postID := range postIDs {
		postID = strings.TrimSpace(postID)
		if post, found := s.posts[postID]; found {
			ownerships[postID] = post
		}
	}
	return ownerships, nil
}

func (s *Store) ReadAfter(
	_ context.Context,
	checkpoint string,
	limit int,
) ([]commentports.OutboxEvent, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if limit <= 0 {
		limit = 100
	}
	events := cloneOutboxEvents(s.outbox)
	if strings.TrimSpace(checkpoint) == "" {
		if len(events) > limit {
			events = events[:limit]
		}
		return events, nil
	}
	start := len(events)
	for index, event := range events {
		if event.Checkpoint == checkpoint {
			start = index + 1
			break
		}
	}
	if start == len(events) {
		return []commentports.OutboxEvent{}, nil
	}
	events = events[start:]
	if len(events) > limit {
		events = events[:limit]
	}
	return events, nil
}

func (s *Store) OutboxEvents() []commentports.OutboxEvent {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return cloneOutboxEvents(s.outbox)
}

func (s *Store) LoadCheckpoint(_ context.Context, consumer string) (string, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.checkpoints[strings.TrimSpace(consumer)], nil
}

func (s *Store) SaveCheckpoint(_ context.Context, consumer, checkpoint string) error {
	consumer = strings.TrimSpace(consumer)
	checkpoint = strings.TrimSpace(checkpoint)
	if consumer == "" || checkpoint == "" {
		return contentgenerated.AppErrorFromInvalidArgument("comment checkpoint is incomplete")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.checkpoints[consumer] = checkpoint
	return nil
}

func validateCommit(commit commentports.Commit) error {
	if commit.Aggregate == nil || strings.TrimSpace(commit.Aggregate.ID()) == "" {
		return contentgenerated.AppErrorFromVersionConflict("test comment aggregate is required")
	}
	if strings.TrimSpace(commit.IdempotencyKey) == "" ||
		strings.TrimSpace(commit.CommandName) == "" ||
		strings.TrimSpace(commit.CommandDigest) == "" {
		return contentgenerated.AppErrorFromIdempotencyConflict("test comment command receipt is incomplete")
	}
	if commit.Aggregate.Version() != commit.ExpectedVersion+1 {
		return contentgenerated.AppErrorFromVersionConflict("test comment version is not monotonic")
	}
	if len(commit.Events) == 0 {
		return contentgenerated.AppErrorFromVersionConflict("test comment commit requires an outbox fact")
	}
	eventIDs := make(map[string]struct{}, len(commit.Events))
	for _, event := range commit.Events {
		if strings.TrimSpace(event.EventID) == "" ||
			strings.TrimSpace(event.EventType) == "" ||
			event.AggregateID != commit.Aggregate.ID() ||
			event.AggregateVersion != commit.Aggregate.Version() ||
			event.OccurredAt.IsZero() {
			return contentgenerated.AppErrorFromVersionConflict("test comment outbox fact does not match aggregate")
		}
		if _, found := eventIDs[event.EventID]; found {
			return contentgenerated.AppErrorFromVersionConflict("test comment outbox fact id is duplicated")
		}
		eventIDs[event.EventID] = struct{}{}
	}
	return nil
}

func readModel(snapshot commentmodel.Snapshot) commentmodel.ReadModel {
	return commentmodel.ReadModel{
		ID:                        snapshot.ID,
		Version:                   snapshot.Version,
		PostID:                    snapshot.PostID,
		AuthorID:                  snapshot.AuthorID,
		AuthorDisplayNameSnapshot: snapshot.AuthorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot:   snapshot.AuthorAvatarURLSnapshot,
		PersonaContextVersion:     snapshot.PersonaContextVersion,
		Content:                   snapshot.Content,
		ReplyToCommentID:          snapshot.ReplyToCommentID,
		ReplyToUserID:             snapshot.ReplyToUserID,
		ParentCommentID:           snapshot.ParentCommentID,
		AttachmentMediaIDs:        cloneStrings(snapshot.AttachmentMediaIDs),
		Mentions:                  append([]commentmodel.Mention(nil), snapshot.Mentions...),
		AssistantMentioned:        snapshot.AssistantMentioned,
		AssistantReplySource:      snapshot.AssistantReplySource,
		AssistantCorrectionStatus: snapshot.AssistantCorrectionStatus,
		Status:                    snapshot.Status,
		IsPinned:                  snapshot.IsPinned,
		PinnedAt:                  cloneTime(snapshot.PinnedAt),
		CreatedAt:                 snapshot.CreatedAt.UTC(),
		UpdatedAt:                 snapshot.UpdatedAt.UTC(),
		DeletedAt:                 cloneTime(snapshot.DeletedAt),
	}
}

func pageFrom(
	items []commentmodel.ReadModel,
	request commentports.PageRequest,
	after func(commentmodel.ReadModel, commentmodel.Cursor) bool,
) commentmodel.Page {
	total := int64(len(items))
	if cursor, found := commentmodel.DecodeCursor(request.Cursor); found {
		filtered := make([]commentmodel.ReadModel, 0, len(items))
		for _, item := range items {
			if after(item, cursor) {
				filtered = append(filtered, item)
			}
		}
		items = filtered
	}
	limit := request.Limit
	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	nextCursor := ""
	if len(items) > limit {
		items = items[:limit]
		nextCursor = commentmodel.EncodeCursor(commentmodel.CursorFor(items[len(items)-1]))
	}
	cloned := make([]commentmodel.ReadModel, len(items))
	for index, item := range items {
		cloned[index] = item.Clone()
	}
	return commentmodel.Page{Items: cloned, NextCursor: nextCursor, Total: total}
}

func topLevelBefore(left, right commentmodel.ReadModel) bool {
	if left.IsPinned != right.IsPinned {
		return left.IsPinned
	}
	leftPinnedAt := time.Time{}
	if left.PinnedAt != nil {
		leftPinnedAt = left.PinnedAt.UTC()
	}
	rightPinnedAt := time.Time{}
	if right.PinnedAt != nil {
		rightPinnedAt = right.PinnedAt.UTC()
	}
	if !leftPinnedAt.Equal(rightPinnedAt) {
		return leftPinnedAt.After(rightPinnedAt)
	}
	return flatBefore(left, right)
}

func flatBefore(left, right commentmodel.ReadModel) bool {
	if !left.CreatedAt.Equal(right.CreatedAt) {
		return left.CreatedAt.After(right.CreatedAt)
	}
	return left.ID > right.ID
}

func topLevelAfter(item commentmodel.ReadModel, cursor commentmodel.Cursor) bool {
	if item.IsPinned != cursor.Pinned {
		return !item.IsPinned && cursor.Pinned
	}
	if item.IsPinned {
		pinnedAt := int64(0)
		if item.PinnedAt != nil {
			pinnedAt = item.PinnedAt.UTC().UnixNano()
		}
		if pinnedAt != cursor.PinnedAtNano {
			return pinnedAt < cursor.PinnedAtNano
		}
	}
	return flatAfter(item, cursor)
}

func flatAfter(item commentmodel.ReadModel, cursor commentmodel.Cursor) bool {
	createdAt := item.CreatedAt.UTC().UnixNano()
	if createdAt != cursor.CreatedAtNano {
		return createdAt < cursor.CreatedAtNano
	}
	return item.ID < cursor.ID
}

func cloneSnapshot(snapshot commentmodel.Snapshot) commentmodel.Snapshot {
	snapshot.AttachmentMediaIDs = cloneStrings(snapshot.AttachmentMediaIDs)
	snapshot.Mentions = append([]commentmodel.Mention(nil), snapshot.Mentions...)
	snapshot.PinnedAt = cloneTime(snapshot.PinnedAt)
	snapshot.DeletedAt = cloneTime(snapshot.DeletedAt)
	return snapshot
}

func cloneOutboxEvents(events []commentports.OutboxEvent) []commentports.OutboxEvent {
	cloned := make([]commentports.OutboxEvent, len(events))
	for index, event := range events {
		cloned[index] = event
		cloned[index].Payload = append([]byte(nil), event.Payload...)
	}
	return cloned
}

func cloneStrings(values []string) []string {
	if len(values) == 0 {
		return []string{}
	}
	cloned := make([]string, 0, len(values))
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			cloned = append(cloned, value)
		}
	}
	return cloned
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}

var (
	_ commentports.AggregateStore            = (*Store)(nil)
	_ commentports.OutboxReader              = (*Store)(nil)
	_ commentports.ProjectionCheckpointStore = (*Store)(nil)
	_ commentports.CommentPageReader         = (*Store)(nil)
	_ commentports.ReplyPageReader           = (*Store)(nil)
	_ commentports.ReplySummaryReader        = (*Store)(nil)
	_ commentports.AuthorCommentPageReader   = (*Store)(nil)
	_ commentports.ReceivedCommentPageReader = (*Store)(nil)
	_ commentports.CountReader               = (*Store)(nil)
	_ commentports.CommentRelationReader     = (*Store)(nil)
	_ commentports.PostOwnershipReader       = (*Store)(nil)
	_ commentports.AttachmentReader          = (*Store)(nil)
)
