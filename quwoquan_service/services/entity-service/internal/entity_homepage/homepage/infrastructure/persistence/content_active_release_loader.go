package persistence

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	homepageports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
)

// ContentActiveReleaseLoader is the narrow adapter for Content's authoritative
// active tuple. It reads that owner-local fence and persists nothing in Entity.
type ContentActiveReleaseLoader struct {
	state       *mongo.Collection
	environment string
	sourceOwner string
}

func NewContentActiveReleaseLoader(
	database *mongo.Database,
	environment string,
	sourceOwner string,
) *ContentActiveReleaseLoader {
	var state *mongo.Collection
	if database != nil {
		state = database.Collection("data_release_state")
	}
	return &ContentActiveReleaseLoader{
		state: state, environment: strings.TrimSpace(environment),
		sourceOwner: strings.TrimSpace(sourceOwner),
	}
}

func (loader *ContentActiveReleaseLoader) LoadActiveRelease(
	ctx context.Context,
) (homepageports.ReleaseIdentity, bool, error) {
	if loader == nil || loader.state == nil || loader.environment == "" || loader.sourceOwner == "" {
		return homepageports.ReleaseIdentity{}, false, fmt.Errorf("Content active release loader is incomplete")
	}
	var pointer struct {
		Kind              string    `bson:"kind"`
		Status            string    `bson:"status"`
		Environment       string    `bson:"environment"`
		SourceOwner       string    `bson:"sourceOwner"`
		ActiveReleaseID   string    `bson:"activeReleaseId"`
		ManifestDigest    string    `bson:"manifestDigest"`
		ProjectionVersion int64     `bson:"projectionVersion"`
		Revision          int64     `bson:"revision"`
		ActivatedAt       time.Time `bson:"activatedAt"`
	}
	err := loader.state.FindOne(ctx, bson.M{
		"kind": "active_pointer", "status": "active",
		"environment": loader.environment, "sourceOwner": loader.sourceOwner,
	}).Decode(&pointer)
	if err == mongo.ErrNoDocuments {
		return homepageports.ReleaseIdentity{}, false, nil
	}
	if err != nil {
		return homepageports.ReleaseIdentity{}, false, fmt.Errorf("read Content active release tuple: %w", err)
	}
	identity := homepageports.ReleaseIdentity{
		Environment: pointer.Environment, SourceOwner: pointer.SourceOwner,
		ReleaseID: pointer.ActiveReleaseID, ManifestDigest: pointer.ManifestDigest,
	}
	if pointer.Kind != "active_pointer" || pointer.Status != "active" ||
		pointer.Environment != loader.environment || pointer.SourceOwner != loader.sourceOwner ||
		pointer.ProjectionVersion <= 0 || pointer.Revision <= 0 || pointer.ActivatedAt.IsZero() ||
		identity.ReleaseID == "" || identity.ManifestDigest == "" {
		return homepageports.ReleaseIdentity{}, false, fmt.Errorf("Content active release tuple is incomplete")
	}
	return identity, true, nil
}
