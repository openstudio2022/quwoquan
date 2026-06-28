// Package placeindex implements the content domain's first-party place snapshot
// store and the write side of the unified search index for location.place
// objects (R-S05e). A free-text location referenced by published content — and
// not yet bound to a canonical entity / homepage — is aggregated and deduplicated
// into a first-party place record (place_snapshots) keyed by a canonical id, then
// projected into the shared ES/OpenSearch index as a location.place object.
//
// The place snapshot is a DERIVED read model: posts remain the single write truth
// source. The place→Document projection and the canonical identity are owned by
// application (ProjectPlaceToSearchDocument / CanonicalPlaceID), shared by the
// projector and the backfill so the two never diverge. ES lives only here
// (infrastructure); a place bound to a canonical entity is removed so it is
// carried by entity.homepage instead (single source — a place appears once).
package placeindex

import (
	"context"
	"log/slog"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/content-service/internal/application/searchprojection"
)

// PlaceSnapshotCollection is the Mongo collection holding first-party place
// snapshots (derived read model over posts).
const PlaceSnapshotCollection = "place_snapshots"

// PlaceStore materializes first-party place snapshots. It is reference-set based
// so the place projector can incrementally add/remove a single post's reference
// and know when a place has no remaining references (then it is deleted, keeping
// the index aligned with the live free-text places).
type PlaceStore interface {
	// AddReference records that postID references the place described by ref,
	// upserting the place record (latest name/geo win) and returning the updated
	// snapshot.
	AddReference(ctx context.Context, ref searchprojection.PlaceRef, postID string) (searchprojection.PlaceSnapshot, error)
	// RemoveReference drops postID from a place's reference set and returns the
	// updated snapshot plus how many references remain. When the last reference
	// is removed the record is deleted and remaining is 0.
	RemoveReference(ctx context.Context, placeID, postID string) (snapshot searchprojection.PlaceSnapshot, remaining int, err error)
	// PlacesReferencing returns every place currently referencing postID (the
	// reverse lookup the projector uses to retract stale references).
	PlacesReferencing(ctx context.Context, postID string) ([]searchprojection.PlaceSnapshot, error)
	// Upsert replaces a place record wholesale with the given snapshot. It is the
	// authoritative rebuild path used by backfill.
	Upsert(ctx context.Context, snapshot searchprojection.PlaceSnapshot) error
}

// --- In-memory implementation (tests + non-mongo dev) ---

// InMemoryPlaceStore is a goroutine-safe in-memory PlaceStore.
type InMemoryPlaceStore struct {
	mu     sync.Mutex
	places map[string]*searchprojection.PlaceSnapshot
}

// NewInMemoryPlaceStore builds an empty in-memory place store.
func NewInMemoryPlaceStore() *InMemoryPlaceStore {
	return &InMemoryPlaceStore{places: map[string]*searchprojection.PlaceSnapshot{}}
}

func (s *InMemoryPlaceStore) AddReference(_ context.Context, ref searchprojection.PlaceRef, postID string) (searchprojection.PlaceSnapshot, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	rec := s.places[ref.PlaceID]
	if rec == nil {
		rec = &searchprojection.PlaceSnapshot{PlaceID: ref.PlaceID}
		s.places[ref.PlaceID] = rec
	}
	rec.Name = ref.Name
	rec.Geo = cloneGeo(ref.Geo)
	rec.RefPostIDs = addUnique(rec.RefPostIDs, postID)
	return cloneSnapshot(*rec), nil
}

func (s *InMemoryPlaceStore) RemoveReference(_ context.Context, placeID, postID string) (searchprojection.PlaceSnapshot, int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	rec := s.places[placeID]
	if rec == nil {
		return searchprojection.PlaceSnapshot{PlaceID: placeID}, 0, nil
	}
	rec.RefPostIDs = removeValue(rec.RefPostIDs, postID)
	if len(rec.RefPostIDs) == 0 {
		snap := cloneSnapshot(*rec)
		delete(s.places, placeID)
		return snap, 0, nil
	}
	return cloneSnapshot(*rec), len(rec.RefPostIDs), nil
}

func (s *InMemoryPlaceStore) PlacesReferencing(_ context.Context, postID string) ([]searchprojection.PlaceSnapshot, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	var out []searchprojection.PlaceSnapshot
	for _, rec := range s.places {
		for _, id := range rec.RefPostIDs {
			if id == postID {
				out = append(out, cloneSnapshot(*rec))
				break
			}
		}
	}
	return out, nil
}

func (s *InMemoryPlaceStore) Upsert(_ context.Context, snapshot searchprojection.PlaceSnapshot) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	rec := cloneSnapshot(snapshot)
	s.places[snapshot.PlaceID] = &rec
	return nil
}

// --- Mongo implementation (production) ---

// placeRecord is the persisted place snapshot shape.
type placeRecord struct {
	ID         string     `bson:"_id"`
	Name       string     `bson:"name"`
	Geo        *geoRecord `bson:"geo,omitempty"`
	RefPostIDs []string   `bson:"refPostIds"`
	CreatedAt  time.Time  `bson:"createdAt,omitempty"`
	UpdatedAt  time.Time  `bson:"updatedAt"`
}

type geoRecord struct {
	Lat float64 `bson:"lat"`
	Lng float64 `bson:"lng"`
}

func (r placeRecord) toSnapshot() searchprojection.PlaceSnapshot {
	snap := searchprojection.PlaceSnapshot{PlaceID: r.ID, Name: r.Name, RefPostIDs: r.RefPostIDs}
	if r.Geo != nil {
		snap.Geo = &rtsearch.GeoPoint{Lat: r.Geo.Lat, Lng: r.Geo.Lng}
	}
	return snap
}

// MongoPlaceStore is the MongoDB-backed PlaceStore for place_snapshots.
type MongoPlaceStore struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

// NewMongoPlaceStore builds the Mongo place store and ensures its reverse-lookup
// index (refPostIds) so PlacesReferencing stays a cheap indexed query.
func NewMongoPlaceStore(coll *mongo.Collection, logger *slog.Logger) *MongoPlaceStore {
	if logger == nil {
		logger = slog.Default()
	}
	s := &MongoPlaceStore{coll: coll, logger: logger}
	s.ensureIndexes()
	return s
}

func (s *MongoPlaceStore) ensureIndexes() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if _, err := s.coll.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "refPostIds", Value: 1}},
	}); err != nil {
		s.logger.Warn("place_snapshots: index creation failed", slog.String("error", err.Error()))
	}
}

func geoToRecord(geo *rtsearch.GeoPoint) *geoRecord {
	if geo == nil {
		return nil
	}
	return &geoRecord{Lat: geo.Lat, Lng: geo.Lng}
}

func (s *MongoPlaceStore) AddReference(ctx context.Context, ref searchprojection.PlaceRef, postID string) (searchprojection.PlaceSnapshot, error) {
	now := time.Now().UTC()
	set := bson.M{"name": ref.Name, "updatedAt": now}
	if rec := geoToRecord(ref.Geo); rec != nil {
		set["geo"] = rec
	}
	update := bson.M{
		"$setOnInsert": bson.M{"createdAt": now},
		"$set":         set,
		"$addToSet":    bson.M{"refPostIds": postID},
	}
	if _, err := s.coll.UpdateOne(ctx, bson.M{"_id": ref.PlaceID}, update, options.UpdateOne().SetUpsert(true)); err != nil {
		return searchprojection.PlaceSnapshot{}, err
	}
	snap, _, err := s.get(ctx, ref.PlaceID)
	return snap, err
}

func (s *MongoPlaceStore) RemoveReference(ctx context.Context, placeID, postID string) (searchprojection.PlaceSnapshot, int, error) {
	now := time.Now().UTC()
	update := bson.M{"$pull": bson.M{"refPostIds": postID}, "$set": bson.M{"updatedAt": now}}
	if _, err := s.coll.UpdateOne(ctx, bson.M{"_id": placeID}, update); err != nil {
		return searchprojection.PlaceSnapshot{PlaceID: placeID}, 0, err
	}
	snap, ok, err := s.get(ctx, placeID)
	if err != nil {
		return searchprojection.PlaceSnapshot{PlaceID: placeID}, 0, err
	}
	if !ok {
		return searchprojection.PlaceSnapshot{PlaceID: placeID}, 0, nil
	}
	if len(snap.RefPostIDs) == 0 {
		if _, err := s.coll.DeleteOne(ctx, bson.M{"_id": placeID}); err != nil {
			return snap, 0, err
		}
		return snap, 0, nil
	}
	return snap, len(snap.RefPostIDs), nil
}

func (s *MongoPlaceStore) PlacesReferencing(ctx context.Context, postID string) ([]searchprojection.PlaceSnapshot, error) {
	cur, err := s.coll.Find(ctx, bson.M{"refPostIds": postID})
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)
	var out []searchprojection.PlaceSnapshot
	for cur.Next(ctx) {
		var rec placeRecord
		if err := cur.Decode(&rec); err != nil {
			return out, err
		}
		out = append(out, rec.toSnapshot())
	}
	return out, cur.Err()
}

func (s *MongoPlaceStore) Upsert(ctx context.Context, snapshot searchprojection.PlaceSnapshot) error {
	now := time.Now().UTC()
	rec := placeRecord{
		ID:         snapshot.PlaceID,
		Name:       snapshot.Name,
		Geo:        geoToRecord(snapshot.Geo),
		RefPostIDs: snapshot.RefPostIDs,
		UpdatedAt:  now,
	}
	_, err := s.coll.ReplaceOne(ctx, bson.M{"_id": snapshot.PlaceID}, rec, options.Replace().SetUpsert(true))
	return err
}

func (s *MongoPlaceStore) get(ctx context.Context, placeID string) (searchprojection.PlaceSnapshot, bool, error) {
	var rec placeRecord
	err := s.coll.FindOne(ctx, bson.M{"_id": placeID}).Decode(&rec)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return searchprojection.PlaceSnapshot{PlaceID: placeID}, false, nil
		}
		return searchprojection.PlaceSnapshot{PlaceID: placeID}, false, err
	}
	return rec.toSnapshot(), true, nil
}

// --- shared helpers ---

func cloneGeo(geo *rtsearch.GeoPoint) *rtsearch.GeoPoint {
	if geo == nil {
		return nil
	}
	g := *geo
	return &g
}

func cloneSnapshot(s searchprojection.PlaceSnapshot) searchprojection.PlaceSnapshot {
	out := searchprojection.PlaceSnapshot{PlaceID: s.PlaceID, Name: s.Name, Geo: cloneGeo(s.Geo)}
	if len(s.RefPostIDs) > 0 {
		out.RefPostIDs = append([]string(nil), s.RefPostIDs...)
	}
	return out
}

func addUnique(ids []string, id string) []string {
	for _, existing := range ids {
		if existing == id {
			return ids
		}
	}
	return append(ids, id)
}

func removeValue(ids []string, id string) []string {
	out := ids[:0]
	for _, existing := range ids {
		if existing != id {
			out = append(out, existing)
		}
	}
	return out
}
