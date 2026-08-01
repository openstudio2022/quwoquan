package application

import (
	"context"
	"errors"
	"time"

	reportmodel "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/domain/model"
)

type Store interface {
	Put(context.Context, reportmodel.Report) error
	List(context.Context) ([]reportmodel.Report, error)
}

type DesiredHashReader interface {
	DesiredHash(context.Context, string, string) (string, error)
}

type CommandFacade struct {
	store       Store
	desiredHash DesiredHashReader
	now         func() time.Time
}

func NewCommandFacade(store Store, desiredHash DesiredHashReader, now func() time.Time) *CommandFacade {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &CommandFacade{store: store, desiredHash: desiredHash, now: now}
}

func (f *CommandFacade) Report(ctx context.Context, input reportmodel.Report, trustedService, trustedEnvironment, candidateDigest string) (reportmodel.Report, error) {
	if f == nil || f.store == nil || f.desiredHash == nil {
		return reportmodel.Report{}, errors.New("config instance report dependencies are unavailable")
	}
	desiredHash, err := f.desiredHash.DesiredHash(ctx, input.Environment, input.Service)
	if err != nil {
		return reportmodel.Report{}, err
	}
	report, err := reportmodel.New(input, trustedService, trustedEnvironment, candidateDigest, desiredHash, f.now())
	if err != nil {
		return reportmodel.Report{}, err
	}
	if err := f.store.Put(ctx, report); err != nil {
		return reportmodel.Report{}, err
	}
	return report, nil
}
