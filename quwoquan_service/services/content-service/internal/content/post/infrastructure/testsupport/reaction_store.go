// Package testsupport 中的 ReactionStore 仅用于 local_contract，不得接入生产装配。
package testsupport

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
)

type reactionReceipt struct {
	commandName   string
	commandDigest string
	basisDigest   string
	actor         reactiondomain.Actor
	outcome       reactionports.ReceiptOutcome
	snapshot      reactiondomain.Snapshot
	changed       bool
	expiresAt     time.Time
}

type ReactionStore struct {
	mu           sync.RWMutex
	records      map[string]reactiondomain.Snapshot
	receipts     map[string]reactionReceipt
	outbox       []reactionports.OutboxFact
	nextSequence [reactionports.ContentReactionOutboxPartitionCount]int64
	checkpoints  map[string]reactionports.OutboxPartitionLease
	cleanupJobs  map[string]reactionapp.LifecycleCleanupJob
}

func NewReactionStore() *ReactionStore {
	return &ReactionStore{
		records:     map[string]reactiondomain.Snapshot{},
		receipts:    map[string]reactionReceipt{},
		checkpoints: map[string]reactionports.OutboxPartitionLease{}, cleanupJobs: map[string]reactionapp.LifecycleCleanupJob{},
	}
}

func (s *ReactionStore) Ensure(_ context.Context, j reactionapp.LifecycleCleanupJob) (reactionapp.LifecycleCleanupJob, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if x, ok := s.cleanupJobs[j.ID]; ok {
		return x, nil
	}
	s.cleanupJobs[j.ID] = j
	return j, nil
}
func (s *ReactionStore) Claim(_ context.Context, id string, _ time.Time, _ time.Duration) (reactionapp.LifecycleCleanupJob, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	j, ok := s.cleanupJobs[id]
	if !ok || j.Completed {
		return reactionapp.LifecycleCleanupJob{}, false, nil
	}
	j.LeaseEpoch++
	s.cleanupJobs[id] = j
	return j, true, nil
}
func (s *ReactionStore) Advance(_ context.Context, id string, epoch int64, cursor string, checkpoint int64, done bool) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	j := s.cleanupJobs[id]
	if j.LeaseEpoch != epoch {
		return errors.New("stale cleanup lease")
	}
	j.Cursor = cursor
	j.Checkpoint = checkpoint
	j.Completed = done
	s.cleanupJobs[id] = j
	return nil
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
	identity reactiondomain.Identity,
	idempotencyKey string,
	commandName string,
	commandDigest string,
	basisDigest string,
) (reactionports.CommitResult, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, found := s.receipts[testReceiptKey(identity.Actor, idempotencyKey)]
	if !found {
		return reactionports.CommitResult{}, false, nil
	}
	if !receipt.expiresAt.After(time.Now().UTC()) {
		delete(s.receipts, testReceiptKey(identity.Actor, idempotencyKey))
		return reactionports.CommitResult{}, false, nil
	}
	if receipt.commandName != commandName || receipt.commandDigest != commandDigest || receipt.basisDigest != basisDigest {
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
		Replayed:  true, Outcome: receipt.outcome,
	}, true, nil
}

func testReceiptKey(actor reactiondomain.Actor, key string) string {
	return string(actor.Dimension) + "\x1f" + actor.ID + "\x1f" + key
}
func (s *ReactionStore) RecoverReceipt(_ context.Context, actor reactiondomain.Actor, key, command string) (reactionports.CommitResult, bool, error) {
	s.mu.RLock()
	r, ok := s.receipts[testReceiptKey(actor, key)]
	s.mu.RUnlock()
	if !ok {
		return reactionports.CommitResult{}, false, nil
	}
	if r.commandName != command {
		return reactionports.CommitResult{}, false, contentgenerated.AppErrorFromIdempotencyConflict("receipt mismatch")
	}
	a, e := reactiondomain.Restore(r.snapshot)
	return reactionports.CommitResult{Aggregate: a, Changed: r.changed, Replayed: true, Outcome: r.outcome}, true, e
}
func (s *ReactionStore) FinalizeExpired(_ context.Context, identity reactiondomain.Identity, key, command, digest, basis string, until time.Time) (reactionports.CommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	k := testReceiptKey(identity.Actor, key)
	if r, ok := s.receipts[k]; ok {
		a, e := reactiondomain.Restore(r.snapshot)
		return reactionports.CommitResult{Aggregate: a, Changed: r.changed, Replayed: true, Outcome: r.outcome}, e
	}
	s.receipts[k] = reactionReceipt{commandName: command, commandDigest: digest, basisDigest: basis, actor: identity.Actor, outcome: reactionports.ReceiptOutcomeExpired, expiresAt: until.Add(24 * time.Hour)}
	return reactionports.CommitResult{Outcome: reactionports.ReceiptOutcomeExpired}, nil
}

func (s *ReactionStore) Commit(
	_ context.Context,
	commit reactionports.Commit,
) (reactionports.CommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	key := testReceiptKey(commit.Aggregate.Identity().Actor, commit.IdempotencyKey)
	if receipt, found := s.receipts[key]; found {
		if receipt.expiresAt.After(time.Now().UTC()) {
			if receipt.commandName != commit.CommandName ||
				receipt.commandDigest != commit.CommandDigest || receipt.basisDigest != commit.BasisDigest {
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
				Replayed:  true, Outcome: receipt.outcome,
			}, nil
		}
		delete(s.receipts, key)
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
	s.receipts[key] = reactionReceipt{
		commandName:   commit.CommandName,
		commandDigest: commit.CommandDigest, basisDigest: commit.BasisDigest,
		actor: snapshot.Identity.Actor, outcome: reactionports.ReceiptOutcomeCommitted,
		snapshot:  snapshot,
		changed:   commit.Changed,
		expiresAt: expiresAt,
	}
	facts := cloneReactionOutboxFacts(commit.Events)
	for index := range facts {
		partitionKey := strings.TrimSpace(facts[index].AggregateID)
		partitionID := reactionports.OutboxPartitionForKey(partitionKey)
		s.nextSequence[partitionID]++
		facts[index].PartitionKey = partitionKey
		facts[index].PartitionID = partitionID
		facts[index].PartitionSequence = s.nextSequence[partitionID]
	}
	s.outbox = append(s.outbox, facts...)
	aggregate, err := reactiondomain.Restore(snapshot)
	if err != nil {
		return reactionports.CommitResult{}, err
	}
	return reactionports.CommitResult{
		Aggregate: aggregate,
		Changed:   commit.Changed, Outcome: reactionports.ReceiptOutcomeCommitted,
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

func (s *ReactionStore) ClaimOutboxPartitions(
	_ context.Context,
	consumer string,
	owner string,
	leaseDuration time.Duration,
	maxPartitions int,
) ([]reactionports.OutboxPartitionLease, error) {
	consumer = strings.TrimSpace(consumer)
	owner = strings.TrimSpace(owner)
	if consumer == "" || owner == "" {
		return nil, fmt.Errorf("reaction checkpoint identity is required")
	}
	if maxPartitions <= 0 || maxPartitions > reactionports.ContentReactionOutboxPartitionCount {
		maxPartitions = reactionports.ContentReactionOutboxPartitionCount
	}
	now := time.Now().UTC()
	if leaseDuration <= 0 {
		leaseDuration = time.Minute
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	leases := make([]reactionports.OutboxPartitionLease, 0, maxPartitions)
	for partitionID := 0; partitionID < reactionports.ContentReactionOutboxPartitionCount && len(leases) < maxPartitions; partitionID++ {
		key := fmt.Sprintf("%s:%02d", consumer, partitionID)
		current := s.checkpoints[key]
		if current.Owner != "" && current.Owner != owner && current.LeaseUntil.After(now) {
			continue
		}
		current.Consumer = consumer
		current.Owner = owner
		current.PartitionID = partitionID
		current.LeaseEpoch++
		current.LeaseUntil = now.Add(leaseDuration)
		s.checkpoints[key] = current
		leases = append(leases, current)
	}
	return leases, nil
}

func (s *ReactionStore) ReadOutboxPartition(
	_ context.Context,
	lease reactionports.OutboxPartitionLease,
	limit int,
) ([]reactionports.OutboxFact, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if limit <= 0 {
		limit = 100
	}
	facts := make([]reactionports.OutboxFact, 0, limit)
	expected := lease.Sequence + 1
	for _, fact := range s.outbox {
		if fact.PartitionID != lease.PartitionID || fact.PartitionSequence <= lease.Sequence {
			continue
		}
		if fact.PartitionSequence != expected {
			return nil, fmt.Errorf("reaction partition gap")
		}
		facts = append(facts, fact)
		expected++
		if len(facts) == limit {
			break
		}
	}
	return cloneReactionOutboxFacts(facts), nil
}

func (s *ReactionStore) AdvanceOutboxCheckpoint(
	_ context.Context,
	lease reactionports.OutboxPartitionLease,
	fact reactionports.OutboxFact,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	key := fmt.Sprintf("%s:%02d", lease.Consumer, lease.PartitionID)
	current := s.checkpoints[key]
	if current.Owner != lease.Owner || current.LeaseEpoch != lease.LeaseEpoch ||
		current.Sequence != lease.Sequence || current.LeaseUntil.Before(time.Now().UTC()) ||
		fact.PartitionID != lease.PartitionID || fact.PartitionSequence != lease.Sequence+1 {
		return reactionports.ErrOutboxLeaseLost
	}
	current.Sequence = fact.PartitionSequence
	s.checkpoints[key] = current
	return nil
}

func (s *ReactionStore) CheckpointSequence(consumer string, partitionID int) int64 {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.checkpoints[fmt.Sprintf("%s:%02d", consumer, partitionID)].Sequence
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
