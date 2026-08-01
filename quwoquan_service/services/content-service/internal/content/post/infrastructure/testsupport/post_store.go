package testsupport

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type postReceipt struct {
	commandName   string
	commandDigest string
	post          postmodel.Post
	expiresAt     time.Time
}

// PostStore 仅供 local_contract 使用；生产装配不得依赖 testsupport。
type PostStore struct {
	mu          sync.RWMutex
	posts       map[string]postmodel.Post
	receipts    map[string]postReceipt
	outbox      []postports.OutboxEvent
	checkpoints map[string]string
	tombstones  map[string]postports.PostDeletionTombstone
}

func NewPostStore(seed []postmodel.Post) *PostStore {
	store := &PostStore{
		posts:       make(map[string]postmodel.Post, len(seed)),
		receipts:    map[string]postReceipt{},
		checkpoints: map[string]string{},
		tombstones:  map[string]postports.PostDeletionTombstone{},
	}
	for _, item := range seed {
		copyItem := item
		if copyItem.Version == 0 {
			copyItem.Version = 1
		}
		store.posts[item.ID] = copyItem
	}
	return store
}

func (s *PostStore) Load(_ context.Context, postID string) (*postmodel.Post, bool, error) {
	post, ok := s.FindByID(context.Background(), postID)
	return post, ok, nil
}

func (s *PostStore) Commit(_ context.Context, commit postports.Commit) (postports.CommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if receipt, ok := s.receipts[commit.IdempotencyKey]; ok {
		if !receipt.expiresAt.After(time.Now().UTC()) {
			delete(s.receipts, commit.IdempotencyKey)
		} else {
			if receipt.commandName != commit.CommandName || receipt.commandDigest != commit.CommandDigest {
				return postports.CommitResult{}, contentgenerated.AppErrorFromIdempotencyConflict("test receipt digest mismatch")
			}
			replayed := receipt.post
			return postports.CommitResult{Post: &replayed, Replayed: true}, nil
		}
	}
	current, exists := s.posts[commit.Post.ID]
	if commit.ExpectedVersion == 0 {
		for _, existing := range s.posts {
			sameAuthor := existing.AuthorId == commit.Post.AuthorId
			sameIntent := commit.Post.PublishIntentId != "" &&
				existing.PublishIntentId == commit.Post.PublishIntentId
			sameDraft := commit.Post.LocalDraftId != "" &&
				existing.LocalDraftId == commit.Post.LocalDraftId
			if sameAuthor && (sameIntent || sameDraft) {
				return postports.CommitResult{},
					contentgenerated.AppErrorFromIdempotencyConflict(
						"post publication identity already committed",
					)
			}
		}
		if exists {
			return postports.CommitResult{}, contentgenerated.AppErrorFromVersionConflict("post already exists")
		}
	} else if !exists || current.Version != commit.ExpectedVersion {
		return postports.CommitResult{}, contentgenerated.AppErrorFromVersionConflict("post version changed")
	}
	next := *commit.Post
	next.Version = commit.ExpectedVersion + 1
	s.posts[next.ID] = next
	expiresAt := commit.ReceiptExpiresAt
	if expiresAt.IsZero() {
		expiresAt = time.Now().UTC().Add(24 * time.Hour)
	}
	s.receipts[commit.IdempotencyKey] = postReceipt{
		commandName:   commit.CommandName,
		commandDigest: commit.CommandDigest,
		post:          next,
		expiresAt:     expiresAt,
	}
	for _, event := range commit.Events {
		event.AggregateVersion = next.Version
		s.outbox = append(s.outbox, event)
	}
	if commit.Tombstone != nil {
		key := strings.TrimSpace(commit.Tombstone.PostID)
		if _, exists := s.tombstones[key]; !exists {
			s.tombstones[key] = *commit.Tombstone
		}
	}
	return postports.CommitResult{Post: &next}, nil
}

// FindTombstone 与生产 Mongo adapter 同语义：保留期内返回墓碑事实。
func (s *PostStore) FindTombstone(
	_ context.Context,
	postID string,
) (postports.PostDeletionTombstone, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	tombstone, ok := s.tombstones[strings.TrimSpace(postID)]
	if !ok || (!tombstone.ExpireAt.IsZero() && !tombstone.ExpireAt.After(time.Now().UTC())) {
		return postports.PostDeletionTombstone{}, false, nil
	}
	return tombstone, true, nil
}

// RemovePostDocumentForTest 模拟聚合文档在保留期内被清理（隐私硬删）；
// 墓碑事实保留，供 410 契约测试验证读取不依赖聚合文档存活。
func (s *PostStore) RemovePostDocumentForTest(postID string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.posts, strings.TrimSpace(postID))
}

func (s *PostStore) FindByID(_ context.Context, postID string) (*postmodel.Post, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	post, ok := s.posts[strings.TrimSpace(postID)]
	if !ok {
		return nil, false
	}
	copyPost := post
	return &copyPost, true
}

func (s *PostStore) FindByPublicationIntent(
	_ context.Context,
	authorID string,
	publishIntentID string,
) (*postmodel.Post, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for _, post := range s.posts {
		if post.AuthorId == strings.TrimSpace(authorID) &&
			post.PublishIntentId == strings.TrimSpace(publishIntentID) {
			copyPost := post
			return &copyPost, true
		}
	}
	return nil, false
}

func (s *PostStore) AdjustCommentCount(_ context.Context, postID string, delta int64) (int64, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	post, ok := s.posts[postID]
	if !ok {
		return 0, false, nil
	}
	post.CommentCount += delta
	post.UpdatedAt = time.Now().UTC()
	s.posts[postID] = post
	return post.CommentCount, true, nil
}

func (s *PostStore) SetCommentCount(_ context.Context, postID string, count int64) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	post, ok := s.posts[postID]
	if !ok {
		return false, nil
	}
	post.CommentCount = count
	post.UpdatedAt = time.Now().UTC()
	s.posts[postID] = post
	return true, nil
}

func (s *PostStore) ListAll(_ context.Context) ([]postmodel.Post, error) {
	return s.list(func(postmodel.Post) bool { return true }, 0, ""), nil
}

func (s *PostStore) ListPublished(_ context.Context, limit int, cursor string) []postmodel.Post {
	return s.list(func(post postmodel.Post) bool {
		return strings.EqualFold(post.Status, "published") &&
			strings.EqualFold(post.Visibility, "public") &&
			strings.EqualFold(post.ModerationStatus, "approved")
	}, limit, cursor)
}

func (s *PostStore) ListByAuthor(_ context.Context, authorID string, limit int, cursor string) []postmodel.Post {
	return s.list(func(post postmodel.Post) bool {
		return post.AuthorId == authorID &&
			strings.EqualFold(post.Status, "published") &&
			strings.EqualFold(post.ModerationStatus, "approved")
	}, limit, cursor)
}

func (s *PostStore) list(include func(postmodel.Post) bool, limit int, cursor string) []postmodel.Post {
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := make([]postmodel.Post, 0, len(s.posts))
	for _, post := range s.posts {
		if include(post) {
			items = append(items, post)
		}
	}
	sort.Slice(items, func(i, j int) bool { return items[i].CreatedAt.After(items[j].CreatedAt) })
	if cursor != "" {
		start := len(items)
		for index := range items {
			if items[index].ID == cursor {
				start = index + 1
				break
			}
		}
		items = items[start:]
	}
	if limit > 0 && len(items) > limit {
		items = items[:limit]
	}
	return items
}

func (s *PostStore) OutboxEvents() []postports.OutboxEvent {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return append([]postports.OutboxEvent(nil), s.outbox...)
}

func (s *PostStore) ReadAfter(
	_ context.Context,
	checkpoint string,
	limit int,
) ([]postports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	s.mu.RLock()
	defer s.mu.RUnlock()

	start := 0
	if checkpoint != "" {
		found := false
		for index, event := range s.outbox {
			if testPostOutboxCheckpoint(event) == checkpoint {
				start = index + 1
				found = true
				break
			}
		}
		if !found {
			return nil, fmt.Errorf("unknown local Post outbox checkpoint %q", checkpoint)
		}
	}
	end := start + limit
	if end > len(s.outbox) {
		end = len(s.outbox)
	}
	events := make([]postports.OutboxEvent, 0, end-start)
	for _, event := range s.outbox[start:end] {
		event.Payload = append([]byte(nil), event.Payload...)
		event.Checkpoint = testPostOutboxCheckpoint(event)
		events = append(events, event)
	}
	return events, nil
}

func (s *PostStore) LoadCheckpoint(
	_ context.Context,
	consumer string,
) (string, error) {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return "", fmt.Errorf("Post projection consumer is required")
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.checkpoints[consumer], nil
}

func (s *PostStore) SaveCheckpoint(
	_ context.Context,
	consumer string,
	checkpoint string,
) error {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" || strings.TrimSpace(checkpoint) == "" {
		return fmt.Errorf("Post projection consumer and checkpoint are required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.checkpoints[consumer] = checkpoint
	return nil
}

func testPostOutboxCheckpoint(event postports.OutboxEvent) string {
	return event.OccurredAt.UTC().Format(time.RFC3339Nano) + "|" + event.EventID
}

var (
	_ postports.OutboxReader              = (*PostStore)(nil)
	_ postports.ProjectionCheckpointStore = (*PostStore)(nil)
)
