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

	contentpublic "quwoquan_service/services/content-service/internal/content/post/application/public"
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
	sourceOwner     string
	cache           *activeSupplySnapshotCache
}

type MongoActiveSupplyReaderOption func(*MongoActiveSupplyReader)

type activeSupplyReleaseState struct {
	Kind              string    `bson:"kind"`
	Environment       string    `bson:"environment"`
	SourceOwner       string    `bson:"sourceOwner"`
	Status            string    `bson:"status"`
	ActiveReleaseID   string    `bson:"activeReleaseId"`
	ManifestDigest    string    `bson:"manifestDigest"`
	ReleaseClass      string    `bson:"releaseClass"`
	ProjectionVersion int64     `bson:"projectionVersion"`
	Revision          int64     `bson:"revision"`
	ActivatedAt       time.Time `bson:"activatedAt"`
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
	return NewMongoActiveSupplyReaderForOwner(db, environment, "qwq_data", opts...)
}

// NewMongoActiveSupplyReaderForOwner constructs the Content-owned exact-key
// reader used by the public active-fence query seam.
func NewMongoActiveSupplyReaderForOwner(
	db *mongo.Database,
	environment string,
	sourceOwner string,
	opts ...MongoActiveSupplyReaderOption,
) *MongoActiveSupplyReader {
	if db == nil {
		return nil
	}
	reader := &MongoActiveSupplyReader{
		stateCollection: db.Collection("data_release_state"),
		postsCollection: db.Collection("posts"),
		playableVideos: mongoPlayableVideoSupplyReader{
			posts: db.Collection("posts"), sourceOwner: strings.TrimSpace(sourceOwner),
		},
		environment: strings.TrimSpace(environment),
		sourceOwner: strings.TrimSpace(sourceOwner),
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
		r.environment == "" || r.sourceOwner == "" {
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
	releaseClass := strings.TrimSpace(state.ReleaseClass)
	if releaseID == "" || !canonicalManifestDigestPattern.MatchString(manifestDigest) ||
		(releaseClass != "research" && releaseClass != "commercial") ||
		state.ProjectionVersion <= 0 || state.Revision <= 0 || state.ActivatedAt.IsZero() {
		r.cache.Invalidate()
		return empty, fmt.Errorf("active release binding is malformed")
	}
	key := activeSupplyCacheKey{
		environment:       strings.TrimSpace(state.Environment),
		releaseID:         releaseID,
		manifestDigest:    manifestDigest,
		releaseClass:      releaseClass,
		projectionVersion: state.ProjectionVersion,
		revision:          state.Revision,
		activatedAt:       state.ActivatedAt,
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
		snapshot.ReleaseClass = releaseClass
		snapshot.ProjectionVersion = state.ProjectionVersion
		snapshot.Revision = state.Revision
		snapshot.ActivatedAt = state.ActivatedAt.UTC()
		// Re-attest after the expensive counts. A release can switch while the
		// singleflight leader is reading projections; returning that late old
		// snapshot would let the in-flight request serve a deactivated release.
		current, currentFound, currentErr := r.readActiveSupplyReleaseState(readCtx)
		if currentErr != nil {
			return empty, fmt.Errorf("re-attest active release after readback: %w", currentErr)
		}
		if !currentFound || strings.TrimSpace(current.ActiveReleaseID) != releaseID ||
			strings.TrimSpace(current.ManifestDigest) != manifestDigest ||
			strings.TrimSpace(current.ReleaseClass) != releaseClass ||
			current.ProjectionVersion != state.ProjectionVersion ||
			current.Revision != state.Revision ||
			!current.ActivatedAt.Equal(state.ActivatedAt) {
			return empty, fmt.Errorf("active release changed during supply readback")
		}
		return snapshot, nil
	})
}

// ReadActiveReleaseFence exposes only the validated Content release identity.
// It reuses ActiveSupplySnapshot so legacy state, malformed identity, and
// in-flight pointer drift retain the existing fail-closed behavior.
func (r *MongoActiveSupplyReader) ReadActiveReleaseFence(
	ctx context.Context,
	query contentpublic.ActiveReleaseFenceQuery,
) (contentpublic.ActiveReleaseFence, error) {
	query.Environment = strings.TrimSpace(query.Environment)
	query.SourceOwner = strings.TrimSpace(query.SourceOwner)
	if r == nil || query.Environment == "" || query.SourceOwner == "" ||
		query.Environment != r.environment || query.SourceOwner != r.sourceOwner {
		return contentpublic.ActiveReleaseFence{}, &contentpublic.ActiveReleaseFenceError{
			Reason: "query does not match configured environment and sourceOwner",
		}
	}
	legacyCount, err := r.stateCollection.CountDocuments(ctx, bson.M{
		"environment": query.Environment, "sourceOwner": query.SourceOwner,
		"kind": bson.M{"$exists": false},
	}, options.Count().SetLimit(1))
	if err != nil {
		return contentpublic.ActiveReleaseFence{}, fmt.Errorf("inspect active release fence legacy state: %w", err)
	}
	if legacyCount != 0 {
		return contentpublic.ActiveReleaseFence{}, &contentpublic.ActiveReleaseFenceError{
			Reason: "legacy active release state requires migration",
		}
	}
	snapshot, err := r.ActiveSupplySnapshot(ctx)
	if err != nil {
		return contentpublic.ActiveReleaseFence{}, err
	}
	result := contentpublic.ActiveReleaseFence{
		Environment: query.Environment, SourceOwner: query.SourceOwner,
	}
	if snapshot.IsEmpty() {
		return result, nil
	}
	result.Found = true
	result.ReleaseID = strings.TrimSpace(snapshot.ActiveReleaseID)
	result.ManifestDigest = strings.TrimSpace(snapshot.ManifestDigest)
	result.Revision = snapshot.Revision
	result.ReleaseClass = strings.TrimSpace(snapshot.ReleaseClass)
	result.ProjectionVersion = snapshot.ProjectionVersion
	result.ActivatedAt = snapshot.ActivatedAt.UTC()
	if err := contentpublic.ValidateActiveReleaseFence(query, result); err != nil {
		return contentpublic.ActiveReleaseFence{}, err
	}
	return result, nil
}

func (r *MongoActiveSupplyReader) readActiveSupplyReleaseState(
	ctx context.Context,
) (activeSupplyReleaseState, bool, error) {
	var state activeSupplyReleaseState
	err := r.stateCollection.FindOne(
		ctx,
		bson.M{
			"environment":     r.environment,
			"sourceOwner":     r.sourceOwner,
			"kind":            "active_pointer",
			"status":          "active",
			"activeReleaseId": bson.M{"$type": "string", "$ne": ""},
		},
		options.FindOne().SetProjection(bson.M{
			"kind": 1, "environment": 1, "sourceOwner": 1, "status": 1,
			"activeReleaseId": 1, "manifestDigest": 1, "releaseClass": 1,
			"projectionVersion": 1, "activatedAt": 1, "revision": 1,
		}),
	).Decode(&state)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return activeSupplyReleaseState{}, false, nil
		}
		return activeSupplyReleaseState{}, false, err
	}
	if state.Kind != "active_pointer" || state.Status != "active" ||
		state.Environment != r.environment || state.SourceOwner != r.sourceOwner {
		return activeSupplyReleaseState{}, false, fmt.Errorf("active release pointer shape is malformed")
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
		"sourceOwner":     sourceOwner,
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
	posts       *mongo.Collection
	sourceOwner string
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
		"sourceOwner":      reader.sourceOwner,
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

var _ postports.ActiveSupplyReader = (*MongoActiveSupplyReader)(nil)
var _ contentpublic.ActiveReleaseFenceQueryPort = (*MongoActiveSupplyReader)(nil)
