package filtercatalogrelease

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/content-service/internal/media/filter_catalog_release/domain/model"
	filtercatalogports "quwoquan_service/services/content-service/internal/media/filter_catalog_release/domain/ports"
)

const commandReceiptTTL = 24 * time.Hour

type Service struct {
	store       filtercatalogports.AggregateStore
	reader      filtercatalogports.ActiveFilterCatalogReader
	invalidator filtercatalogports.ActiveFilterCatalogInvalidator
	observer    Observer
	now         func() time.Time
}

func NewService(
	store filtercatalogports.AggregateStore,
	reader filtercatalogports.ActiveFilterCatalogReader,
	options ...ServiceOption,
) (*Service, error) {
	if store == nil {
		return nil, errors.New("FilterCatalogRelease aggregate store is required")
	}
	if reader == nil {
		return nil, errors.New("ActiveFilterCatalogReader is required")
	}
	service := &Service{
		store:    store,
		reader:   reader,
		observer: noopObserver{},
		now:      time.Now,
	}
	for _, option := range options {
		option(service)
	}
	return service, nil
}

func (service *Service) Stage(
	ctx context.Context,
	command StageFilterCatalogReleaseCommand,
) (result FilterCatalogReleaseCommandResult, err error) {
	startedAt := time.Now()
	defer func() {
		service.observer.Observe(
			OperationStage,
			filterCatalogOutcome(err),
			result.Replayed,
			time.Since(startedAt),
		)
	}()

	idempotencyKey, err := requiredFilterCatalogIdempotencyKey(ctx)
	if err != nil {
		return FilterCatalogReleaseCommandResult{}, err
	}
	now := service.now()
	release, err := model.NewStaged(model.NewStagedParams{
		ReleaseID:                    command.ReleaseID,
		SourceOwner:                  command.SourceOwner,
		CanonicalDigest:              command.CanonicalDigest,
		Categories:                   command.Categories,
		Presets:                      command.Presets,
		RecommendedFallbackPresetIDs: command.RecommendedFallbackPresetIDs,
		ImportedAt:                   now,
	})
	if err != nil {
		return FilterCatalogReleaseCommandResult{}, err
	}
	digest, err := stageCommandDigest(release.Snapshot())
	if err != nil {
		return FilterCatalogReleaseCommandResult{}, filterCatalogStorageError(err)
	}
	committed, err := service.store.Stage(ctx, filtercatalogports.StageCommit{
		Release:          release,
		IdempotencyKey:   idempotencyKey,
		CommandDigest:    digest,
		ReceiptExpiresAt: now.Add(commandReceiptTTL),
	})
	if err != nil {
		return FilterCatalogReleaseCommandResult{}, filterCatalogStorageError(err)
	}
	return filterCatalogCommandResult(committed), nil
}

func (service *Service) Activate(
	ctx context.Context,
	command ActivateFilterCatalogReleaseCommand,
) (result FilterCatalogReleaseCommandResult, err error) {
	startedAt := time.Now()
	defer func() {
		service.observer.Observe(
			OperationActivate,
			filterCatalogOutcome(err),
			result.Replayed,
			time.Since(startedAt),
		)
	}()
	result, err = service.transition(
		ctx,
		OperationActivate,
		strings.TrimSpace(command.ReleaseID),
	)
	return result, err
}

func (service *Service) Rollback(
	ctx context.Context,
	command RollbackFilterCatalogReleaseCommand,
) (result FilterCatalogReleaseCommandResult, err error) {
	startedAt := time.Now()
	defer func() {
		service.observer.Observe(
			OperationRollback,
			filterCatalogOutcome(err),
			result.Replayed,
			time.Since(startedAt),
		)
	}()
	result, err = service.transition(
		ctx,
		OperationRollback,
		strings.TrimSpace(command.ReleaseID),
	)
	return result, err
}

func (service *Service) GetActiveFilterCatalog(
	ctx context.Context,
) (result FilterCatalogSlice, err error) {
	startedAt := time.Now()
	defer func() {
		service.observer.Observe(
			OperationGet,
			filterCatalogOutcome(err),
			false,
			time.Since(startedAt),
		)
	}()
	release, found, err := service.reader.GetActive(ctx)
	if err != nil {
		return FilterCatalogSlice{}, filterCatalogStorageError(err)
	}
	if !found {
		return FilterCatalogSlice{}, model.ErrCatalogUnavailable
	}
	return filterCatalogSlice(release), nil
}

func (service *Service) transition(
	ctx context.Context,
	operation string,
	releaseID string,
) (FilterCatalogReleaseCommandResult, error) {
	if releaseID == "" {
		return FilterCatalogReleaseCommandResult{}, fmt.Errorf(
			"%w: releaseId is required",
			model.ErrInvalidArgument,
		)
	}
	idempotencyKey, err := requiredFilterCatalogIdempotencyKey(ctx)
	if err != nil {
		return FilterCatalogReleaseCommandResult{}, err
	}
	digest, err := transitionCommandDigest(operation, releaseID)
	if err != nil {
		return FilterCatalogReleaseCommandResult{}, filterCatalogStorageError(err)
	}
	now := service.now()
	commit := filtercatalogports.TransitionCommit{
		ReleaseID:        releaseID,
		IdempotencyKey:   idempotencyKey,
		CommandDigest:    digest,
		TransitionedAt:   now,
		ReceiptExpiresAt: now.Add(commandReceiptTTL),
	}
	var committed filtercatalogports.CommandResult
	switch operation {
	case OperationActivate:
		committed, err = service.store.Activate(ctx, commit)
	case OperationRollback:
		committed, err = service.store.Rollback(ctx, commit)
	default:
		err = fmt.Errorf("unsupported filter catalog transition %q", operation)
	}
	if err != nil {
		return FilterCatalogReleaseCommandResult{}, filterCatalogStorageError(err)
	}
	result := filterCatalogCommandResult(committed)
	if service.invalidator != nil {
		if invalidateErr := service.invalidator.InvalidateActive(ctx); invalidateErr != nil {
			return result, filterCatalogStorageError(invalidateErr)
		}
	}
	return result, nil
}

func requiredFilterCatalogIdempotencyKey(ctx context.Context) (string, error) {
	key := idempotencyKey(ctx)
	if key == "" {
		return "", fmt.Errorf(
			"%w: Idempotency-Key is required",
			model.ErrIdempotencyConflict,
		)
	}
	return key, nil
}

func stageCommandDigest(snapshot model.Snapshot) (string, error) {
	return hashFilterCatalogCommand(struct {
		Command                      string                           `json:"command"`
		ReleaseID                    string                           `json:"releaseId"`
		SourceOwner                  string                           `json:"sourceOwner"`
		CanonicalDigest              string                           `json:"canonicalDigest"`
		Categories                   []model.FilterCategoryDefinition `json:"categories"`
		Presets                      []model.FilterPresetDefinition   `json:"presets"`
		RecommendedFallbackPresetIDs []string                         `json:"recommendedFallbackPresetIds"`
	}{
		Command:                      filtercatalogports.CommandStageFilterCatalogRelease,
		ReleaseID:                    snapshot.ReleaseID,
		SourceOwner:                  snapshot.SourceOwner,
		CanonicalDigest:              snapshot.CanonicalDigest,
		Categories:                   snapshot.Categories,
		Presets:                      snapshot.Presets,
		RecommendedFallbackPresetIDs: snapshot.RecommendedFallbackPresetIDs,
	})
}

func transitionCommandDigest(operation string, releaseID string) (string, error) {
	commandName := ""
	switch operation {
	case OperationActivate:
		commandName = filtercatalogports.CommandActivateFilterCatalogRelease
	case OperationRollback:
		commandName = filtercatalogports.CommandRollbackFilterCatalogRelease
	default:
		return "", fmt.Errorf("unsupported filter catalog transition %q", operation)
	}
	return hashFilterCatalogCommand(struct {
		Command   string `json:"command"`
		ReleaseID string `json:"releaseId"`
	}{
		Command:   commandName,
		ReleaseID: releaseID,
	})
}

func hashFilterCatalogCommand(command any) (string, error) {
	encoded, err := json.Marshal(command)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(encoded)
	return hex.EncodeToString(sum[:]), nil
}

func filterCatalogCommandResult(
	committed filtercatalogports.CommandResult,
) FilterCatalogReleaseCommandResult {
	return FilterCatalogReleaseCommandResult{
		Release:  filterCatalogSlice(committed.Release),
		Changed:  committed.Changed,
		Replayed: committed.Replayed,
	}
}

func filterCatalogStorageError(err error) error {
	switch {
	case err == nil:
		return nil
	case errors.Is(err, model.ErrInvalidArgument),
		errors.Is(err, model.ErrDigestMismatch),
		errors.Is(err, model.ErrReleaseNotFound),
		errors.Is(err, model.ErrInvalidTransition),
		errors.Is(err, model.ErrIdempotencyConflict),
		errors.Is(err, model.ErrCatalogUnavailable):
		return err
	default:
		return fmt.Errorf("%w: %v", model.ErrStorageUnavailable, err)
	}
}

func filterCatalogOutcome(err error) string {
	switch {
	case err == nil:
		return "success"
	case errors.Is(err, model.ErrInvalidArgument):
		return "invalid_argument"
	case errors.Is(err, model.ErrDigestMismatch):
		return "digest_mismatch"
	case errors.Is(err, model.ErrReleaseNotFound):
		return "not_found"
	case errors.Is(err, model.ErrInvalidTransition):
		return "invalid_transition"
	case errors.Is(err, model.ErrIdempotencyConflict):
		return "idempotency_conflict"
	case errors.Is(err, model.ErrCatalogUnavailable):
		return "unavailable"
	default:
		return "storage_unavailable"
	}
}
