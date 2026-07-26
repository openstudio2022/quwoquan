package filtercatalogrelease

import "context"

type Facades struct {
	command FilterCatalogReleaseCommandFacet
	query   FilterCatalogQueryFacet
}

func BindFacades(service *Service) *Facades {
	if service == nil {
		panic("FilterCatalogRelease service is required")
	}
	return &Facades{command: service, query: service}
}

func (facades *Facades) Stage(
	ctx context.Context,
	command StageFilterCatalogReleaseCommand,
) (FilterCatalogReleaseCommandResult, error) {
	return facades.command.Stage(ctx, command)
}

func (facades *Facades) Activate(
	ctx context.Context,
	command ActivateFilterCatalogReleaseCommand,
) (FilterCatalogReleaseCommandResult, error) {
	return facades.command.Activate(ctx, command)
}

func (facades *Facades) Rollback(
	ctx context.Context,
	command RollbackFilterCatalogReleaseCommand,
) (FilterCatalogReleaseCommandResult, error) {
	return facades.command.Rollback(ctx, command)
}

func (facades *Facades) GetActiveFilterCatalog(
	ctx context.Context,
) (FilterCatalogSlice, error) {
	return facades.query.GetActiveFilterCatalog(ctx)
}
