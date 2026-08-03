package application

import (
	"context"
	"errors"
	"strings"

	entrymodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/domain/model"
	pagecontextmodel "quwoquan_service/services/assistant-service/internal/assistant/page_context/domain/model"
)

var ErrInvalidPageContext = errors.New("assistant entry page context is invalid")

type Reader interface {
	Get(context.Context, string) (*entrymodel.View, error)
}

type PageContextReader interface {
	Current(context.Context, string) (*pagecontextmodel.PageContext, error)
}

type QueryFacade struct {
	reader   Reader
	contexts PageContextReader
}

func NewQueryFacade(reader Reader, contexts PageContextReader) *QueryFacade {
	return &QueryFacade{reader: reader, contexts: contexts}
}

func (f *QueryFacade) GetEntry(
	ctx context.Context,
	accountID string,
	pageType string,
	objectID string,
) (entrymodel.View, error) {
	accountID = strings.TrimSpace(accountID)
	pageType = strings.TrimSpace(pageType)
	objectID = strings.TrimSpace(objectID)
	if accountID == "" {
		return entrymodel.View{}, errors.New("assistant entry requires accountId")
	}
	view := entrymodel.Empty()
	if f != nil && f.reader != nil {
		stored, err := f.reader.Get(ctx, accountID)
		if err != nil {
			return entrymodel.View{}, err
		}
		if stored != nil {
			view = *stored
		}
	}
	if pageType != "" || objectID != "" {
		if f == nil || f.contexts == nil {
			return entrymodel.View{}, ErrInvalidPageContext
		}
		current, err := f.contexts.Current(ctx, accountID)
		if err != nil {
			return entrymodel.View{}, err
		}
		if current == nil || strings.TrimSpace(current.Snapshot.PageType) != pageType {
			return entrymodel.View{}, ErrInvalidPageContext
		}
		if objectID != "" && !containsPageObject(current.Snapshot.PageObjects, objectID) {
			return entrymodel.View{}, ErrInvalidPageContext
		}
		view.Actions = entrymodel.ActionsForPage(pageType, objectID)
	}
	if view.SuggestionLines == nil {
		view.SuggestionLines = []string{}
	}
	if view.Chips == nil {
		view.Chips = []entrymodel.Chip{}
	}
	if view.Actions == nil {
		view.Actions = []entrymodel.Action{}
	}
	return view, nil
}

func containsPageObject(objects []pagecontextmodel.ObjectRef, objectID string) bool {
	for _, object := range objects {
		if strings.TrimSpace(object.ObjectID) == objectID {
			return true
		}
	}
	return false
}
