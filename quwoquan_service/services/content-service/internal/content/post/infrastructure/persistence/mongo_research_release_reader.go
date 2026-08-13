package persistence

import (
	"context"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
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
	closure, err := reader.readResearchReleaseObjectClosure(ctx, researchFilter)
	if err != nil {
		return postapp.ResearchReleaseBinding{}, err
	}
	if int64(len(closure.postIDs)) != researchPosts {
		return postapp.ResearchReleaseBinding{}, fmt.Errorf("%w: research post closure drifted during readback", postapp.ErrResearchReleaseUnavailable)
	}
	current, found, err := reader.active.readActiveSupplyReleaseState(ctx)
	if err != nil || !found || strings.TrimSpace(current.ActiveReleaseID) != snapshot.ActiveReleaseID ||
		strings.TrimSpace(current.ManifestDigest) != snapshot.ManifestDigest {
		return postapp.ResearchReleaseBinding{}, fmt.Errorf("%w: release changed during research readback", postapp.ErrResearchReleaseUnavailable)
	}
	return postapp.ResearchReleaseBinding{
		ReleaseID:      snapshot.ActiveReleaseID,
		ManifestDigest: snapshot.ManifestDigest,
		PostIDs:        closure.postIDs,
		EntityRefs:     closure.entityRefs,
		MediaAssetIDs:  closure.mediaAssetIDs,
		MediaURLForms:  closure.mediaURLForms,
	}, nil
}

type researchReleaseObjectClosure struct {
	postIDs       []string
	entityRefs    []string
	mediaAssetIDs []string
	mediaURLForms []string
}

// researchReleasePostDocument projects only the exact binding identities and
// every stored media URL form of one research post. The URL forms feed the
// server-side network exposure derivation; they are never returned verbatim.
type researchReleasePostDocument struct {
	ID            string   `bson:"_id"`
	EntityRefs    []string `bson:"entityRefs"`
	MediaAssetIDs []string `bson:"mediaAssetIds"`
	MediaURLs     []string `bson:"mediaUrls"`
	VideoURL      string   `bson:"videoUrl"`
	CoverURL      string   `bson:"coverUrl"`
	ThumbnailURL  string   `bson:"thumbnailUrl"`
}

func (reader *MongoResearchReleaseBindingReader) readResearchReleaseObjectClosure(
	ctx context.Context,
	researchFilter bson.M,
) (researchReleaseObjectClosure, error) {
	cursor, err := reader.active.postsCollection.Find(
		ctx,
		researchFilter,
		options.Find().SetProjection(bson.M{
			"_id": 1, "entityRefs": 1, "mediaAssetIds": 1,
			"mediaUrls": 1, "videoUrl": 1, "coverUrl": 1, "thumbnailUrl": 1,
		}),
	)
	if err != nil {
		return researchReleaseObjectClosure{}, fmt.Errorf("%w: read research post closure: %v", postapp.ErrResearchReleaseUnavailable, err)
	}
	defer func() { _ = cursor.Close(ctx) }()
	var closure researchReleaseObjectClosure
	for cursor.Next(ctx) {
		var document researchReleasePostDocument
		if err := cursor.Decode(&document); err != nil {
			return researchReleaseObjectClosure{}, fmt.Errorf("%w: decode research post closure: %v", postapp.ErrResearchReleaseUnavailable, err)
		}
		if strings.TrimSpace(document.ID) == "" {
			return researchReleaseObjectClosure{}, fmt.Errorf("%w: research post is missing its canonical id", postapp.ErrResearchReleaseUnavailable)
		}
		closure.postIDs = append(closure.postIDs, document.ID)
		closure.entityRefs = append(closure.entityRefs, document.EntityRefs...)
		closure.mediaAssetIDs = append(closure.mediaAssetIDs, document.MediaAssetIDs...)
		closure.mediaURLForms = append(closure.mediaURLForms, document.MediaURLs...)
		closure.mediaURLForms = append(
			closure.mediaURLForms,
			document.VideoURL,
			document.CoverURL,
			document.ThumbnailURL,
		)
	}
	if err := cursor.Err(); err != nil {
		return researchReleaseObjectClosure{}, fmt.Errorf("%w: iterate research post closure: %v", postapp.ErrResearchReleaseUnavailable, err)
	}
	return closure, nil
}

var _ postapp.ResearchReleaseBindingReader = (*MongoResearchReleaseBindingReader)(nil)
