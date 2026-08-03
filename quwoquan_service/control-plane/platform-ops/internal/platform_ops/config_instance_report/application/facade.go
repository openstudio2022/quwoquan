package application

import (
	"context"
	"errors"
	"time"

	reportmodel "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/domain/model"
)

type CommandContext struct {
	Actor       string
	Environment string
	RequestID   string
	TraceID     string
}

type Store interface {
	Commit(context.Context, reportmodel.Report, CommandContext) (reportmodel.Report, error)
	List(context.Context) ([]reportmodel.Report, error)
}

type DesiredHashReader interface {
	DesiredHash(context.Context, string, string) (string, error)
}

type DesiredHashReaderFunc func(context.Context, string, string) (string, error)

func (reader DesiredHashReaderFunc) DesiredHash(
	ctx context.Context,
	environment string,
	service string,
) (string, error) {
	return reader(ctx, environment, service)
}

type CommandFacade struct {
	store       Store
	desiredHash DesiredHashReader
	now         func() time.Time
}

func NewCommandFacade(
	store Store,
	desiredHash DesiredHashReader,
	now func() time.Time,
) *CommandFacade {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &CommandFacade{store: store, desiredHash: desiredHash, now: now}
}

func (facade *CommandFacade) Report(
	ctx context.Context,
	input reportmodel.Report,
	trustedService string,
	trustedEnvironment string,
	candidateDigest string,
	commandContext CommandContext,
) (reportmodel.Report, error) {
	if facade == nil || facade.store == nil || facade.desiredHash == nil {
		return reportmodel.Report{}, errors.New(
			"config instance report dependencies are unavailable",
		)
	}
	desiredHash, err := facade.desiredHash.DesiredHash(
		ctx,
		input.Environment,
		input.Service,
	)
	if err != nil {
		return reportmodel.Report{}, err
	}
	report, err := reportmodel.New(
		input,
		trustedService,
		trustedEnvironment,
		candidateDigest,
		desiredHash,
		facade.now(),
	)
	if err != nil {
		return reportmodel.Report{}, err
	}
	committed, err := facade.store.Commit(ctx, report, commandContext)
	if err != nil {
		return reportmodel.Report{}, err
	}
	return committed, nil
}

type QueryFacade struct{ store Store }

func NewQueryFacade(store Store) *QueryFacade { return &QueryFacade{store: store} }

func (facade *QueryFacade) List(
	ctx context.Context,
) ([]reportmodel.Report, error) {
	if facade == nil || facade.store == nil {
		return nil, errors.New("config instance report store is unavailable")
	}
	return facade.store.List(ctx)
}
