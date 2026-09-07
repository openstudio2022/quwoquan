package public_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	contentpublic "quwoquan_service/services/content-service/internal/content/post/application/public"
)

const fenceDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

type activeFenceReaderStub struct {
	fence contentpublic.ActiveReleaseFence
	err   error
	query contentpublic.ActiveReleaseFenceQuery
}

func (reader *activeFenceReaderStub) ReadActiveReleaseFence(
	_ context.Context,
	query contentpublic.ActiveReleaseFenceQuery,
) (contentpublic.ActiveReleaseFence, error) {
	reader.query = query
	return reader.fence, reader.err
}

func TestActiveReleaseFencePublicPortReturnsCompleteIdentity(t *testing.T) {
	activatedAt := time.Date(2026, 9, 6, 4, 0, 0, 0, time.UTC)
	reader := &activeFenceReaderStub{fence: contentpublic.ActiveReleaseFence{
		Found: true, Environment: "alpha", SourceOwner: "qwq_data",
		ReleaseID: "release-42", ManifestDigest: fenceDigest,
		Revision: 7, ReleaseClass: "research", ProjectionVersion: 91,
		ActivatedAt: activatedAt,
	}}
	facade := contentpublic.NewActiveReleaseFenceQueryFacade(reader)
	got, err := facade.ReadActiveReleaseFence(context.Background(), contentpublic.ActiveReleaseFenceQuery{
		Environment: " alpha ", SourceOwner: " qwq_data ",
	})
	if err != nil {
		t.Fatal(err)
	}
	if reader.query.Environment != "alpha" || reader.query.SourceOwner != "qwq_data" {
		t.Fatalf("query key was not canonicalized: %+v", reader.query)
	}
	if !got.Found || got.Environment != "alpha" || got.SourceOwner != "qwq_data" ||
		got.ReleaseID != "release-42" || got.ManifestDigest != fenceDigest ||
		got.Revision != 7 || got.ReleaseClass != "research" ||
		got.ProjectionVersion != 91 || !got.ActivatedAt.Equal(activatedAt) {
		t.Fatalf("active fence identity is incomplete: %+v", got)
	}
}

func TestActiveReleaseFencePublicPortReturnsTypedNotFound(t *testing.T) {
	reader := &activeFenceReaderStub{fence: contentpublic.ActiveReleaseFence{
		Environment: "alpha", SourceOwner: "qwq_data",
	}}
	got, err := contentpublic.NewActiveReleaseFenceQueryFacade(reader).ReadActiveReleaseFence(
		context.Background(),
		contentpublic.ActiveReleaseFenceQuery{Environment: "alpha", SourceOwner: "qwq_data"},
	)
	if err != nil || got.Found || got.Environment != "alpha" || got.SourceOwner != "qwq_data" {
		t.Fatalf("not-found fence=%+v err=%v", got, err)
	}
}

func TestActiveReleaseFencePublicPortFailsClosedOnPriorAndDrift(t *testing.T) {
	query := contentpublic.ActiveReleaseFenceQuery{Environment: "alpha", SourceOwner: "qwq_data"}
	now := time.Date(2026, 9, 6, 4, 0, 0, 0, time.UTC)
	valid := contentpublic.ActiveReleaseFence{
		Found: true, Environment: "alpha", SourceOwner: "qwq_data",
		ReleaseID: "release-42", ManifestDigest: fenceDigest,
		Revision: 7, ReleaseClass: "commercial", ProjectionVersion: 91,
		ActivatedAt: now,
	}
	tests := map[string]contentpublic.ActiveReleaseFence{
		"prior found tuple": {
			Found: true, Environment: "alpha", SourceOwner: "qwq_data",
			ReleaseID: "prior", ManifestDigest: fenceDigest,
		},
		"not-found with stale state": {
			Environment: "alpha", SourceOwner: "qwq_data", ReleaseID: "stale",
		},
		"owner drift": func() contentpublic.ActiveReleaseFence {
			value := valid
			value.SourceOwner = "other_owner"
			return value
		}(),
		"revision drift": func() contentpublic.ActiveReleaseFence {
			value := valid
			value.Revision = 0
			return value
		}(),
	}
	for name, fence := range tests {
		t.Run(name, func(t *testing.T) {
			_, err := contentpublic.NewActiveReleaseFenceQueryFacade(
				&activeFenceReaderStub{fence: fence},
			).ReadActiveReleaseFence(context.Background(), query)
			var typed *contentpublic.ActiveReleaseFenceError
			if !errors.As(err, &typed) ||
				!strings.Contains(err.Error(), contentpublic.ActiveReleaseFenceInvalidCode) {
				t.Fatalf("prior/drift did not fail closed with typed error: %v", err)
			}
		})
	}
}
