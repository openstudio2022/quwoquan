package publicweb

import (
	"context"
	"errors"
	"fmt"
	"strings"
)

// StoredSource and StoredDocumentLink are authoritative ledger projections.
// The caller supplies only their opaque identifier; URL and lineage always
// come from this server-side lookup.
type StoredSource struct {
	SourceID      string
	NormalizedURL string
}

type StoredDocumentLink struct {
	LinkID         string
	URL            string
	ParentSourceID string
}

type ReferenceLookup interface {
	LookupSource(context.Context, string, string) (StoredSource, error)
	LookupDocumentLink(context.Context, string, string) (StoredDocumentLink, error)
}

type LedgerTargetResolver struct {
	references ReferenceLookup
}

func NewLedgerTargetResolver(references ReferenceLookup) *LedgerTargetResolver {
	if references == nil {
		panic("public web reference lookup is required")
	}
	return &LedgerTargetResolver{references: references}
}

func (r *LedgerTargetResolver) ResolveTarget(
	ctx context.Context,
	runID string,
	target Target,
) (ResolvedTarget, error) {
	value := strings.TrimSpace(target.Value)
	if strings.TrimSpace(runID) == "" || value == "" {
		return ResolvedTarget{}, ErrInvalidTarget
	}
	switch target.Kind {
	case TargetURL:
		return ResolvedTarget{URL: value, Origin: string(TargetURL)}, nil
	case TargetSource:
		source, err := r.references.LookupSource(ctx, runID, value)
		if err != nil {
			if errors.Is(err, ErrEvidenceUnavailable) {
				return ResolvedTarget{}, err
			}
			return ResolvedTarget{}, fmt.Errorf("lookup source: %w", err)
		}
		if strings.TrimSpace(source.SourceID) != value || strings.TrimSpace(source.NormalizedURL) == "" {
			return ResolvedTarget{}, ErrTargetUnavailable
		}
		return ResolvedTarget{
			URL:            source.NormalizedURL,
			Origin:         string(TargetSource),
			ParentSourceID: source.SourceID,
		}, nil
	case TargetDocumentLink:
		link, err := r.references.LookupDocumentLink(ctx, runID, value)
		if err != nil {
			if errors.Is(err, ErrEvidenceUnavailable) {
				return ResolvedTarget{}, err
			}
			return ResolvedTarget{}, fmt.Errorf("lookup document link: %w", err)
		}
		if strings.TrimSpace(link.LinkID) != value || strings.TrimSpace(link.URL) == "" || strings.TrimSpace(link.ParentSourceID) == "" {
			return ResolvedTarget{}, ErrTargetUnavailable
		}
		return ResolvedTarget{
			URL:            link.URL,
			Origin:         string(TargetDocumentLink),
			ParentSourceID: link.ParentSourceID,
		}, nil
	default:
		return ResolvedTarget{}, ErrInvalidTarget
	}
}
