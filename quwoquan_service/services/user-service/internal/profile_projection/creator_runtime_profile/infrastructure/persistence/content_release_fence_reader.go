package persistence

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

// ContentReleaseFenceReader 是 Content owner active tuple 的窄读 adapter：只读
// Content 库 data_release_state 里 environment+sourceOwner 唯一的 active_pointer，
// 在 User 侧不持久化任何 pointer、不扫描 latest、不从旧 Persona 回退。
type ContentReleaseFenceReader struct {
	state       *mongo.Collection
	environment string
	sourceOwner string
}

func NewContentReleaseFenceReader(
	contentDatabase *mongo.Database,
	environment string,
	sourceOwner string,
) *ContentReleaseFenceReader {
	var state *mongo.Collection
	if contentDatabase != nil {
		state = contentDatabase.Collection("data_release_state")
	}
	return &ContentReleaseFenceReader{
		state:       state,
		environment: strings.TrimSpace(environment),
		sourceOwner: strings.TrimSpace(sourceOwner),
	}
}

func (reader *ContentReleaseFenceReader) ActiveContentReleaseFence(
	ctx context.Context,
) (userports.ContentReleaseFence, bool, error) {
	if reader == nil || reader.state == nil || reader.environment == "" || reader.sourceOwner == "" {
		return userports.ContentReleaseFence{}, false, fmt.Errorf("Content release fence reader is incomplete")
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
	err := reader.state.FindOne(ctx, bson.M{
		"kind": "active_pointer", "status": "active",
		"environment": reader.environment, "sourceOwner": reader.sourceOwner,
	}).Decode(&pointer)
	if err == mongo.ErrNoDocuments {
		return userports.ContentReleaseFence{}, false, nil
	}
	if err != nil {
		return userports.ContentReleaseFence{}, false, fmt.Errorf("read Content active release tuple: %w", err)
	}
	fence := userports.ContentReleaseFence{
		Environment:    pointer.Environment,
		SourceOwner:    pointer.SourceOwner,
		ReleaseID:      pointer.ActiveReleaseID,
		ManifestDigest: pointer.ManifestDigest,
	}
	if pointer.Kind != "active_pointer" || pointer.Status != "active" ||
		pointer.Environment != reader.environment || pointer.SourceOwner != reader.sourceOwner ||
		pointer.ProjectionVersion <= 0 || pointer.Revision <= 0 || pointer.ActivatedAt.IsZero() ||
		fence.ReleaseID == "" || fence.ManifestDigest == "" {
		return userports.ContentReleaseFence{}, false, fmt.Errorf("Content active release tuple is incomplete")
	}
	return fence, true, nil
}
