package application

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	turnviewmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/domain/model"
)

const projectionPageSize = 200

type TerminalRunSource interface {
	ListTerminalRunsAfter(context.Context, time.Time, string, int) ([]runruntime.TerminalRunRecord, error)
}

type ProjectionStore interface {
	LoadCheckpoint(context.Context) (turnviewmodel.Checkpoint, error)
	Apply(context.Context, turnviewmodel.Projection, turnviewmodel.Checkpoint) error
}

type Synchronizer interface {
	CatchUp(context.Context) error
}

type Projector struct {
	source TerminalRunSource
	store  ProjectionStore
}

func NewProjector(source TerminalRunSource, store ProjectionStore) *Projector {
	if source == nil || store == nil {
		panic("assistant turn view projector dependencies are required")
	}
	return &Projector{source: source, store: store}
}

func (p *Projector) CatchUp(ctx context.Context) error {
	checkpoint, err := p.store.LoadCheckpoint(ctx)
	if err != nil {
		return err
	}
	for {
		records, err := p.source.ListTerminalRunsAfter(
			ctx,
			checkpoint.SourceUpdatedAt,
			checkpoint.SourceRunID,
			projectionPageSize,
		)
		if err != nil {
			return err
		}
		for _, record := range records {
			projection, err := terminalProjection(record)
			if err != nil {
				return err
			}
			checkpoint = turnviewmodel.Checkpoint{
				SourceUpdatedAt: record.SourceUpdatedAt,
				SourceRunID:     record.SourceRunID,
			}
			if err := p.store.Apply(ctx, projection, checkpoint); err != nil {
				return err
			}
		}
		if len(records) < projectionPageSize {
			return nil
		}
	}
}

func terminalProjection(
	record runruntime.TerminalRunRecord,
) (turnviewmodel.Projection, error) {
	run := record.Run
	var terminalSnapshot *turnviewmodel.TerminalSnapshotView
	if len(run.TerminalSnapshot) > 0 {
		encoded, err := json.Marshal(run.TerminalSnapshot)
		if err != nil {
			return turnviewmodel.Projection{}, fmt.Errorf("encode assistant run terminal snapshot: %w", err)
		}
		var decoded turnviewmodel.TerminalSnapshotView
		if err := json.Unmarshal(encoded, &decoded); err != nil {
			return turnviewmodel.Projection{}, fmt.Errorf("decode assistant run terminal snapshot: %w", err)
		}
		terminalSnapshot = &decoded
	}
	return turnviewmodel.Projection{
		TurnID:           run.RunID,
		UserID:           run.UserID,
		SessionID:        run.SessionID,
		Status:           run.State.WireName(),
		InputText:        run.InputText,
		TerminalSnapshot: terminalSnapshot,
		SkillID:          run.RequestedSkillID,
		DomainID:         run.RequestedDomainID,
		CreatedAt:        run.CreatedAt.UTC(),
		CompletedAt:      run.CompletedAt,
		SourceRevision:   run.Revision,
		SourceUpdatedAt:  record.SourceUpdatedAt.UTC(),
	}, nil
}
