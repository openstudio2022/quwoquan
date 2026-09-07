package accountclosure

import (
	"context"
	"errors"
	"fmt"

	"quwoquan_service/runtime/search/es"
)

// VersionedIndexer is the only search write surface the closure workflow may
// use: a closed account's documents are removed with versioned tombstones, never
// with a physical DELETE that a replayed write-time projection could resurrect
// (DEC-002). *es.Indexer satisfies it.
type VersionedIndexer interface {
	ApplyVersioned(context.Context, es.VersionedChangeEvent) (bool, error)
}

type SearchIndexerDeleter struct {
	indexer VersionedIndexer
	enabled bool
}

func NewSearchIndexerDeleter(
	indexer VersionedIndexer,
	enabled bool,
) (*SearchIndexerDeleter, error) {
	if enabled && indexer == nil {
		return nil, errors.New(
			"UserAccountClosed search deletion is enabled but indexer is unavailable",
		)
	}
	return &SearchIndexerDeleter{
		indexer: indexer,
		enabled: enabled,
	}, nil
}

// DeleteSearchDocument writes the staged tombstone under the SourceVersion
// captured with the Post hard-delete. A stale/replayed tombstone (applied=false)
// is a success: the index already holds an equal or newer terminal state.
func (deleter *SearchIndexerDeleter) DeleteSearchDocument(
	ctx context.Context,
	document SearchDocumentID,
) error {
	if deleter == nil {
		return errors.New("UserAccountClosed search deleter is not configured")
	}
	if err := document.Validate(); err != nil {
		return err
	}
	if !deleter.enabled {
		return nil
	}
	if deleter.indexer == nil {
		return errors.New("UserAccountClosed search indexer is unavailable")
	}
	if _, err := deleter.indexer.ApplyVersioned(ctx, es.VersionedChangeEvent{
		Op:            es.OpDelete,
		Doc:           document.runtimeDocument(),
		SourceVersion: document.SourceVersion,
	}); err != nil {
		return fmt.Errorf("tombstone canonical search document: %w", err)
	}
	return nil
}

var _ SearchDocumentDeleter = (*SearchIndexerDeleter)(nil)
