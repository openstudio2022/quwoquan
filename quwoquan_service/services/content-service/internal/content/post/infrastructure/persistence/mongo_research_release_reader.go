package persistence

import (
	"context"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
)

type MongoResearchReleaseBindingReader struct {
	active *MongoActiveSupplyReader
}

func NewMongoResearchReleaseBindingReader(
	active *MongoActiveSupplyReader,
) *MongoResearchReleaseBindingReader {
	if active == nil {
		return nil
	}
	return &MongoResearchReleaseBindingReader{active: active}
}

func (reader *MongoResearchReleaseBindingReader) ReadActiveResearchRelease(
	ctx context.Context,
) (postapp.ResearchReleaseBinding, error) {
	if reader == nil || reader.active == nil || reader.active.postsCollection == nil {
		return postapp.ResearchReleaseBinding{}, postapp.ErrResearchReleaseUnavailable
	}
	snapshot, err := reader.active.ActiveSupplySnapshot(ctx)
	if err != nil || !snapshot.ContentReady() {
		return postapp.ResearchReleaseBinding{}, fmt.Errorf("%w: active supply readback: %v", postapp.ErrResearchReleaseUnavailable, err)
	}
	filter := bson.M{
		"sourceOwner":      "qwq_data",
		"releaseId":        strings.TrimSpace(snapshot.ActiveReleaseID),
		"manifestDigest":   strings.TrimSpace(snapshot.ManifestDigest),
		"lifecycleStatus":  "active",
		"status":           "published",
		"visibility":       "public",
		"moderationStatus": "approved",
	}
	researchFilter := cloneBSONMap(filter)
	researchFilter["admission.usageScope"] = "research"
	researchPosts, err := reader.active.postsCollection.CountDocuments(ctx, researchFilter)
	if err != nil {
		return postapp.ResearchReleaseBinding{}, fmt.Errorf("%w: count research posts: %v", postapp.ErrResearchReleaseUnavailable, err)
	}
	if researchPosts != snapshot.Posts {
		return postapp.ResearchReleaseBinding{}, postapp.ErrResearchReleaseNotResearch
	}
	current, found, err := reader.active.readActiveSupplyReleaseState(ctx)
	if err != nil || !found || strings.TrimSpace(current.ActiveReleaseID) != snapshot.ActiveReleaseID ||
		strings.TrimSpace(current.ManifestDigest) != snapshot.ManifestDigest {
		return postapp.ResearchReleaseBinding{}, fmt.Errorf("%w: release changed during research readback", postapp.ErrResearchReleaseUnavailable)
	}
	return postapp.ResearchReleaseBinding{
		ReleaseID:      snapshot.ActiveReleaseID,
		ManifestDigest: snapshot.ManifestDigest,
	}, nil
}

var _ postapp.ResearchReleaseBindingReader = (*MongoResearchReleaseBindingReader)(nil)
