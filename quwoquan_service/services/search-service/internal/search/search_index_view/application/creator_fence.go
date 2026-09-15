package application

import (
	"context"
	"fmt"
	rt "quwoquan_service/runtime/search"
	"time"
)

// ContentCreatorFence对应Content owner传输值，非Search持久pointer。
type ContentCreatorFence struct {
	Found             bool       `json:"found"`
	Environment       string     `json:"environment"`
	SourceOwner       string     `json:"sourceOwner"`
	ReleaseID         string     `json:"releaseId"`
	ManifestDigest    string     `json:"manifestDigest"`
	Revision          int64      `json:"revision"`
	ProjectionVersion int64      `json:"projectionVersion"`
	ActivatedAt       *time.Time `json:"activatedAt"`
}
type ContentCreatorFenceReader interface {
	Read(context.Context) (ContentCreatorFence, error)
}
type CreatorQueryFence struct {
	reader                          ContentCreatorFenceReader
	environment, generation, schema string
}

func NewCreatorQueryFence(reader ContentCreatorFenceReader, environment, generation, schema string) (*CreatorQueryFence, error) {
	if reader == nil || environment == "" || generation == "" {
		return nil, fmt.Errorf("creator fence binding required")
	}
	return &CreatorQueryFence{reader, environment, generation, schema}, nil
}
func (f *CreatorQueryFence) Pin(ctx context.Context) (context.Context, string, error) {
	value, err := f.reader.Read(ctx)
	if err != nil {
		return ctx, "", err
	}
	if value.Environment != f.environment || value.SourceOwner != "qwq_data" {
		return ctx, "", fmt.Errorf("Content fence identity mismatch")
	}
	var binding *rt.ReleaseQueryPreparationBinding
	if value.Found {
		b := rt.ReleaseQueryPreparationBinding{Release: rt.ReleaseCandidateBinding{Environment: value.Environment, SourceOwner: value.SourceOwner, ReleaseID: value.ReleaseID, ManifestDigest: value.ManifestDigest}, Slice: "creator_search", SchemaGeneration: f.schema, ProviderBindingGeneration: f.generation}
		if err = b.Validate(f.environment, f.generation); err != nil || value.Revision < 1 || value.ProjectionVersion < 1 || value.ActivatedAt == nil || value.ActivatedAt.IsZero() {
			return ctx, "", fmt.Errorf("incomplete Content fence")
		}
		binding = &b
	} else if value.ReleaseID != "" || value.ManifestDigest != "" || value.Revision != 0 || value.ProjectionVersion != 0 || value.ActivatedAt != nil {
		return ctx, "", fmt.Errorf("absent Content fence has state")
	}
	digest, err := rt.CreatorCanonicalDigest(value, "")
	if err != nil {
		return ctx, "", err
	}
	return rt.WithCreatorQueryBinding(ctx, binding), digest, nil
}
