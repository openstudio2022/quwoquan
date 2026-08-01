package application

import (
	"context"
	"errors"
	"strings"

	taskmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/domain/model"
)

type Reader interface {
	List(context.Context, string, string, int) ([]taskmodel.Item, error)
}

type QueryFacade struct{ reader Reader }

func NewQueryFacade(reader Reader) *QueryFacade { return &QueryFacade{reader: reader} }

func (f *QueryFacade) ListTasks(ctx context.Context, accountID, status string, limit int) (taskmodel.Slice, error) {
	accountID = strings.TrimSpace(accountID)
	if accountID == "" {
		return taskmodel.Slice{}, errors.New("assistant task view requires accountId")
	}
	if limit <= 0 {
		limit = 32
	}
	if limit > 100 {
		limit = 100
	}
	if f == nil || f.reader == nil {
		return taskmodel.Slice{Items: []taskmodel.Item{}}, nil
	}
	items, err := f.reader.List(ctx, accountID, strings.TrimSpace(status), limit)
	if err != nil {
		return taskmodel.Slice{}, err
	}
	if items == nil {
		items = []taskmodel.Item{}
	}
	return taskmodel.Slice{Items: items}, nil
}
