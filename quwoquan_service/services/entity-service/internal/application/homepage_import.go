package application

import (
	"context"

	homepageapp "quwoquan_service/services/entity-service/internal/application/homepage"
)

type ImportedHomepageInput = homepageapp.ImportedInput
type HomepageImportMode = homepageapp.ImportMode
type HomepageImportRequest = homepageapp.ImportRequest
type HomepageImportReport = homepageapp.ImportReport

const (
	HomepageImportModeUpsert = homepageapp.ImportModeUpsert
	HomepageImportModeSync   = homepageapp.ImportModeSync
)

func (s *HomepageService) ReconcileImportedHomepages(
	ctx context.Context,
	request HomepageImportRequest,
) (HomepageImportReport, error) {
	return s.imports.Reconcile(ctx, request)
}
