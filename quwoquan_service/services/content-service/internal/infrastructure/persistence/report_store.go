package persistence

import (
	"context"
	"sort"
	"sync"

	reportmodel "quwoquan_service/services/content-service/internal/domain/report/model"
)

type InMemoryReportStore struct {
	mu      sync.RWMutex
	reports map[string]*reportmodel.Report
}

func NewInMemoryReportStore() *InMemoryReportStore {
	return &InMemoryReportStore{
		reports: map[string]*reportmodel.Report{},
	}
}

func (s *InMemoryReportStore) Create(_ context.Context, report *reportmodel.Report) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	cp := *report
	s.reports[report.ID] = &cp
	return nil
}

func (s *InMemoryReportStore) FindByID(_ context.Context, id string) (*reportmodel.Report, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	report, ok := s.reports[id]
	if !ok {
		return nil, false, nil
	}
	cp := *report
	return &cp, true, nil
}

func (s *InMemoryReportStore) Update(_ context.Context, report *reportmodel.Report) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	cp := *report
	s.reports[report.ID] = &cp
	return nil
}

func (s *InMemoryReportStore) List(_ context.Context, limit int) ([]*reportmodel.Report, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := make([]*reportmodel.Report, 0, len(s.reports))
	for _, report := range s.reports {
		cp := *report
		items = append(items, &cp)
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].CreatedAt.After(items[j].CreatedAt)
	})
	if limit > 0 && len(items) > limit {
		items = items[:limit]
	}
	return items, nil
}
