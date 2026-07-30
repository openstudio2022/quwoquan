package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	homepageapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
	homepageports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
)

// MemoryHomepageStore 是 alpha/local_contract 显式注入的适配器；production
// composition 不得引用它。
type MemoryHomepageStore struct {
	mu          sync.RWMutex
	homepages   map[string]homepagemodel.Snapshot
	details     map[string]homepageports.DetailProjection
	receipts    map[string]memoryReceipt
	outbox      map[string]homepageports.OutboxEvent
	followers   map[string]map[string]memoryFollower
	checkpoints map[string]string
}

type memoryReceipt struct {
	ActorID        string
	IdempotencyKey string
	CommandName    string
	CommandDigest  string
	Result         homepagemodel.Snapshot
	ExpiresAt      time.Time
}

type memoryFollower struct {
	Following     bool
	SourceVersion int64
	UpdatedAt     time.Time
}

func NewMemoryHomepageStore(seeds ...homepagemodel.Snapshot) (*MemoryHomepageStore, error) {
	store := &MemoryHomepageStore{
		homepages:   map[string]homepagemodel.Snapshot{},
		details:     map[string]homepageports.DetailProjection{},
		receipts:    map[string]memoryReceipt{},
		outbox:      map[string]homepageports.OutboxEvent{},
		followers:   map[string]map[string]memoryFollower{},
		checkpoints: map[string]string{},
	}
	for _, seed := range seeds {
		aggregate, err := homepagemodel.Restore(seed)
		if err != nil {
			return nil, err
		}
		snapshot := aggregate.Snapshot()
		if err := store.ensureUniqueLocked(snapshot, ""); err != nil {
			return nil, err
		}
		store.homepages[snapshot.ID] = snapshot
	}
	return store, nil
}

func (s *MemoryHomepageStore) Load(
	_ context.Context,
	homepageID string,
) (*homepagemodel.Homepage, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	snapshot, found := s.homepages[strings.TrimSpace(homepageID)]
	if !found {
		return nil, false, nil
	}
	aggregate, err := homepagemodel.Restore(snapshot)
	return aggregate, err == nil, err
}

func (s *MemoryHomepageStore) FindByCanonical(
	_ context.Context,
	canonicalEntityID string,
) (*homepagemodel.Homepage, bool, error) {
	return s.findAggregate(func(snapshot homepagemodel.Snapshot) bool {
		return snapshot.CanonicalEntityID == strings.TrimSpace(canonicalEntityID)
	})
}

func (s *MemoryHomepageStore) FindBySource(
	_ context.Context,
	sourceOwner string,
	sourceEntityRef string,
) (*homepagemodel.Homepage, bool, error) {
	return s.findAggregate(func(snapshot homepagemodel.Snapshot) bool {
		return snapshot.SourceOwner == strings.TrimSpace(sourceOwner) &&
			snapshot.SourceEntityRef == strings.TrimSpace(sourceEntityRef)
	})
}

func (s *MemoryHomepageStore) findAggregate(
	matches func(homepagemodel.Snapshot) bool,
) (*homepagemodel.Homepage, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for _, snapshot := range s.homepages {
		if matches(snapshot) {
			aggregate, err := homepagemodel.Restore(snapshot)
			return aggregate, err == nil, err
		}
	}
	return nil, false, nil
}

func (s *MemoryHomepageStore) FindExact(
	_ context.Context,
	lookup homepageports.ExactLookup,
) (homepagemodel.Snapshot, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	id := strings.TrimSpace(lookup.ID)
	canonical := strings.TrimSpace(lookup.CanonicalEntityID)
	alias := homepagemodel.NormalizeLookupAlias(lookup.LookupAlias)
	for _, snapshot := range s.homepages {
		if id != "" && snapshot.ID == id {
			return snapshot, true, nil
		}
		if canonical != "" && snapshot.CanonicalEntityID == canonical {
			return snapshot, true, nil
		}
		if alias != "" {
			for _, candidate := range snapshot.LookupAliases {
				if candidate == alias {
					return snapshot, true, nil
				}
			}
		}
		if strings.TrimSpace(lookup.SourceOwner) != "" &&
			snapshot.SourceOwner == strings.TrimSpace(lookup.SourceOwner) &&
			snapshot.SourceEntityRef == strings.TrimSpace(lookup.SourceEntityRef) {
			return snapshot, true, nil
		}
	}
	return homepagemodel.Snapshot{}, false, nil
}

func (s *MemoryHomepageStore) Search(
	_ context.Context,
	query homepageports.SearchQuery,
) (homepageports.Page, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	status := strings.TrimSpace(query.Status)
	if status == "" {
		status = string(homepagemodel.StatusPublished)
	}
	items := make([]homepagemodel.Snapshot, 0, len(s.homepages))
	for _, snapshot := range s.homepages {
		if snapshot.Status != homepagemodel.Status(status) ||
			(strings.TrimSpace(query.HomepageType) != "" && snapshot.HomepageType != strings.TrimSpace(query.HomepageType)) ||
			(strings.TrimSpace(query.City) != "" && snapshot.City != strings.TrimSpace(query.City)) {
			continue
		}
		items = append(items, snapshot)
	}
	if strings.TrimSpace(query.Query) != "" {
		index := make(map[string]homepagemodel.Snapshot, len(items))
		documents := make([]rtsearch.Document, 0, len(items))
		for _, snapshot := range items {
			view := application.Homepage(snapshotToView(snapshot, s.details[snapshot.ID]))
			index[snapshot.ID] = snapshot
			documents = append(documents, application.ProjectHomepageToSearchDocument(view))
		}
		response := rtsearch.Execute(rtsearch.Request{
			Query:       query.Query,
			Mode:        rtsearch.ModeResult,
			ObjectTypes: []string{rtsearch.ObjectTypeEntityHomepage},
			Limit:       len(documents),
		}, documents)
		ranked := make([]homepagemodel.Snapshot, 0, len(response.Hits))
		for _, hit := range response.Hits {
			if snapshot, found := index[hit.ObjectID]; found {
				ranked = append(ranked, snapshot)
			}
		}
		return memoryPage(ranked, query.Cursor, query.Limit), nil
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].UpdatedAt.Equal(items[j].UpdatedAt) {
			return items[i].ID > items[j].ID
		}
		return items[i].UpdatedAt.After(items[j].UpdatedAt)
	})
	return memoryPage(items, query.Cursor, query.Limit), nil
}

func snapshotToView(
	snapshot homepagemodel.Snapshot,
	projection homepageports.DetailProjection,
) application.Homepage {
	view := application.Homepage{
		ID: snapshot.ID, Title: snapshot.Title, Subtitle: snapshot.Subtitle,
		HomepageType: snapshot.HomepageType, CanonicalEntityID: snapshot.CanonicalEntityID,
		Status: string(snapshot.Status), CategoryTags: snapshot.CategoryTags,
		City: snapshot.City, Address: snapshot.Address, Location: snapshot.Location,
		UpdatedAt: snapshot.UpdatedAt,
	}
	return application.Homepage(homepageapp.ApplyDetailProjection(homepageapp.View(view), projection))
}

func (s *MemoryHomepageStore) ListBySourceOwner(
	_ context.Context,
	sourceOwner string,
	cursor string,
	limit int,
) (homepageports.Page, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := make([]homepagemodel.Snapshot, 0)
	for _, snapshot := range s.homepages {
		if snapshot.SourceOwner == strings.TrimSpace(sourceOwner) {
			items = append(items, snapshot)
		}
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].UpdatedAt.Equal(items[j].UpdatedAt) {
			return items[i].ID > items[j].ID
		}
		return items[i].UpdatedAt.After(items[j].UpdatedAt)
	})
	return memoryPage(items, cursor, limit), nil
}

func (s *MemoryHomepageStore) Scan(
	_ context.Context,
	cursor string,
	limit int,
) (homepageports.Page, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	ids := make([]string, 0, len(s.homepages))
	for id := range s.homepages {
		if strings.TrimSpace(cursor) == "" || id > strings.TrimSpace(cursor) {
			ids = append(ids, id)
		}
	}
	sort.Strings(ids)
	limit = boundedLimit(limit, 500, 2000)
	page := homepageports.Page{}
	for index, id := range ids {
		if index == limit {
			page.NextCursor = ids[limit-1]
			break
		}
		page.Items = append(page.Items, s.homepages[id])
	}
	return page, nil
}

func (s *MemoryHomepageStore) Count(_ context.Context) (int64, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return int64(len(s.homepages)), nil
}

func (s *MemoryHomepageStore) LoadDetailProjection(
	_ context.Context,
	homepageID string,
) (homepageports.DetailProjection, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	projection, found := s.details[strings.TrimSpace(homepageID)]
	return cloneDetailProjection(projection), found, nil
}

func (s *MemoryHomepageStore) UpsertReviewSummary(
	_ context.Context,
	homepageID string,
	averageRating *float64,
	ratingCount int,
	highlightTags []string,
	updatedAt time.Time,
) error {
	homepageID = strings.TrimSpace(homepageID)
	s.mu.Lock()
	defer s.mu.Unlock()
	projection := s.details[homepageID]
	projection.HomepageID = homepageID
	projection.AverageRating = cloneFloat64Pointer(averageRating)
	projection.RatingCount = ratingCount
	projection.ReviewSummary = &homepagemodel.ReviewSummary{
		AverageRating: cloneFloat64Pointer(averageRating),
		RatingCount:   ratingCount,
		HighlightTags: append([]string(nil), highlightTags...),
	}
	projection.UpdatedAt = updatedAt.UTC()
	s.details[homepageID] = cloneDetailProjection(projection)
	return nil
}

// SeedDetailProjection 仅供 alpha/local_contract fixture 装配。生产读投影必须由
// 对象事实消费者写入，不允许从 Homepage aggregate seed 反向恢复。
func (s *MemoryHomepageStore) SeedDetailProjection(projection homepageports.DetailProjection) error {
	homepageID := strings.TrimSpace(projection.HomepageID)
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, found := s.homepages[homepageID]; !found {
		return errors.New("homepage detail projection requires existing homepage")
	}
	projection.HomepageID = homepageID
	s.details[homepageID] = cloneDetailProjection(projection)
	return nil
}

func memoryPage(items []homepagemodel.Snapshot, cursor string, limit int) homepageports.Page {
	limit = boundedLimit(limit, 20, 500)
	start := 0
	if value := strings.TrimSpace(cursor); value != "" {
		if parsed, err := strconv.Atoi(value); err == nil && parsed >= 0 {
			start = parsed
		}
	}
	if start > len(items) {
		start = len(items)
	}
	end := start + limit
	if end > len(items) {
		end = len(items)
	}
	page := homepageports.Page{Items: append([]homepagemodel.Snapshot(nil), items[start:end]...)}
	if end < len(items) {
		page.NextCursor = strconv.Itoa(end)
	}
	return page
}

func (s *MemoryHomepageStore) FindReceipt(
	_ context.Context,
	actorID string,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (homepageports.CommitResult, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receipt, found := s.receipts[receiptID(actorID, idempotencyKey)]
	if !found {
		return homepageports.CommitResult{}, false, nil
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		delete(s.receipts, receiptID(actorID, idempotencyKey))
		return homepageports.CommitResult{}, false, nil
	}
	if receipt.CommandName != commandName || receipt.CommandDigest != commandDigest {
		return homepageports.CommitResult{}, false, generated.AppErrorFromIdempotencyConflict(
			"idempotency key was reused with a different homepage command",
		)
	}
	aggregate, err := homepagemodel.Restore(receipt.Result)
	return homepageports.CommitResult{Aggregate: aggregate, Replayed: true}, err == nil, err
}

func (s *MemoryHomepageStore) RecordNoopReceipt(
	_ context.Context,
	noop homepageports.NoopReceipt,
) (homepageports.CommitResult, error) {
	if noop.Aggregate == nil {
		return homepageports.CommitResult{}, errors.New("homepage no-op receipt requires aggregate")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	key := receiptID(noop.ActorID, noop.IdempotencyKey)
	if existing, found := s.receipts[key]; found {
		if existing.CommandName != noop.CommandName || existing.CommandDigest != noop.CommandDigest {
			return homepageports.CommitResult{}, generated.AppErrorFromIdempotencyConflict(
				"idempotency key was reused with a different homepage command",
			)
		}
		aggregate, err := homepagemodel.Restore(existing.Result)
		return homepageports.CommitResult{Aggregate: aggregate, Replayed: true}, err
	}
	snapshot := noop.Aggregate.Snapshot()
	s.receipts[key] = memoryReceipt{
		ActorID:        noop.ActorID,
		IdempotencyKey: noop.IdempotencyKey,
		CommandName:    noop.CommandName,
		CommandDigest:  noop.CommandDigest,
		Result:         snapshot,
		ExpiresAt:      normalizedExpiry(noop.ReceiptExpiresAt),
	}
	aggregate, err := homepagemodel.Restore(snapshot)
	return homepageports.CommitResult{Aggregate: aggregate}, err
}

func (s *MemoryHomepageStore) Commit(
	_ context.Context,
	commit homepageports.Commit,
) (homepageports.CommitResult, error) {
	if err := validateCommit(commit); err != nil {
		return homepageports.CommitResult{}, err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	receiptKey := receiptID(commit.ActorID, commit.IdempotencyKey)
	if existing, found := s.receipts[receiptKey]; found {
		if existing.CommandName != commit.CommandName || existing.CommandDigest != commit.CommandDigest {
			return homepageports.CommitResult{}, generated.AppErrorFromIdempotencyConflict(
				"idempotency key was reused with a different homepage command",
			)
		}
		aggregate, err := homepagemodel.Restore(existing.Result)
		return homepageports.CommitResult{Aggregate: aggregate, Replayed: true}, err
	}
	snapshot := commit.Aggregate.Snapshot()
	current, exists := s.homepages[snapshot.ID]
	if commit.ExpectedVersion == 0 {
		if exists {
			return homepageports.CommitResult{}, generated.AppErrorFromVersionConflict("homepage already exists")
		}
	} else if !exists || current.Version != commit.ExpectedVersion {
		return homepageports.CommitResult{}, generated.AppErrorFromVersionConflict(
			"homepage version changed before commit",
		)
	}
	if err := s.ensureUniqueLocked(snapshot, snapshot.ID); err != nil {
		return homepageports.CommitResult{}, err
	}
	if _, duplicate := s.outbox[commit.Event.EventID]; duplicate {
		return homepageports.CommitResult{}, generated.AppErrorFromVersionConflict("homepage outbox event already exists")
	}
	for _, event := range s.outbox {
		if event.AggregateID == snapshot.ID && event.AggregateVersion == snapshot.Version {
			return homepageports.CommitResult{}, generated.AppErrorFromVersionConflict(
				"homepage outbox aggregate version already exists",
			)
		}
	}
	s.homepages[snapshot.ID] = snapshot
	s.outbox[commit.Event.EventID] = commit.Event
	s.receipts[receiptKey] = memoryReceipt{
		ActorID:        commit.ActorID,
		IdempotencyKey: commit.IdempotencyKey,
		CommandName:    commit.CommandName,
		CommandDigest:  commit.CommandDigest,
		Result:         snapshot,
		ExpiresAt:      normalizedExpiry(commit.ReceiptExpiresAt),
	}
	aggregate, err := homepagemodel.Restore(snapshot)
	return homepageports.CommitResult{Aggregate: aggregate}, err
}

func (s *MemoryHomepageStore) ensureUniqueLocked(
	snapshot homepagemodel.Snapshot,
	exceptID string,
) error {
	for id, existing := range s.homepages {
		if id == exceptID {
			continue
		}
		if existing.CanonicalEntityID == snapshot.CanonicalEntityID {
			return generated.AppErrorFromVersionConflict("homepage canonical identity already exists")
		}
		if snapshot.SourceOwner != "" && snapshot.SourceEntityRef != "" &&
			existing.SourceOwner == snapshot.SourceOwner &&
			existing.SourceEntityRef == snapshot.SourceEntityRef {
			return generated.AppErrorFromVersionConflict("homepage source identity already exists")
		}
	}
	return nil
}

func (s *MemoryHomepageStore) UpsertFollowerState(
	_ context.Context,
	homepageID string,
	personaID string,
	following bool,
	sourceVersion int64,
	updatedAt time.Time,
) error {
	homepageID = strings.TrimSpace(homepageID)
	personaID = strings.TrimSpace(personaID)
	if homepageID == "" || personaID == "" {
		return nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.followers[homepageID] == nil {
		s.followers[homepageID] = map[string]memoryFollower{}
	}
	if current, found := s.followers[homepageID][personaID]; found && current.SourceVersion >= sourceVersion {
		return nil
	}
	s.followers[homepageID][personaID] = memoryFollower{
		Following:     following,
		SourceVersion: sourceVersion,
		UpdatedAt:     updatedAt.UTC(),
	}
	return nil
}

func (s *MemoryHomepageStore) ResolveFollowerView(
	_ context.Context,
	homepageID string,
	viewerPersonaID string,
) (homepageports.FollowerView, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	view := homepageports.FollowerView{}
	for personaID, state := range s.followers[strings.TrimSpace(homepageID)] {
		if state.Following {
			view.Count++
			if personaID == strings.TrimSpace(viewerPersonaID) {
				view.ViewerFollows = true
			}
		}
	}
	return view, nil
}

func (s *MemoryHomepageStore) ReadAfter(
	_ context.Context,
	checkpoint string,
	limit int,
) ([]homepageports.OutboxEvent, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	ids := make([]string, 0, len(s.outbox))
	for id := range s.outbox {
		if strings.TrimSpace(checkpoint) == "" || id > strings.TrimSpace(checkpoint) {
			ids = append(ids, id)
		}
	}
	sort.Strings(ids)
	limit = boundedLimit(limit, 100, 1000)
	if len(ids) > limit {
		ids = ids[:limit]
	}
	events := make([]homepageports.OutboxEvent, 0, len(ids))
	for _, id := range ids {
		events = append(events, s.outbox[id])
	}
	return events, nil
}

func (s *MemoryHomepageStore) LoadCheckpoint(_ context.Context, consumer string) (string, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.checkpoints[strings.TrimSpace(consumer)], nil
}

func (s *MemoryHomepageStore) SaveCheckpoint(
	_ context.Context,
	consumer string,
	checkpoint string,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.checkpoints[strings.TrimSpace(consumer)] = strings.TrimSpace(checkpoint)
	return nil
}

func cloneDetailProjection(value homepageports.DetailProjection) homepageports.DetailProjection {
	result := value
	result.AverageRating = cloneFloat64Pointer(value.AverageRating)
	if value.ReviewSummary != nil {
		result.ReviewSummary = &homepagemodel.ReviewSummary{
			AverageRating: cloneFloat64Pointer(value.ReviewSummary.AverageRating),
			RatingCount:   value.ReviewSummary.RatingCount,
			HighlightTags: append([]string(nil), value.ReviewSummary.HighlightTags...),
		}
	}
	result.ContentPreview = append([]homepagemodel.ContentPreview{}, value.ContentPreview...)
	for index := range result.ContentPreview {
		result.ContentPreview[index].IntersectionReasons = cloneRawMessages(
			value.ContentPreview[index].IntersectionReasons,
		)
	}
	result.QuestionPreview = append([]homepagemodel.QuestionPreview{}, value.QuestionPreview...)
	result.RelatedGroups = append([]homepagemodel.RelatedGroup{}, value.RelatedGroups...)
	result.RelationEdges = cloneRawMessages(value.RelationEdges)
	result.AssistantContext = append(json.RawMessage(nil), value.AssistantContext...)
	return result
}

func cloneRawMessages(values []json.RawMessage) []json.RawMessage {
	result := make([]json.RawMessage, 0, len(values))
	for _, value := range values {
		result = append(result, append(json.RawMessage(nil), value...))
	}
	return result
}

func cloneFloat64Pointer(value *float64) *float64 {
	if value == nil {
		return nil
	}
	result := *value
	return &result
}
