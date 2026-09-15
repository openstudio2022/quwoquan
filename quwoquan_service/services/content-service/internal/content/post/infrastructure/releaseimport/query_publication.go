package releaseimport

import (
	"context"
	"encoding/json"
	"fmt"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	rt "quwoquan_service/runtime/search"
	events "quwoquan_service/services/content-service/generated/content/post/contract/event"
	"time"
)

type QueryPublication struct {
	PublicationID string                            `json:"publicationId" bson:"publicationId"`
	Binding       rt.ReleaseQueryPreparationBinding `json:"binding" bson:"binding"`
	Snapshot      rt.ReleasePostCandidateSnapshot   `json:"snapshot" bson:"snapshot"`
	SourceVersion int64                             `json:"sourceVersion" bson:"sourceVersion"`
	OccurredAt    time.Time                         `json:"occurredAt" bson:"occurredAt"`
}
type QueryPublisher struct{ db *mongo.Database }

func NewQueryPublisher(db *mongo.Database) *QueryPublisher { return &QueryPublisher{db} }
func (p *QueryPublisher) EnsureIndexes(ctx context.Context) error {
	_, err := p.db.Collection("data_release_query_publications").Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "publicationId", Value: 1}}, Options: options.Index().SetName("uq_data_release_query_publication").SetUnique(true)},
		{Keys: bson.D{{Key: "binding.release.environment", Value: 1}, {Key: "binding.release.sourceOwner", Value: 1}, {Key: "binding.release.releaseId", Value: 1}, {Key: "binding.release.manifestDigest", Value: 1}, {Key: "binding.slice", Value: 1}, {Key: "binding.providerBindingGeneration", Value: 1}, {Key: "binding.schemaGeneration", Value: 1}}, Options: options.Index().SetName("uq_data_release_query_binding").SetUnique(true)},
	})
	return err
}
func (p *QueryPublisher) Publish(ctx context.Context, b rt.ReleaseQueryPreparationBinding, s rt.ReleasePostCandidateSnapshot) (string, error) {
	if b.Slice != "recommendation" || b.Release != s.Release || s.Validate() != nil {
		return "", rt.ErrCreatorSourceInvalid
	}
	if err := p.EnsureIndexes(ctx); err != nil {
		return "", err
	}
	id, err := rt.CreatorCanonicalDigest(map[string]any{"binding": b, "snapshotDigest": s.SnapshotDigest}, "")
	if err != nil {
		return "", err
	}
	session, err := p.db.Client().StartSession()
	if err != nil {
		return "", err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(tx context.Context) (any, error) {
		filter := bson.M{"binding.release.environment": b.Release.Environment, "binding.release.sourceOwner": b.Release.SourceOwner, "binding.release.releaseId": b.Release.ReleaseID, "binding.release.manifestDigest": b.Release.ManifestDigest, "binding.slice": b.Slice, "binding.providerBindingGeneration": b.ProviderBindingGeneration, "binding.schemaGeneration": b.SchemaGeneration}
		var existing QueryPublication
		e := p.db.Collection("data_release_query_publications").FindOne(tx, filter).Decode(&existing)
		if e == nil {
			if existing.PublicationID != id || existing.Snapshot.SnapshotDigest != s.SnapshotDigest {
				return nil, fmt.Errorf("publication binding conflict")
			}
			var envelope importedOutboxDocument
			if e = p.db.Collection("content_outbox").FindOne(tx, bson.M{"_id": id}).Decode(&envelope); e != nil {
				return nil, e
			}
			payload, _ := json.Marshal(existing)
			if string(payload) != string(envelope.PayloadJSON) {
				return nil, fmt.Errorf("publication outbox drift")
			}
			return nil, nil
		}
		if e != mongo.ErrNoDocuments {
			return nil, e
		}
		var counter struct {
			Value int64 `bson:"value"`
		}
		if e = p.db.Collection("content_outbox_sequences").FindOneAndUpdate(tx, bson.M{"_id": "Post"}, bson.M{"$inc": bson.M{"value": 1}}, options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After)).Decode(&counter); e != nil {
			return nil, e
		}
		publication := QueryPublication{PublicationID: id, Binding: b, Snapshot: s, SourceVersion: counter.Value, OccurredAt: time.Now().UTC().Truncate(time.Millisecond)}
		payload, e := json.Marshal(publication)
		if e != nil {
			return nil, e
		}
		if _, e = p.db.Collection("data_release_query_publications").InsertOne(tx, publication); e != nil {
			return nil, e
		}
		_, e = p.db.Collection("content_outbox").InsertOne(tx, importedOutboxDocument{ID: id, SourceOwner: b.Release.SourceOwner, ReleaseID: b.Release.ReleaseID, ManifestDigest: b.Release.ManifestDigest, OutboxSequence: counter.Value, EventType: events.PostReleaseCandidatePrepared, AggregateType: "Post", AggregateID: id, AggregateVersion: counter.Value, PayloadJSON: payload, OccurredAt: publication.OccurredAt})
		return nil, e
	})
	return id, err
}
