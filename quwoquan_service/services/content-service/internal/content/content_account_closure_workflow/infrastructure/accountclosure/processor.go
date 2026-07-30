package accountclosure

import (
	"context"
	"errors"
	"fmt"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
)

const ContentPostSearchObjectType = rtsearch.ObjectTypeContentPost

type SearchDocumentID struct {
	ObjectType string
	ObjectID   string
}

// MediaArtifactCleanupWork describes opaque object-store cleanup that must
// converge before a closed account's content projection is complete. The
// values are storage keys only; account, persona, event payload, and delivery
// URLs are deliberately excluded.
type MediaArtifactCleanupWork struct {
	ID                string
	PublicSliceKeys   []string
	PublicPrefixes    []string
	PrivateObjectKeys []string
	PrivatePrefixes   []string
}

func (document SearchDocumentID) Validate() error {
	if strings.TrimSpace(document.ObjectType) == "" ||
		strings.TrimSpace(document.ObjectID) == "" {
		return errors.New("search document identity is incomplete")
	}
	return nil
}

func (document SearchDocumentID) CanonicalID() string {
	return es.IndexID(document.runtimeDocument())
}

func (document SearchDocumentID) runtimeDocument() rtsearch.Document {
	return rtsearch.Document{
		ObjectType: strings.TrimSpace(document.ObjectType),
		ObjectID:   strings.TrimSpace(document.ObjectID),
	}
}

type CleanupStore interface {
	ReserveCleanup(
		ctx context.Context,
		event UserAccountClosedEvent,
	) (CleanupState, error)
	RegisterClosedSubjects(
		ctx context.Context,
		event UserAccountClosedEvent,
	) error
	PersonalCacheKeys(
		ctx context.Context,
		event UserAccountClosedEvent,
	) ([]string, error)
	PrepareCleanup(
		ctx context.Context,
		event UserAccountClosedEvent,
	) (CleanupState, error)
	PendingSearchDocuments(
		ctx context.Context,
		eventID string,
		limit int64,
	) ([]SearchDocumentID, error)
	MarkSearchDocumentDone(
		ctx context.Context,
		eventID string,
		document SearchDocumentID,
	) error
	PendingMediaArtifactCleanup(
		ctx context.Context,
		eventID string,
		limit int64,
	) ([]MediaArtifactCleanupWork, error)
	MarkMediaArtifactCleanupDone(
		ctx context.Context,
		eventID string,
		workID string,
	) error
	MarkCompleted(
		ctx context.Context,
		event UserAccountClosedEvent,
	) error
}

type SearchDocumentDeleter interface {
	DeleteSearchDocument(
		ctx context.Context,
		document SearchDocumentID,
	) error
}

type PersonalDataCacheCleaner interface {
	BlockClosedSubjects(
		ctx context.Context,
		subjectIDs []string,
	) error
	DeletePersonalCacheKeys(
		ctx context.Context,
		keys []string,
	) error
	VerifyNoPersonalDataResidual(
		ctx context.Context,
		subjectIDs []string,
		keys []string,
	) error
}

// MediaArtifactReclaimer must physically remove every public delivery
// artifact, then remove only private candidates no longer referenced by any
// surviving MediaAsset. It must reject unsafe object namespaces rather than
// widening deletion authority.
type MediaArtifactReclaimer interface {
	ReclaimMediaArtifacts(
		ctx context.Context,
		publicSliceKeys []string,
		publicPrefixes []string,
		privateObjectKeys []string,
		privatePrefixes []string,
	) error
}

type Processor struct {
	store     CleanupStore
	cache     PersonalDataCacheCleaner
	search    SearchDocumentDeleter
	media     MediaArtifactReclaimer
	batchSize int64
}

func NewProcessor(
	store CleanupStore,
	cache PersonalDataCacheCleaner,
	search SearchDocumentDeleter,
	media MediaArtifactReclaimer,
) (*Processor, error) {
	if store == nil || cache == nil || search == nil || media == nil {
		return nil, errors.New(
			"UserAccountClosed processor requires cleanup store, cache cleaner, search deleter, and media artifact reclaimer",
		)
	}
	return &Processor{
		store:     store,
		cache:     cache,
		search:    search,
		media:     media,
		batchSize: 200,
	}, nil
}

func (processor *Processor) Apply(
	ctx context.Context,
	event UserAccountClosedEvent,
) (ApplyResult, error) {
	if processor == nil ||
		processor.store == nil ||
		processor.cache == nil ||
		processor.search == nil ||
		processor.media == nil {
		return ApplyResult{}, errors.New(
			"UserAccountClosed processor is not configured",
		)
	}
	if err := event.Validate(); err != nil {
		return ApplyResult{}, err
	}
	reservedState, err := processor.store.ReserveCleanup(ctx, event)
	if err != nil {
		return ApplyResult{}, err
	}
	if reservedState.Completed {
		return ApplyResult{Replayed: true}, nil
	}
	if err := processor.store.RegisterClosedSubjects(ctx, event); err != nil {
		return ApplyResult{}, err
	}
	if err := processor.cache.BlockClosedSubjects(
		ctx,
		event.SubjectIDs(),
	); err != nil {
		return ApplyResult{}, err
	}
	cacheKeys, err := processor.store.PersonalCacheKeys(ctx, event)
	if err != nil {
		return ApplyResult{}, err
	}
	if err := processor.cache.DeletePersonalCacheKeys(ctx, cacheKeys); err != nil {
		return ApplyResult{}, err
	}
	if err := processor.cache.VerifyNoPersonalDataResidual(
		ctx,
		event.SubjectIDs(),
		cacheKeys,
	); err != nil {
		return ApplyResult{}, err
	}
	state, err := processor.store.PrepareCleanup(ctx, event)
	if err != nil {
		return ApplyResult{}, err
	}
	if state.Completed {
		return ApplyResult{Replayed: true}, nil
	}
	replayed := state.AlreadyApplied
	for {
		if err := ctx.Err(); err != nil {
			return ApplyResult{}, err
		}
		documents, err := processor.store.PendingSearchDocuments(
			ctx,
			event.EventID,
			processor.batchSize,
		)
		if err != nil {
			return ApplyResult{}, err
		}
		if len(documents) == 0 {
			break
		}
		for _, document := range documents {
			if err := document.Validate(); err != nil {
				return ApplyResult{}, fmt.Errorf(
					"invalid UserAccountClosed search work: %w",
					err,
				)
			}
			if err := processor.search.DeleteSearchDocument(
				ctx,
				document,
			); err != nil {
				return ApplyResult{}, fmt.Errorf(
					"delete closed-account search document: %w",
					err,
				)
			}
			if err := processor.store.MarkSearchDocumentDone(
				ctx,
				event.EventID,
				document,
			); err != nil {
				return ApplyResult{}, err
			}
		}
	}
	for {
		if err := ctx.Err(); err != nil {
			return ApplyResult{}, err
		}
		workItems, err := processor.store.PendingMediaArtifactCleanup(
			ctx,
			event.EventID,
			processor.batchSize,
		)
		if err != nil {
			return ApplyResult{}, err
		}
		if len(workItems) == 0 {
			break
		}
		for _, work := range workItems {
			if err := processor.media.ReclaimMediaArtifacts(
				ctx,
				work.PublicSliceKeys,
				work.PublicPrefixes,
				work.PrivateObjectKeys,
				work.PrivatePrefixes,
			); err != nil {
				return ApplyResult{}, fmt.Errorf(
					"reclaim closed-account media artifacts: %w",
					err,
				)
			}
			if err := processor.store.MarkMediaArtifactCleanupDone(
				ctx,
				event.EventID,
				work.ID,
			); err != nil {
				return ApplyResult{}, err
			}
		}
	}
	if err := processor.store.MarkCompleted(ctx, event); err != nil {
		return ApplyResult{}, err
	}
	return ApplyResult{Replayed: replayed}, nil
}

var _ EventProcessor = (*Processor)(nil)
