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
	feedCollection  *mongo.Collection
	premiumPlayable postports.PremiumPlayableSupplyReader
	environment     string
	cache           *activeSupplySnapshotCache
}

type MongoActiveSupplyReaderOption func(*MongoActiveSupplyReader)

type activeSupplyReleaseState struct {
	Environment     string `bson:"environment"`
	SourceOwner     string `bson:"sourceOwner"`
	Status          string `bson:"status"`
	ActiveReleaseID string `bson:"activeReleaseId"`
	ManifestDigest  string `bson:"manifestDigest"`
}

func WithPremiumPlayableSupplyReader(
	reader postports.PremiumPlayableSupplyReader,
) MongoActiveSupplyReaderOption {
	return func(active *MongoActiveSupplyReader) {
		active.premiumPlayable = reader
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
		feedCollection:  db.Collection("rm_discovery_feed"),
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
		r.feedCollection == nil || r.environment == "" {
		return empty, fmt.Errorf("active supply reader is not fully configured")
	}
	if r.premiumPlayable == nil {
		return empty, fmt.Errorf("premium playable supply reader is not configured")
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
		// Re-attest after the expensive counts. A release can switch while the
		// singleflight leader is reading projections; returning that late old
		// snapshot would let the in-flight request serve a deactivated release.
		current, currentFound, currentErr := r.readActiveSupplyReleaseState(readCtx)
		if currentErr != nil {
			return empty, fmt.Errorf("re-attest active release after readback: %w", currentErr)
		}
		if !currentFound || strings.TrimSpace(current.ActiveReleaseID) != releaseID ||
			strings.TrimSpace(current.ManifestDigest) != manifestDigest {
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
			"activeReleaseId": 1, "manifestDigest": 1,
		}),
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
	discoveryPosts, err := r.feedCollection.CountDocuments(ctx, canonicalFilter)
	if err != nil {
		return empty, fmt.Errorf("count active release discovery posts: %w", err)
	}
	premiumVideos, err := r.premiumPlayable.CountActiveReleasePlayableVideos(
		ctx,
		releaseID,
		manifestDigest,
	)
	if err != nil {
		return empty, fmt.Errorf("count active release premium playable videos: %w", err)
	}
	return postports.ActiveSupplySnapshot{
		Environment:           strings.TrimSpace(environment),
		SourceOwner:           strings.TrimSpace(sourceOwner),
		Status:                strings.TrimSpace(status),
		ActiveReleaseID:       releaseID,
		ManifestDigest:        manifestDigest,
		ReadbackStatus:        "passed",
		Posts:                 posts,
		DiscoveryPosts:        discoveryPosts,
		PremiumPlayableVideos: premiumVideos,
	}, nil
}

func cloneBSONMap(source bson.M) bson.M {
	cloned := make(bson.M, len(source))
	for key, value := range source {
		cloned[key] = value
	}
	return cloned
}
