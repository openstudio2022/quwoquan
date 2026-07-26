package search

import (
	"context"
	"sort"
)

// CandidateSource fetches candidate documents for a plan from a single domain
// store (Mongo text / receipted query, PG GIN, etc.). Services implement this
// and push the target/anchor/tags/timeRange/permission constraints down into
// the store query so the candidate set stays bounded.
type CandidateSource interface {
	Candidates(ctx context.Context, plan RetrievePlan) ([]Document, error)
	SourceName() string
}

// NativeStoreBackend supports domain-local retrieval and deterministic
// contracts. It fans out to per-domain CandidateSources and returns candidates
// for the shared CrossTypeRanker; unified search production does not bind it.
type NativeStoreBackend struct {
	sources []CandidateSource
}

// NewNativeStoreBackend builds the native backend over the given domain sources.
func NewNativeStoreBackend(sources ...CandidateSource) *NativeStoreBackend {
	return &NativeStoreBackend{sources: sources}
}

// Name implements RecallBackend.
func (b *NativeStoreBackend) Name() string { return "native_store" }

// Recall implements RecallBackend by gathering candidates from every domain
// source whose object types intersect the planned targets.
func (b *NativeStoreBackend) Recall(ctx context.Context, plan RetrievePlan) ([]RecallCandidate, error) {
	out := []RecallCandidate{}
	for _, src := range b.sources {
		docs, err := src.Candidates(ctx, plan)
		if err != nil {
			// Degrade gracefully: skip the failing source, keep the rest.
			continue
		}
		for _, doc := range docs {
			out = append(out, RecallCandidate{Document: doc, Source: src.SourceName()})
		}
	}
	// Stable ordering before ranking for deterministic output.
	sort.SliceStable(out, func(i, j int) bool {
		return out[i].Document.ObjectID < out[j].Document.ObjectID
	})
	return out, nil
}

// SliceCandidateSource is an in-memory CandidateSource over a fixed document
// set. It is used by tests and by lightweight providers that already hold the
// documents in memory.
type SliceCandidateSource struct {
	Source string
	Docs   []Document
}

// Candidates implements CandidateSource.
func (s SliceCandidateSource) Candidates(_ context.Context, _ RetrievePlan) ([]Document, error) {
	return s.Docs, nil
}

// SourceName implements CandidateSource.
func (s SliceCandidateSource) SourceName() string {
	if s.Source == "" {
		return "slice"
	}
	return s.Source
}

// NewSliceBackend is a convenience constructor for a native backend over a
// static document set (tests / in-memory providers).
func NewSliceBackend(docs []Document) *NativeStoreBackend {
	return NewNativeStoreBackend(SliceCandidateSource{Source: "slice", Docs: docs})
}
