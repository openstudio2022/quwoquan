package application

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	claimapp "quwoquan_service/services/entity-service/internal/application/homepage_claim_request"
	statusapp "quwoquan_service/services/entity-service/internal/application/homepage_status_report"
	claimmodel "quwoquan_service/services/entity-service/internal/domain/homepage_claim_request/model"
	claimports "quwoquan_service/services/entity-service/internal/domain/homepage_claim_request/ports"
	statusmodel "quwoquan_service/services/entity-service/internal/domain/homepage_status_report/model"
	statusports "quwoquan_service/services/entity-service/internal/domain/homepage_status_report/ports"
)

const (
	claimHomepageConsumer  = "entity.homepage-claim-lifecycle"
	statusHomepageConsumer = "entity.homepage-status-lifecycle"
)

type ClaimLifecycleSource interface {
	claimports.AggregateStore
	claimports.OutboxReader
	claimports.ProjectionCheckpointStore
}

type ClaimHomepageProjector struct {
	source    ClaimLifecycleSource
	homepages *HomepageService
}

func NewClaimHomepageProjector(
	source ClaimLifecycleSource,
	homepages *HomepageService,
) (*ClaimHomepageProjector, error) {
	if source == nil || homepages == nil {
		return nil, fmt.Errorf("claim homepage projector requires source and homepage service")
	}
	return &ClaimHomepageProjector{source: source, homepages: homepages}, nil
}

func (p *ClaimHomepageProjector) RunOnce(
	ctx context.Context,
	limit int,
) (int, error) {
	checkpoint, err := p.source.LoadCheckpoint(ctx, claimHomepageConsumer)
	if err != nil {
		return 0, err
	}
	events, err := p.source.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, err
	}
	processed := 0
	for _, event := range events {
		if err := p.project(ctx, event); err != nil {
			return processed, err
		}
		if err := p.source.SaveCheckpoint(
			ctx,
			claimHomepageConsumer,
			event.EventID,
		); err != nil {
			return processed, err
		}
		processed++
	}
	return processed, nil
}

func (p *ClaimHomepageProjector) project(
	ctx context.Context,
	event claimports.OutboxEvent,
) error {
	switch event.EventType {
	case claimapp.EventClaimRequested:
		var payload struct {
			HomepageID string `json:"homepageId"`
		}
		if err := json.Unmarshal(event.Payload, &payload); err != nil {
			return fmt.Errorf("decode claim requested payload: %w", err)
		}
		if strings.TrimSpace(payload.HomepageID) == "" {
			return fmt.Errorf("claim requested payload has empty homepageId")
		}
		return p.homepages.ApplyClaimRequestedProjection(
			ctx,
			event.EventID,
			payload.HomepageID,
		)
	case claimapp.EventClaimReviewed:
		claim, found, err := p.source.Load(ctx, event.AggregateID)
		if err != nil {
			return err
		}
		if !found {
			return fmt.Errorf("claim aggregate %s not found for projection", event.AggregateID)
		}
		snapshot := claim.Snapshot()
		if snapshot.Status != claimmodel.StatusApproved &&
			snapshot.Status != claimmodel.StatusRejected {
			return fmt.Errorf(
				"claim aggregate %s is not terminal: %s",
				event.AggregateID,
				snapshot.Status,
			)
		}
		return p.homepages.ApplyClaimReviewedProjection(
			ctx,
			event.EventID,
			snapshot.HomepageID,
			snapshot.RequesterPersonaID,
			snapshot.Status == claimmodel.StatusApproved,
		)
	default:
		return fmt.Errorf("unsupported claim outbox event %q", event.EventType)
	}
}

type StatusLifecycleSource interface {
	statusports.OutboxReader
	statusports.ProjectionCheckpointStore
}

type StatusHomepageProjector struct {
	source    StatusLifecycleSource
	homepages *HomepageService
}

func NewStatusHomepageProjector(
	source StatusLifecycleSource,
	homepages *HomepageService,
) (*StatusHomepageProjector, error) {
	if source == nil || homepages == nil {
		return nil, fmt.Errorf("status homepage projector requires source and homepage service")
	}
	return &StatusHomepageProjector{source: source, homepages: homepages}, nil
}

func (p *StatusHomepageProjector) RunOnce(
	ctx context.Context,
	limit int,
) (int, error) {
	checkpoint, err := p.source.LoadCheckpoint(ctx, statusHomepageConsumer)
	if err != nil {
		return 0, err
	}
	events, err := p.source.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, err
	}
	processed := 0
	for _, event := range events {
		if err := p.project(ctx, event); err != nil {
			return processed, err
		}
		if err := p.source.SaveCheckpoint(
			ctx,
			statusHomepageConsumer,
			event.EventID,
		); err != nil {
			return processed, err
		}
		processed++
	}
	return processed, nil
}

func (p *StatusHomepageProjector) project(
	ctx context.Context,
	event statusports.OutboxEvent,
) error {
	switch event.EventType {
	case statusapp.EventStatusReported:
		return nil
	case statusapp.EventStatusReportReviewed:
		var payload struct {
			HomepageID string             `json:"homepageId"`
			Status     statusmodel.Status `json:"status"`
		}
		if err := json.Unmarshal(event.Payload, &payload); err != nil {
			return fmt.Errorf("decode status report reviewed payload: %w", err)
		}
		if payload.Status != statusmodel.StatusConfirmedOffline {
			return nil
		}
		if strings.TrimSpace(payload.HomepageID) == "" {
			return fmt.Errorf("status report reviewed payload has empty homepageId")
		}
		return p.homepages.ApplyStatusReviewedProjection(
			ctx,
			event.EventID,
			payload.HomepageID,
		)
	default:
		return fmt.Errorf("unsupported status report outbox event %q", event.EventType)
	}
}
