package creatorprojection

import (
	"context"
	"errors"
	"fmt"
	rt "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	app "quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

type Provider struct {
	writer, reader *es.Client
	namespace      string
}

func NewProvider(writer, reader *es.Client, namespace string) *Provider {
	return &Provider{writer, reader, namespace}
}
func (p *Provider) check(ctx context.Context) error {
	if err := p.reader.VerifyPhysicalNamespace(ctx, p.namespace); err != nil {
		return err
	}
	return p.writer.VerifyPhysicalNamespace(ctx, p.namespace)
}
func (p *Provider) Write(ctx context.Context, b rt.ReleaseQueryPreparationBinding, s rt.SearchReleaseCandidateSnapshot) ([]string, error) {
	if err := p.check(ctx); err != nil {
		return nil, err
	}
	ids, err := p.writer.WriteReleaseCandidate(ctx, b, s)
	return ids, projectionError(err)
}
func (p *Provider) Verify(ctx context.Context, b rt.ReleaseQueryPreparationBinding, s rt.SearchReleaseCandidateSnapshot) ([]rt.ReleaseQueryClassEvidence, error) {
	if err := p.check(ctx); err != nil {
		return nil, err
	}
	e, err := p.reader.VerifyReleaseCandidate(ctx, b, s)
	return e, projectionError(err)
}
func projectionError(err error) error {
	if errors.Is(err, es.ErrSameVersionDigestConflict) || errors.Is(err, es.ErrVersionedSourceStateInvalid) || errors.Is(err, es.ErrIndexSchemaIncompatible) {
		return fmt.Errorf("%w: %v", rt.ErrCreatorProjectionConflict, err)
	}
	return err
}

var _ app.ReleaseCandidateIndex = (*Provider)(nil)
