// Package testsupport 中的 ReactionStore 仅用于 local_contract，不得接入生产装配。
package testsupport

import (
	"context"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
)

type reactionReceipt struct {
	commandName   string
	commandDigest string
	snapshot      reactiondomain.Snapshot
	changed       bool
	expiresAt     time.Time
}

type ReactionStore struct {
	mu          sync.RWMutex
	records     map[string]reactiondomain.Snapshot
	receipts    map[string]reactionReceipt
	outbox      []reactionports.OutboxFact
	checkpoints map[string]string
}

func NewReactionStore() *ReactionStore {
	return &ReactionStore{
		records:     map[string]reactiondomain.Snapshot{},
		receipts:    map[string]reactionReceipt{},
		checkpoints: map[string]string{},
	}
}

func (s *ReactionStore) Load(
	_ context.Context,
	aggregateID string,
) (*reactiondomain.ContentReaction, bool, error) {
	s.mu.RLock()
	snapshot, found := s.records[aggregateID]
	s.mu.RUnlock()
	if !found {
		return nil, false, nil
	}
	aggregate, err := reactiondomain.Restore(snapshot)
	if err != nil {
		return nil, false, err
	}
	return aggregate, true, nil
}

func (s *ReactionStore) FindReceipt(
	_ context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (reactionports.CommitResult, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, found := s.receipts[idempotencyKey]
	if !found {
		return reactionports.CommitResult{}, false, nil
	}
	if !receipt.expiresAt.After(time.Now().UTC()) {
		delete(s.receipts, idempotencyKey)
		return reactionports.CommitResult{}, false, nil
	}
	if receipt.commandName != commandName || receipt.commandDigest != commandDigest {
		return reactionports.CommitResult{},
			false,
			contentgenerated.AppErrorFromIdempotencyConflict("reaction test receipt digest mismatch")
	}
	aggregate, err := reactiondomain.Restore(receipt.snapshot)
	if err != nil {
		return reactionports.CommitResult{}, false, err
	}
	return reactionports.CommitResult{
		Aggregate: aggregate,
		Changed:   receipt.changed,
		Replayed:  true,
	}, true, nil
}

func (s *ReactionStore) Commit(
	_ context.Context,
	commit reactionports.Commit,
) (reactionports.CommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if receipt, found := s.receipts[commit.IdempotencyKey]; found {
		if receipt.expiresAt.After(time.Now().UTC()) {
			if receipt.commandName != commit.CommandName ||
				receipt.commandDigest != commit.CommandDigest {
				return reactionports.CommitResult{},
					contentgenerated.AppErrorFromIdempotencyConflict("reaction test receipt digest mismatch")
			}
			aggregate, err := reactiondomain.Restore(receipt.snapshot)
			if err != nil {
				return reactionports.CommitResult{}, err
			}
			return reactionports.CommitResult{
				Aggregate: aggregate,
				Changed:   receipt.changed,
				Replayed:  true,
			}, nil
		}
		delete(s.receipts, commit.IdempotencyKey)
	}
	if commit.Aggregate == nil || commit.IdempotencyKey == "" {
		return reactionports.CommitResult{},
			contentgenerated.AppErrorFromIdempotencyConflict("reaction commit requires aggregate and idempotency key")
	}
	snapshot := commit.Aggregate.Snapshot()
	current, exists := s.records[snapshot.ID]
	mutatesAggregate := snapshot.Version == commit.ExpectedVersion+1
	isNoop := snapshot.Version == commit.ExpectedVersion
	if !mutatesAggregate && !isNoop {
		return reactionports.CommitResult{},
			contentgenerated.AppErrorFromVersionConflict("reaction version is not monotonic")
	}
	if commit.Changed && !mutatesAggregate {
		return reactionports.CommitResult{},
			contentgenerated.AppErrorFromVersionConflict("reaction changed command did not advance version")
	}
	if len(commit.Events) > 0 && (!commit.Changed || !mutatesAggregate) {
		return reactionports.CommitResult{},
			contentgenerated.AppErrorFromVersionConflict("reaction noop command carries outbox facts")
	}
	for _, event := range commit.Events {
		if event.AggregateID != snapshot.ID ||
			event.AggregateVersion != snapshot.Version {
			return reactionports.CommitResult{},
				contentgenerated.AppErrorFromVersionConflict("reaction outbox version does not match aggregate")
		}
	}
	if mutatesAggregate {
		if commit.ExpectedVersion == 0 {
			if exists {
				return reactionports.CommitResult{},
					contentgenerated.AppErrorFromVersionConflict("reaction already exists")
			}
		} else if !exists || current.Version != commit.ExpectedVersion {
			return reactionports.CommitResult{},
				contentgenerated.AppErrorFromVersionConflict("reaction version changed")
		}
		s.records[snapshot.ID] = snapshot
	} else if !exists || current.Version != commit.ExpectedVersion {
		return reactionports.CommitResult{},
			contentgenerated.AppErrorFromVersionConflict("reaction noop used stale version")
	}
	expiresAt := commit.ReceiptExpiresAt
	if expiresAt.IsZero() {
		expiresAt = time.Now().UTC().Add(24 * time.Hour)
	}
	s.receipts[commit.IdempotencyKey] = reactionReceipt{
		commandName:   commit.CommandName,
		commandDigest: commit.CommandDigest,
		snapshot:      snapshot,
		changed:       commit.Changed,
		expiresAt:     expiresAt,
	}
	facts := cloneReactionOutboxFacts(commit.Events)
	for index := range facts {
		facts[index].Checkpoint = strconv.Itoa(len(s.outbox) + index + 1)
	}
	s.outbox = append(s.outbox, facts...)
	aggregate, err := reactiondomain.Restore(snapshot)
	if err != nil {
		return reactionports.CommitResult{}, err
	}
	return reactionports.CommitResult{
		Aggregate: aggregate,
		Changed:   commit.Changed,
	}, nil
}

func (s *ReactionStore) ReadContentReactionState(
	_ context.Context,
	identity reactiondomain.Identity,
) (reactionapp.ContentReactionStateSlice, error) {
	s.mu.RLock()
	snapshot, found := s.records[identity.AggregateID()]
	s.mu.RUnlock()
	if !found {
		return reactionapp.ContentReactionStateSlice{
			PostID: identity.Target.ID,
		}, nil
	}
	return reactionapp.ContentReactionStateSlice{
		Found:     true,
		PostID:    snapshot.Identity.Target.ID,
		Liked:     snapshot.Value == reactiondomain.ValueLike,
		Version:   snapshot.Version,
		UpdatedAt: snapshot.UpdatedAt,
	}, nil
}

func (s *ReactionStore) FindReactionTarget(
	_ context.Context,
	target reactiondomain.Target,
) (reactionapp.ReactionTargetSlice, error) {
	if err := target.Validate(); err != nil {
		return reactionapp.ReactionTargetSlice{}, err
	}
	if strings.TrimSpace(target.ID) == "" {
		return reactionapp.ReactionTargetSlice{}, nil
	}
	return reactionapp.ReactionTargetSlice{
		Exists:   true,
		AuthorID: "author-" + strings.TrimSpace(target.ID),
	}, nil
}

func (s *ReactionStore) CountCommentReactions(
	_ context.Context,
	commentID string,
) (int64, int64, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var likeCount int64
	var dislikeCount int64
	for _, snapshot := range s.records {
		if snapshot.Identity.Target.Kind != reactiondomain.TargetKindComment ||
			snapshot.Identity.Target.ID != strings.TrimSpace(commentID) {
			continue
		}
		switch snapshot.Value {
		case reactiondomain.ValueLike:
			likeCount++
		case reactiondomain.ValueDislike:
			dislikeCount++
		}
	}
	return likeCount, dislikeCount, nil
}

func (s *ReactionStore) ReadCommentReactionCounts(
	_ context.Context,
	commentIDs []string,
) (map[string]reactiondomain.CommentReactionCounts, error) {
	requested := map[string]struct{}{}
	for _, id := range commentIDs {
		if id = strings.TrimSpace(id); id != "" {
			requested[id] = struct{}{}
		}
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	counts := make(map[string]reactiondomain.CommentReactionCounts, len(requested))
	for _, snapshot := range s.records {
		if snapshot.Identity.Target.Kind != reactiondomain.TargetKindComment {
			continue
		}
		commentID := snapshot.Identity.Target.ID
		if _, found := requested[commentID]; !found {
			continue
		}
		value := counts[commentID]
		switch snapshot.Value {
		case reactiondomain.ValueLike:
			value.LikeCount++
		case reactiondomain.ValueDislike:
			value.DislikeCount++
		}
		counts[commentID] = value
	}
	return counts, nil
}

func (s *ReactionStore) ReadCommentReactionValues(
	_ context.Context,
	actor reactiondomain.Actor,
	commentIDs []string,
) (map[string]reactiondomain.Value, error) {
	if err := actor.Validate(); err != nil {
		return nil, err
	}
	requested := map[string]struct{}{}
	for _, id := range commentIDs {
		if id = strings.TrimSpace(id); id != "" {
			requested[id] = struct{}{}
		}
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	values := map[string]reactiondomain.Value{}
	for _, snapshot := range s.records {
		if snapshot.Identity.Target.Kind != reactiondomain.TargetKindComment || snapshot.Identity.Actor != actor {
			continue
		}
		if _, ok := requested[snapshot.Identity.Target.ID]; ok && snapshot.Value != reactiondomain.ValueNone {
			values[snapshot.Identity.Target.ID] = snapshot.Value
		}
	}
	return values, nil
}

func (s *ReactionStore) ReadAuthorLikedFlags(
	ctx context.Context,
	commentIDsByPostAuthor map[string][]string,
) (map[string]bool, error) {
	flags := map[string]bool{}
	for postAuthorID, commentIDs := range commentIDsByPostAuthor {
		actor, err := reactiondomain.NewActor(
			reactiondomain.ActorDimensionPersona,
			strings.TrimSpace(postAuthorID),
		)
		if err != nil {
			return nil, err
		}
		values, err := s.ReadCommentReactionValues(ctx, actor, commentIDs)
		if err != nil {
			return nil, err
		}
		for commentID, value := range values {
			if value == reactiondomain.ValueLike {
				flags[commentID] = true
			}
		}
	}
	return flags, nil
}

func (s *ReactionStore) CountActiveReactions(
	_ context.Context,
	postID string,
) (int64, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var count int64
	for _, snapshot := range s.records {
		if snapshot.Identity.Target.Kind == reactiondomain.TargetKindPost &&
			snapshot.Identity.Target.ID == postID && snapshot.Value == reactiondomain.ValueLike {
			count++
		}
	}
	return count, nil
}

func (s *ReactionStore) CountActiveReactionsForActor(
	_ context.Context,
	actor reactiondomain.Actor,
) (int64, error) {
	if err := actor.Validate(); err != nil {
		return 0, err
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	var count int64
	for _, snapshot := range s.records {
		if snapshot.Identity.Target.Kind == reactiondomain.TargetKindPost &&
			snapshot.Identity.Actor == actor && snapshot.Value == reactiondomain.ValueLike {
			count++
		}
	}
	return count, nil
}

func (s *ReactionStore) ListActiveProfileReactions(
	_ context.Context,
	actorID string,
	limit int,
) ([]reactionports.ProfileActivitySlice, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	normalizedActorID := strings.TrimSpace(actorID)
	slices := make([]reactionports.ProfileActivitySlice, 0, len(s.records))
	for _, snapshot := range s.records {
		if snapshot.Identity.Target.Kind != reactiondomain.TargetKindPost ||
			snapshot.Value != reactiondomain.ValueLike ||
			snapshot.Identity.Actor.Dimension != reactiondomain.ActorDimensionPersona {
			continue
		}
		if normalizedActorID != "" && snapshot.Identity.Actor.ID != normalizedActorID {
			continue
		}
		slices = append(slices, reactionports.ProfileActivitySlice{
			ReactionID: snapshot.ID,
			PostID:     snapshot.Identity.Target.ID,
			ActorID:    snapshot.Identity.Actor.ID,
			OccurredAt: snapshot.UpdatedAt,
		})
	}
	sort.Slice(slices, func(i, j int) bool {
		if !slices[i].OccurredAt.Equal(slices[j].OccurredAt) {
			return slices[i].OccurredAt.After(slices[j].OccurredAt)
		}
		return slices[i].ReactionID > slices[j].ReactionID
	})
	if limit <= 0 || limit > 1000 {
		limit = 1000
	}
	if len(slices) > limit {
		slices = slices[:limit]
	}
	return slices, nil
}

func (s *ReactionStore) ListActiveReactionsForPost(
	_ context.Context,
	postID string,
	limit int,
) ([]reactiondomain.Identity, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	postID = strings.TrimSpace(postID)
	if postID == "" {
		return nil, fmt.Errorf("Post id is required")
	}
	identities := make([]reactiondomain.Identity, 0)
	for _, snapshot := range s.records {
		if snapshot.Identity.Target.Kind == reactiondomain.TargetKindPost &&
			snapshot.Identity.Target.ID == postID && snapshot.Value == reactiondomain.ValueLike {
			identities = append(identities, snapshot.Identity)
		}
	}
	sort.Slice(identities, func(i, j int) bool {
		return identities[i].AggregateID() < identities[j].AggregateID()
	})
	if limit <= 0 || limit > 1000 {
		limit = 500
	}
	if len(identities) > limit {
		identities = identities[:limit]
	}
	return identities, nil
}

func (s *ReactionStore) ReadAfter(
	_ context.Context,
	checkpoint string,
	limit int,
) ([]reactionports.OutboxFact, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	start := 0
	if strings.TrimSpace(checkpoint) != "" {
		parsed, err := strconv.Atoi(checkpoint)
		if err != nil || parsed < 0 {
			return nil, fmt.Errorf("invalid reaction checkpoint")
		}
		start = parsed
	}
	if start > len(s.outbox) {
		return nil, fmt.Errorf("reaction checkpoint exceeds outbox")
	}
	if limit <= 0 || start+limit > len(s.outbox) {
		limit = len(s.outbox) - start
	}
	return cloneReactionOutboxFacts(s.outbox[start : start+limit]), nil
}

func (s *ReactionStore) LoadCheckpoint(
	_ context.Context,
	consumer string,
) (string, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.checkpoints[consumer], nil
}

func (s *ReactionStore) SaveCheckpoint(
	_ context.Context,
	consumer string,
	checkpoint string,
) error {
	if strings.TrimSpace(consumer) == "" || strings.TrimSpace(checkpoint) == "" {
		return fmt.Errorf("reaction checkpoint identity is required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.checkpoints[consumer] = checkpoint
	return nil
}

func (s *ReactionStore) OutboxFacts() []reactionports.OutboxFact {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return cloneReactionOutboxFacts(s.outbox)
}

func (s *ReactionStore) AggregateCount() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.records)
}

func cloneReactionOutboxFacts(
	facts []reactionports.OutboxFact,
) []reactionports.OutboxFact {
	cloned := make([]reactionports.OutboxFact, len(facts))
	for index, fact := range facts {
		cloned[index] = fact
		cloned[index].Payload = append([]byte(nil), fact.Payload...)
	}
	return cloned
}

var _ reactionports.ProfileActivityReader = (*ReactionStore)(nil)
