package contentpost

import (
	"context"
	"errors"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	"quwoquan_service/runtime/search/es"
	app "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	"time"
)

const InboxCollection = "search_content_post_inbox"
const CheckpointCollection = "search_content_post_checkpoints"

type Writer interface {
	ApplyVersioned(context.Context, es.VersionedChangeEvent) (bool, error)
}
type Projection struct {
	db     *mongo.Database
	writer Writer
}
type checkpoint struct {
	Version         int64  `bson:"sourceVersion"`
	Digest          string `bson:"projectionDigest"`
	DeletionVersion int64  `bson:"deletionVersion"`
}

func New(db *mongo.Database, writer Writer) (*Projection, error) {
	if db == nil || writer == nil {
		return nil, errors.New("Content Post Mongo and ES writer required")
	}
	return &Projection{db, writer}, nil
}
func (p *Projection) EnsureIndexes(ctx context.Context) error {
	if _, err := p.db.Collection(InboxCollection).Indexes().CreateOne(ctx, mongo.IndexModel{Keys: bson.D{{Key: "eventDigest", Value: 1}}, Options: options.Index().SetName("uq_search_content_post_event").SetUnique(true)}); err != nil {
		return err
	}
	_, err := p.db.Collection(CheckpointCollection).Indexes().CreateOne(ctx, mongo.IndexModel{Keys: bson.D{{Key: "objectDigest", Value: 1}}, Options: options.Index().SetName("uq_search_content_post_checkpoint").SetUnique(true)})
	return err
}
func (p *Projection) ApplyContentPost(ctx context.Context, c app.ContentPostChange) error {
	session, err := p.db.Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(tx context.Context) (any, error) {
		inbox := p.db.Collection(InboxCollection)
		watermarks := p.db.Collection(CheckpointCollection)
		var previous struct {
			Digest string `bson:"payloadDigest"`
		}
		e := inbox.FindOne(tx, bson.M{"eventDigest": c.EventDigest}).Decode(&previous)
		if e == nil {
			if previous.Digest != c.PayloadDigest {
				return nil, app.ErrContentPostConflict
			}
			return nil, nil
		}
		if !errors.Is(e, mongo.ErrNoDocuments) {
			return nil, e
		}
		var mark checkpoint
		e = watermarks.FindOne(tx, bson.M{"objectDigest": c.ObjectDigest}).Decode(&mark)
		if e != nil && !errors.Is(e, mongo.ErrNoDocuments) {
			return nil, e
		}
		if mark.Version == c.SourceVersion && mark.Digest != c.ProjectionDigest {
			return nil, app.ErrContentPostConflict
		}
		if mark.DeletionVersion > 0 && !c.Deleted && c.SourceVersion >= mark.DeletionVersion {
			return nil, app.ErrContentPostConflict
		}
		// 在跨Provider调用前取得同对象事务写锁；不把Mongo作为ES版本比较替身。
		now := time.Now().UTC()
		_, e = watermarks.UpdateOne(tx, bson.M{"objectDigest": c.ObjectDigest}, bson.M{"$set": bson.M{"updatedAt": now}, "$setOnInsert": bson.M{"objectDigest": c.ObjectDigest, "sourceVersion": int64(0), "projectionDigest": "", "deletionVersion": int64(0), "deleted": false}}, options.UpdateOne().SetUpsert(true))
		if e != nil {
			return nil, e
		}
		op := es.OpUpsert
		if c.Deleted {
			op = es.OpDelete
		}
		if _, e = p.writer.ApplyVersioned(tx, es.VersionedChangeEvent{Op: op, Doc: c.Document, SourceVersion: c.SourceVersion}); e != nil {
			return nil, e
		}
		if c.SourceVersion >= mark.Version {
			terminal := mark.DeletionVersion
			if c.Terminal && c.SourceVersion > terminal {
				terminal = c.SourceVersion
			}
			_, e = watermarks.UpdateOne(tx, bson.M{"objectDigest": c.ObjectDigest}, bson.M{"$set": bson.M{"sourceVersion": c.SourceVersion, "projectionDigest": c.ProjectionDigest, "deleted": c.Deleted, "deletionVersion": terminal, "updatedAt": now}})
			if e != nil {
				return nil, e
			}
		}
		_, e = inbox.InsertOne(tx, bson.M{"eventDigest": c.EventDigest, "payloadDigest": c.PayloadDigest, "objectDigest": c.ObjectDigest, "sourceVersion": c.SourceVersion, "appliedAt": now})
		return nil, e
	})
	return err
}

var _ app.ContentPostProjection = (*Projection)(nil)
