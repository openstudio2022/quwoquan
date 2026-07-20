package application_test

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	application "quwoquan_service/services/entity-service/internal/application"
	claimapp "quwoquan_service/services/entity-service/internal/application/homepage_claim_request"
	statusapp "quwoquan_service/services/entity-service/internal/application/homepage_status_report"
	claimmodel "quwoquan_service/services/entity-service/internal/domain/homepage_claim_request/model"
	claimports "quwoquan_service/services/entity-service/internal/domain/homepage_claim_request/ports"
	statusmodel "quwoquan_service/services/entity-service/internal/domain/homepage_status_report/model"
	statusports "quwoquan_service/services/entity-service/internal/domain/homepage_status_report/ports"
	homepagepersistence "quwoquan_service/services/entity-service/internal/infrastructure/homepage/persistence"
)

func TestClaimAndStatusOutboxProjectorsConvergeHomepage(t *testing.T) {
	ctx := context.Background()
	seeds, err := application.LoadHomepageFixtureSnapshots()
	if err != nil || len(seeds) == 0 {
		t.Fatalf("load homepage fixtures: count=%d err=%v", len(seeds), err)
	}
	store, err := homepagepersistence.NewMemoryHomepageStore(seeds...)
	if err != nil {
		t.Fatalf("new homepage store: %v", err)
	}
	homepages := application.NewHomepageServiceWithStore(ctx, store)
	homepageID := seeds[0].ID
	now := time.Date(2026, 7, 20, 1, 0, 0, 0, time.UTC)

	claim, err := claimmodel.Create(claimmodel.CreateParams{
		ID:                 "hcr-projector-1",
		HomepageID:         homepageID,
		RequesterPersonaID: "persona-owner",
		ClaimTier:          claimmodel.ClaimTierBasic,
		BusinessLicenseURL: "https://assets.test/license.jpg",
		ContactPhone:       "13800000000",
		Now:                now,
	})
	if err != nil {
		t.Fatalf("create claim: %v", err)
	}
	if err := claim.Review(claimmodel.ReviewParams{
		ReviewerAccountID: "reviewer-account",
		TargetStatus:      claimmodel.StatusApproved,
		Now:               now.Add(time.Second),
	}); err != nil {
		t.Fatalf("review claim: %v", err)
	}
	claimSource := &claimProjectorSource{
		aggregate: claim,
		events: []claimports.OutboxEvent{
			{
				EventID: "claim-event-1", EventType: claimapp.EventClaimRequested,
				AggregateID: claim.ID(), AggregateVersion: 1,
				Payload: mustJSON(t, map[string]any{
					"claimRequestId": claim.ID(),
					"homepageId":     homepageID,
				}),
				OccurredAt: now,
			},
			{
				EventID: "claim-event-2", EventType: claimapp.EventClaimReviewed,
				AggregateID: claim.ID(), AggregateVersion: claim.Version(),
				Payload: mustJSON(t, map[string]any{
					"claimRequestId": claim.ID(),
					"homepageId":     homepageID,
					"status":         string(claimmodel.StatusApproved),
				}),
				OccurredAt: now.Add(time.Second),
			},
		},
	}
	claimProjector, err := application.NewClaimHomepageProjector(claimSource, homepages)
	if err != nil {
		t.Fatalf("new claim projector: %v", err)
	}
	processed, err := claimProjector.RunOnce(ctx, 10)
	if err != nil || processed != 2 {
		t.Fatalf("project claim events: processed=%d err=%v", processed, err)
	}
	homepage, err := homepages.GetHomepage(ctx, homepageID)
	if err != nil {
		t.Fatalf("get claimed homepage: %v", err)
	}
	if homepage.ClaimStatus != "claimed" ||
		homepage.OwnerSubAccountID != "persona-owner" {
		t.Fatalf(
			"claim projection mismatch: status=%s owner=%s",
			homepage.ClaimStatus,
			homepage.OwnerSubAccountID,
		)
	}
	if replayed, err := claimProjector.RunOnce(ctx, 10); err != nil || replayed != 0 {
		t.Fatalf("claim projector replay: processed=%d err=%v", replayed, err)
	}

	statusSource := &statusProjectorSource{
		events: []statusports.OutboxEvent{
			{
				EventID:     "status-event-1",
				EventType:   statusapp.EventStatusReportReviewed,
				AggregateID: "hsr-projector-1", AggregateVersion: 2,
				Payload: mustJSON(t, map[string]any{
					"reportId":   "hsr-projector-1",
					"homepageId": homepageID,
					"status":     string(statusmodel.StatusConfirmedOffline),
				}),
				OccurredAt: now.Add(2 * time.Second),
			},
		},
	}
	statusProjector, err := application.NewStatusHomepageProjector(statusSource, homepages)
	if err != nil {
		t.Fatalf("new status projector: %v", err)
	}
	if processed, err := statusProjector.RunOnce(ctx, 10); err != nil || processed != 1 {
		t.Fatalf("project status event: processed=%d err=%v", processed, err)
	}
	status, found, err := homepages.FindHomepageStatus(ctx, homepageID)
	if err != nil || !found || status != "offline" {
		t.Fatalf("offline projection mismatch: status=%s found=%v err=%v", status, found, err)
	}
}

func TestHomepageOutboxRelayProjectsCommittedState(t *testing.T) {
	ctx := context.Background()
	store, err := homepagepersistence.NewMemoryHomepageStore()
	if err != nil {
		t.Fatalf("new homepage store: %v", err)
	}
	service := application.NewHomepageServiceWithStore(ctx, store)
	created, err := service.SuggestHomepageCandidate(ctx, application.HomepageInput{
		Title:        "对象化主页",
		HomepageType: "sight",
		City:         "杭州",
	})
	if err != nil {
		t.Fatalf("suggest homepage: %v", err)
	}
	projector := &searchProjectorCapture{}
	relay, err := application.NewHomepageSearchRelay(store, projector)
	if err != nil {
		t.Fatalf("new search relay: %v", err)
	}
	processed, err := relay.RunOnce(ctx, 10)
	if err != nil || processed != 1 {
		t.Fatalf("run search relay: processed=%d err=%v", processed, err)
	}
	if projector.event.HomepageID != created.ID ||
		projector.event.Type != application.ProjectorEventHomepageUpserted {
		t.Fatalf("search projection mismatch: %+v", projector.event)
	}
	if replayed, err := relay.RunOnce(ctx, 10); err != nil || replayed != 0 {
		t.Fatalf("search relay replay mismatch: processed=%d err=%v", replayed, err)
	}
}

type claimProjectorSource struct {
	aggregate  *claimmodel.HomepageClaimRequest
	events     []claimports.OutboxEvent
	checkpoint string
}

func (s *claimProjectorSource) Load(
	_ context.Context,
	id string,
) (*claimmodel.HomepageClaimRequest, bool, error) {
	if s.aggregate == nil || s.aggregate.ID() != id {
		return nil, false, nil
	}
	restored, err := claimmodel.Restore(s.aggregate.Snapshot())
	return restored, err == nil, err
}

func (s *claimProjectorSource) FindPending(
	context.Context,
	string,
	string,
) (*claimmodel.HomepageClaimRequest, bool, error) {
	return nil, false, nil
}

func (s *claimProjectorSource) Commit(
	context.Context,
	claimports.Commit,
) (claimports.CommitResult, error) {
	return claimports.CommitResult{}, nil
}

func (s *claimProjectorSource) ReadAfter(
	_ context.Context,
	checkpoint string,
	_ int,
) ([]claimports.OutboxEvent, error) {
	if checkpoint == "" {
		return append([]claimports.OutboxEvent(nil), s.events...), nil
	}
	return []claimports.OutboxEvent{}, nil
}

func (s *claimProjectorSource) LoadCheckpoint(
	context.Context,
	string,
) (string, error) {
	return s.checkpoint, nil
}

func (s *claimProjectorSource) SaveCheckpoint(
	_ context.Context,
	_ string,
	checkpoint string,
) error {
	s.checkpoint = checkpoint
	return nil
}

type statusProjectorSource struct {
	events     []statusports.OutboxEvent
	checkpoint string
}

func (s *statusProjectorSource) ReadAfter(
	_ context.Context,
	checkpoint string,
	_ int,
) ([]statusports.OutboxEvent, error) {
	if checkpoint == "" {
		return append([]statusports.OutboxEvent(nil), s.events...), nil
	}
	return []statusports.OutboxEvent{}, nil
}

func (s *statusProjectorSource) LoadCheckpoint(
	context.Context,
	string,
) (string, error) {
	return s.checkpoint, nil
}

func (s *statusProjectorSource) SaveCheckpoint(
	_ context.Context,
	_ string,
	checkpoint string,
) error {
	s.checkpoint = checkpoint
	return nil
}

func mustJSON(t *testing.T, value any) []byte {
	t.Helper()
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return encoded
}

type searchProjectorCapture struct {
	event application.ProjectorEvent
}

func (p *searchProjectorCapture) Project(
	_ context.Context,
	event application.ProjectorEvent,
) error {
	p.event = event
	return nil
}
