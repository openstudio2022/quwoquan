package accountclosure

import (
	"context"
	"errors"
	"fmt"

	"quwoquan_service/runtime/search/es"
)

type SearchIndexerDeleter struct {
	indexer *es.Indexer
	enabled bool
}

func NewSearchIndexerDeleter(
	indexer *es.Indexer,
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
	if err := deleter.indexer.Apply(ctx, es.ChangeEvent{
		Op:  es.OpDelete,
		Doc: document.runtimeDocument(),
	}); err != nil {
		return fmt.Errorf("delete canonical search document: %w", err)
	}
	return nil
}

var _ SearchDocumentDeleter = (*SearchIndexerDeleter)(nil)
