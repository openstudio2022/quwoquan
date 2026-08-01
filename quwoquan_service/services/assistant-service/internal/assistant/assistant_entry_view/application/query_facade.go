package application

import (
	"context"
	"errors"
	"strings"

	entrymodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/domain/model"
)

type Reader interface {
	Get(context.Context, string) (*entrymodel.View, error)
}

type QueryFacade struct{ reader Reader }

func NewQueryFacade(reader Reader) *QueryFacade { return &QueryFacade{reader: reader} }

func (f *QueryFacade) GetEntry(ctx context.Context, accountID string) (entrymodel.View, error) {
	accountID = strings.TrimSpace(accountID)
	if accountID == "" {
		return entrymodel.View{}, errors.New("assistant entry requires accountId")
	}
	if f == nil || f.reader == nil {
		return entrymodel.Empty(), nil
	}
	view, err := f.reader.Get(ctx, accountID)
	if err != nil {
		return entrymodel.View{}, err
	}
	if view == nil {
		return entrymodel.Empty(), nil
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
	return *view, nil
}
