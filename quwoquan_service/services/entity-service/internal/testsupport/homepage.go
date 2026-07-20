// Package testsupport 装配 entity-service local_contract/api_integration 专用适配器。
// production composition 不得 import 本包。
package testsupport

import (
	"context"
	"fmt"
	"sort"
	"sync"
	"time"

	"quwoquan_service/services/entity-service/internal/application"
	claimapp "quwoquan_service/services/entity-service/internal/application/homepage_claim_request"
	statusapp "quwoquan_service/services/entity-service/internal/application/homepage_status_report"
	claimmodel "quwoquan_service/services/entity-service/internal/domain/homepage_claim_request/model"
	statusmodel "quwoquan_service/services/entity-service/internal/domain/homepage_status_report/model"
	homepagepersistence "quwoquan_service/services/entity-service/internal/infrastructure/homepage/persistence"
)

func NewFixtureHomepageService() *application.HomepageService {
	return NewFixtureHomepageServiceWithOptions()
}

func NewFixtureHomepageServiceWithOptions(
	options ...application.HomepageServiceOption,
) *application.HomepageService {
	seeds, err := application.LoadHomepageFixtureSnapshots()
	if err != nil {
		panic(err)
	}
	store, err := homepagepersistence.NewMemoryHomepageStore(seeds...)
	if err != nil {
		panic(err)
	}
	options = append([]application.HomepageServiceOption{
		application.WithClaimFacade(newMemoryClaimFacade()),
		application.WithStatusReportFacade(newMemoryStatusFacade()),
	}, options...)
	return application.NewHomepageServiceWithStore(
		context.Background(),
		store,
		options...,
	)
}

func NewEmptyHomepageService() (*application.HomepageService, *homepagepersistence.MemoryHomepageStore) {
	store, err := homepagepersistence.NewMemoryHomepageStore()
	if err != nil {
		panic(err)
	}
	return application.NewHomepageServiceWithStore(
		context.Background(),
		store,
		application.WithClaimFacade(newMemoryClaimFacade()),
		application.WithStatusReportFacade(newMemoryStatusFacade()),
	), store
}

type memoryClaimFacade struct {
	mu     sync.Mutex
	next   int
	claims map[string]claimapp.ClaimRequestView
}

func newMemoryClaimFacade() *memoryClaimFacade {
	return &memoryClaimFacade{claims: map[string]claimapp.ClaimRequestView{}}
}

func (f *memoryClaimFacade) Create(
	_ context.Context,
	command claimapp.CreateCommand,
) (claimapp.ClaimRequestView, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.next++
	now := time.Now().UTC()
	id := fmt.Sprintf("hcr_test_%d", f.next)
	view := claimapp.ClaimRequestView{
		ClaimRequestID: id, Version: 1, HomepageID: command.HomepageID,
		RequesterPersonaID: command.ActorPersonaID, ClaimTier: command.ClaimTier,
		BusinessLicenseURL: command.BusinessLicenseURL, ContactPhone: command.ContactPhone,
		IdentityCardFrontURL: command.IdentityCardFrontURL,
		IdentityCardBackURL:  command.IdentityCardBackURL, Note: command.Note,
		Status: claimmodel.StatusPendingReview, CreatedAt: now, UpdatedAt: now,
	}
	f.claims[id] = view
	return view, nil
}

func (f *memoryClaimFacade) Review(
	_ context.Context,
	command claimapp.ReviewCommand,
) (claimapp.ClaimRequestView, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	view, found := f.claims[command.ClaimRequestID]
	if !found {
		return claimapp.ClaimRequestView{}, fmt.Errorf("claim not found")
	}
	now := time.Now().UTC()
	view.Version++
	view.Status = command.TargetStatus
	view.ReviewerAccountID = command.ActorAccountID
	view.ReviewNote = command.ReviewNote
	view.UpdatedAt = now
	view.ReviewedAt = &now
	f.claims[view.ClaimRequestID] = view
	return view, nil
}

func (f *memoryClaimFacade) ListQueue(
	_ context.Context,
	query claimapp.QueueQuery,
) (claimapp.ClaimRequestSlice, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	items := make([]claimapp.ClaimRequestView, 0, len(f.claims))
	for _, view := range f.claims {
		if query.HomepageID != "" && view.HomepageID != query.HomepageID {
			continue
		}
		if query.Status != "" && view.Status != query.Status {
			continue
		}
		items = append(items, view)
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].CreatedAt.Equal(items[j].CreatedAt) {
			return items[i].ClaimRequestID > items[j].ClaimRequestID
		}
		return items[i].CreatedAt.After(items[j].CreatedAt)
	})
	if query.Limit > 0 && query.Limit < len(items) {
		items = items[:query.Limit]
	}
	return claimapp.ClaimRequestSlice{Items: items}, nil
}

type memoryStatusFacade struct {
	mu      sync.Mutex
	next    int
	reports map[string]statusapp.StatusReportView
}

func newMemoryStatusFacade() *memoryStatusFacade {
	return &memoryStatusFacade{reports: map[string]statusapp.StatusReportView{}}
}

func (f *memoryStatusFacade) Create(
	_ context.Context,
	command statusapp.CreateCommand,
) (statusapp.StatusReportView, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.next++
	now := time.Now().UTC()
	id := fmt.Sprintf("hsr_test_%d", f.next)
	view := statusapp.StatusReportView{
		ReportID: id, Version: 1, HomepageID: command.HomepageID,
		ReporterPersonaID: command.ActorPersonaID, Reason: command.Reason,
		Description: command.Description, EvidenceURLs: command.EvidenceURLs,
		Status: statusmodel.StatusPendingReview, CreatedAt: now, UpdatedAt: now,
	}
	f.reports[id] = view
	return view, nil
}

func (f *memoryStatusFacade) Review(
	_ context.Context,
	command statusapp.ReviewCommand,
) (statusapp.StatusReportView, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	view, found := f.reports[command.ReportID]
	if !found {
		return statusapp.StatusReportView{}, fmt.Errorf("report not found")
	}
	now := time.Now().UTC()
	view.Version++
	view.Status = command.TargetStatus
	view.ReviewerAccountID = command.ActorAccountID
	view.ReviewNote = command.ReviewNote
	view.UpdatedAt = now
	view.ReviewedAt = &now
	f.reports[view.ReportID] = view
	return view, nil
}

func (f *memoryStatusFacade) ListQueue(
	_ context.Context,
	query statusapp.QueueQuery,
) (statusapp.StatusReportSlice, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	items := make([]statusapp.StatusReportView, 0, len(f.reports))
	for _, view := range f.reports {
		if query.HomepageID != "" && view.HomepageID != query.HomepageID {
			continue
		}
		if query.Status != "" && view.Status != query.Status {
			continue
		}
		items = append(items, view)
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].CreatedAt.Equal(items[j].CreatedAt) {
			return items[i].ReportID > items[j].ReportID
		}
		return items[i].CreatedAt.After(items[j].CreatedAt)
	})
	if query.Limit > 0 && query.Limit < len(items) {
		items = items[:query.Limit]
	}
	return statusapp.StatusReportSlice{Items: items}, nil
}
