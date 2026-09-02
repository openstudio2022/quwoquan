package persistence

import (
	"context"
	"fmt"
	"regexp"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

var canonicalManifestDigestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

// MongoActiveSupplyReader is the production read side of data_release_state.
// The importer remains the sole writer; feed requests only verify that their
// environment has at least one canonical active release.
type MongoActiveSupplyReader struct {
	stateCollection *mongo.Collection
	postsCollection *mongo.Collection
	playableVideos  postports.PlayableVideoSupplyReader
	environment     string
	cache           *activeSupplySnapshotCache
}

type MongoActiveSupplyReaderOption func(*MongoActiveSupplyReader)

type activeSupplyReleaseState struct {
	Environment     string    `bson:"environment"`
	SourceOwner     string    `bson:"sourceOwner"`
	Status          string    `bson:"status"`
	ActiveReleaseID string    `bson:"activeReleaseId"`
	ManifestDigest  string    `bson:"manifestDigest"`
	ReleaseClass    string    `bson:"releaseClass"`
	ActivatedAt     time.Time `bson:"activatedAt"`
}

func WithPlayableVideoSupplyReader(
	reader postports.PlayableVideoSupplyReader,
) MongoActiveSupplyReaderOption {
	return func(active *MongoActiveSupplyReader) {
		active.playableVideos = reader
	}
}

func WithActiveSupplyCachePolicy(
	ttl time.Duration,
	jitter time.Duration,
) MongoActiveSupplyReaderOption {
	return func(active *MongoActiveSupplyReader) {
		active.cache = newActiveSupplySnapshotCache(ttl, jitter)
	}
}

func NewMongoActiveSupplyReader(
	db *mongo.Database,
	environment string,
	opts ...MongoActiveSupplyReaderOption,
) *MongoActiveSupplyReader {
	if db == nil {
		return nil
	}
	reader := &MongoActiveSupplyReader{
		stateCollection: db.Collection("data_release_state"),
		postsCollection: db.Collection("posts"),
		playableVideos:  mongoPlayableVideoSupplyReader{posts: db.Collection("posts")},
		environment:     strings.TrimSpace(environment),
		cache: newActiveSupplySnapshotCache(
			DefaultActiveSupplyCacheTTL,
			DefaultActiveSupplyCacheJitter,
		),
	}
	for _, opt := range opts {
		if opt != nil {
			opt(reader)
		}
	}
	return reader
}

func (r *MongoActiveSupplyReader) ActiveSupplySnapshot(
	ctx context.Context,
) (postports.ActiveSupplySnapshot, error) {
	empty := postports.ActiveSupplySnapshot{}
	if r == nil || r.stateCollection == nil || r.postsCollection == nil ||
		r.environment == "" {
		return empty, fmt.Errorf("active supply reader is not fully configured")
	}
	if r.playableVideos == nil {
		return empty, fmt.Errorf("playable video supply reader is not configured")
	}
	state, found, err := r.readActiveSupplyReleaseState(ctx)
	if err != nil {
		r.cache.Invalidate()
		return empty, err
	}
	if !found {
		r.cache.Invalidate()
		return empty, nil
	}
	releaseID := strings.TrimSpace(state.ActiveReleaseID)
	manifestDigest := strings.TrimSpace(state.ManifestDigest)
	if releaseID == "" || !canonicalManifestDigestPattern.MatchString(manifestDigest) {
		r.cache.Invalidate()
		return empty, fmt.Errorf("active release binding is malformed")
	}
	key := activeSupplyCacheKey{
		environment:    strings.TrimSpace(state.Environment),
		releaseID:      releaseID,
		manifestDigest: manifestDigest,
		releaseClass:   strings.TrimSpace(state.ReleaseClass),
	}
	return r.cache.Load(ctx, key, func(readCtx context.Context) (postports.ActiveSupplySnapshot, error) {
		snapshot, readErr := r.readActiveSupplyProjectionCounts(
			readCtx,
			state.Environment,
			state.SourceOwner,
			state.Status,
			releaseID,
			manifestDigest,
		)
		if readErr != nil {
			return empty, readErr
		}
		snapshot.ReleaseClass = strings.TrimSpace(state.ReleaseClass)
		// Re-attest after the expensive counts. A release can switch while the
		// singleflight leader is reading projections; returning that late old
		// snapshot would let the in-flight request serve a deactivated release.
		current, currentFound, currentErr := r.readActiveSupplyReleaseState(readCtx)
		if currentErr != nil {
			return empty, fmt.Errorf("re-attest active release after readback: %w", currentErr)
		}
		if !currentFound || strings.TrimSpace(current.ActiveReleaseID) != releaseID ||
			strings.TrimSpace(current.ManifestDigest) != manifestDigest ||
			strings.TrimSpace(current.ReleaseClass) != strings.TrimSpace(state.ReleaseClass) {
			return empty, fmt.Errorf("active release changed during supply readback")
		}
		return snapshot, nil
	})
}

func (r *MongoActiveSupplyReader) readActiveSupplyReleaseState(
	ctx context.Context,
) (activeSupplyReleaseState, bool, error) {
	var state activeSupplyReleaseState
	err := r.stateCollection.FindOne(
		ctx,
		bson.M{
			"environment":     r.environment,
			"sourceOwner":     "qwq_data",
			"status":          "active",
			"activeReleaseId": bson.M{"$type": "string", "$ne": ""},
		},
		options.FindOne().SetProjection(bson.M{
			"environment": 1, "sourceOwner": 1, "status": 1,
			"activeReleaseId": 1, "manifestDigest": 1, "releaseClass": 1,
			"activatedAt": 1,
		}).SetSort(bson.D{{Key: "activatedAt", Value: -1}}),
	).Decode(&state)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return activeSupplyReleaseState{}, false, nil
		}
		return activeSupplyReleaseState{}, false, err
	}
	return state, true, nil
}

func (r *MongoActiveSupplyReader) readActiveSupplyProjectionCounts(
	ctx context.Context,
	environment string,
	sourceOwner string,
	status string,
	releaseID string,
	manifestDigest string,
) (postports.ActiveSupplySnapshot, error) {
	empty := postports.ActiveSupplySnapshot{}
	canonicalFilter := bson.M{
		"sourceOwner":     "qwq_data",
		"releaseId":       releaseID,
		"manifestDigest":  manifestDigest,
		"lifecycleStatus": "active",
		"status":          "published",
		"visibility":      "public",
	}
	postFilter := cloneBSONMap(canonicalFilter)
	postFilter["moderationStatus"] = "approved"
	posts, err := r.postsCollection.CountDocuments(ctx, postFilter)
	if err != nil {
		return empty, fmt.Errorf("count active release posts: %w", err)
	}
	playableVideos, err := r.playableVideos.CountActiveReleasePlayableVideos(
		ctx,
		releaseID,
		manifestDigest,
	)
	if err != nil {
		return empty, fmt.Errorf("count active release playable videos: %w", err)
	}
	return postports.ActiveSupplySnapshot{
		Environment:     strings.TrimSpace(environment),
		SourceOwner:     strings.TrimSpace(sourceOwner),
		Status:          strings.TrimSpace(status),
		ActiveReleaseID: releaseID,
		ManifestDigest:  manifestDigest,
		ReadbackStatus:  "passed",
		Posts:           posts,
		PlayableVideos:  playableVideos,
	}, nil
}

type mongoPlayableVideoSupplyReader struct {
	posts *mongo.Collection
}

func (reader mongoPlayableVideoSupplyReader) CountActiveReleasePlayableVideos(
	ctx context.Context,
	activeReleaseID string,
	manifestDigest string,
) (int64, error) {
	if reader.posts == nil {
		return 0, fmt.Errorf("Post collection is unavailable")
	}
	return reader.posts.CountDocuments(ctx, bson.M{
		"sourceOwner":      "qwq_data",
		"releaseId":        strings.TrimSpace(activeReleaseID),
		"manifestDigest":   strings.TrimSpace(manifestDigest),
		"lifecycleStatus":  "active",
		"status":           "published",
		"visibility":       "public",
		"moderationStatus": "approved",
		"contentType":      "video",
		"videoUrl":         bson.M{"$type": "string", "$ne": ""},
		"durationMs":       bson.M{"$gt": 0},
	})
}

var _ postports.PlayableVideoSupplyReader = mongoPlayableVideoSupplyReader{}

func cloneBSONMap(source bson.M) bson.M {
	cloned := make(bson.M, len(source))
	for key, value := range source {
		cloned[key] = value
	}
	return cloned
}
