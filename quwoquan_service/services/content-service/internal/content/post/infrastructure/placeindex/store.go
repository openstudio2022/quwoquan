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
//
// Every mutation of a place record atomically increments its version; that
// version is the sourceVersion of the location.place search document
// (DEC-002). A place that loses its last reference is retired (empty reference
// set, version bumped) rather than deleted, so the version sequence can never
// restart below the tombstone already written to the search index.
package placeindex

import (
	"context"
	"log/slog"
	"sort"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/content-service/internal/content/post/application/searchprojection"
)

// PlaceSnapshotCollection is the Mongo collection holding first-party place
// snapshots (derived read model over posts).
const PlaceSnapshotCollection = "place_snapshots"

// PlaceStore materializes first-party place snapshots. It is reference-set based
// so the place projector can incrementally add/remove a single post's reference
// and know when a place has no remaining references (then its search document
// is tombstoned under the bumped version). Every returned snapshot carries the
// post-mutation Version.
type PlaceStore interface {
	// AddReference records that postID references the place described by ref,
	// upserting the place record (latest name/geo win), bumping its version and
	// returning the updated snapshot.
	AddReference(ctx context.Context, ref searchprojection.PlaceRef, postID string) (searchprojection.PlaceSnapshot, error)
	// RemoveReference drops postID from a place's reference set, bumps the
	// version and returns the updated snapshot plus how many references remain.
	// The record is retained (retired) when remaining is 0.
	RemoveReference(ctx context.Context, placeID, postID string) (snapshot searchprojection.PlaceSnapshot, remaining int, err error)
	// PlacesReferencing returns every place currently referencing postID (the
	// reverse lookup the projector uses to retract stale references).
	PlacesReferencing(ctx context.Context, postID string) ([]searchprojection.PlaceSnapshot, error)
	// Upsert replaces a place record's facts wholesale with the given snapshot,
	// bumps its version and returns the stored snapshot. It is the authoritative
	// rebuild path used by backfill.
	Upsert(ctx context.Context, snapshot searchprojection.PlaceSnapshot) (searchprojection.PlaceSnapshot, error)
	// ListAll returns every materialized place (including retired ones) so
	// backfill can reconcile snapshots that no longer have an eligible source post.
	ListAll(ctx context.Context) ([]searchprojection.PlaceSnapshot, error)
	// Retire empties a place's reference set and bumps its version, returning
	// the retired snapshot whose Version fences the search tombstone. Backfill
	// retires first, then tombstones, so an interrupted run remains retryable.
	Retire(ctx context.Context, placeID string) (searchprojection.PlaceSnapshot, error)
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
	rec.Version++
	return cloneSnapshot(*rec), nil
}

func (s *InMemoryPlaceStore) RemoveReference(_ context.Context, placeID, postID string) (searchprojection.PlaceSnapshot, int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	rec := s.places[placeID]
	if rec == nil {
		rec = &searchprojection.PlaceSnapshot{PlaceID: placeID}
		s.places[placeID] = rec
	}
	rec.RefPostIDs = removeValue(rec.RefPostIDs, postID)
	rec.Version++
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

func (s *InMemoryPlaceStore) Upsert(_ context.Context, snapshot searchprojection.PlaceSnapshot) (searchprojection.PlaceSnapshot, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	rec := s.places[snapshot.PlaceID]
	if rec == nil {
		rec = &searchprojection.PlaceSnapshot{PlaceID: snapshot.PlaceID}
		s.places[snapshot.PlaceID] = rec
	}
	rec.Name = snapshot.Name
	rec.Geo = cloneGeo(snapshot.Geo)
	rec.RefPostIDs = append([]string(nil), snapshot.RefPostIDs...)
	rec.Version++
	return cloneSnapshot(*rec), nil
}

func (s *InMemoryPlaceStore) ListAll(
	_ context.Context,
) ([]searchprojection.PlaceSnapshot, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]searchprojection.PlaceSnapshot, 0, len(s.places))
	for _, snapshot := range s.places {
		out = append(out, cloneSnapshot(*snapshot))
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i].PlaceID < out[j].PlaceID
	})
	return out, nil
}

func (s *InMemoryPlaceStore) Retire(
	_ context.Context,
	placeID string,
) (searchprojection.PlaceSnapshot, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	rec := s.places[placeID]
	if rec == nil {
		rec = &searchprojection.PlaceSnapshot{PlaceID: placeID}
		s.places[placeID] = rec
	}
	rec.RefPostIDs = nil
	rec.Version++
	return cloneSnapshot(*rec), nil
}

// --- Mongo implementation (production) ---

// placeRecord is the persisted place snapshot shape.
type placeRecord struct {
	ID         string     `bson:"_id"`
	Name       string     `bson:"name"`
	Geo        *geoRecord `bson:"geo,omitempty"`
	RefPostIDs []string   `bson:"refPostIds"`
	Version    int64      `bson:"version"`
	CreatedAt  time.Time  `bson:"createdAt,omitempty"`
	UpdatedAt  time.Time  `bson:"updatedAt"`
}

type geoRecord struct {
	Lat float64 `bson:"lat"`
	Lng float64 `bson:"lng"`
}

func (r placeRecord) toSnapshot() searchprojection.PlaceSnapshot {
	snap := searchprojection.PlaceSnapshot{PlaceID: r.ID, Name: r.Name, RefPostIDs: r.RefPostIDs, Version: r.Version}
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

// mutate applies one atomic update (always `$inc version`) and returns the
// post-mutation snapshot from the same operation, so concurrent writers each
// observe the exact version their own mutation produced.
func (s *MongoPlaceStore) mutate(ctx context.Context, placeID string, update bson.M) (searchprojection.PlaceSnapshot, error) {
	now := time.Now().UTC()
	set, _ := update["$set"].(bson.M)
	if set == nil {
		set = bson.M{}
	}
	set["updatedAt"] = now
	update["$set"] = set
	update["$inc"] = bson.M{"version": int64(1)}
	update["$setOnInsert"] = bson.M{"createdAt": now}
	var rec placeRecord
	err := s.coll.FindOneAndUpdate(
		ctx,
		bson.M{"_id": placeID},
		update,
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&rec)
	if err != nil {
		return searchprojection.PlaceSnapshot{PlaceID: placeID}, err
	}
	return rec.toSnapshot(), nil
}

func (s *MongoPlaceStore) AddReference(ctx context.Context, ref searchprojection.PlaceRef, postID string) (searchprojection.PlaceSnapshot, error) {
	set := bson.M{"name": ref.Name}
	update := bson.M{
		"$set":      set,
		"$addToSet": bson.M{"refPostIds": postID},
	}
	if rec := geoToRecord(ref.Geo); rec != nil {
		set["geo"] = rec
	} else {
		update["$unset"] = bson.M{"geo": ""}
	}
	return s.mutate(ctx, ref.PlaceID, update)
}

func (s *MongoPlaceStore) RemoveReference(ctx context.Context, placeID, postID string) (searchprojection.PlaceSnapshot, int, error) {
	snap, err := s.mutate(ctx, placeID, bson.M{"$pull": bson.M{"refPostIds": postID}})
	if err != nil {
		return snap, 0, err
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

func (s *MongoPlaceStore) Upsert(ctx context.Context, snapshot searchprojection.PlaceSnapshot) (searchprojection.PlaceSnapshot, error) {
	refs := snapshot.RefPostIDs
	if refs == nil {
		refs = []string{}
	}
	set := bson.M{"name": snapshot.Name, "refPostIds": refs}
	update := bson.M{"$set": set}
	if rec := geoToRecord(snapshot.Geo); rec != nil {
		set["geo"] = rec
	} else {
		update["$unset"] = bson.M{"geo": ""}
	}
	return s.mutate(ctx, snapshot.PlaceID, update)
}

func (s *MongoPlaceStore) ListAll(
	ctx context.Context,
) ([]searchprojection.PlaceSnapshot, error) {
	cursor, err := s.coll.Find(
		ctx,
		bson.D{},
		options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	out := make([]searchprojection.PlaceSnapshot, 0)
	for cursor.Next(ctx) {
		var record placeRecord
		if err := cursor.Decode(&record); err != nil {
			return nil, err
		}
		out = append(out, record.toSnapshot())
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

func (s *MongoPlaceStore) Retire(
	ctx context.Context,
	placeID string,
) (searchprojection.PlaceSnapshot, error) {
	return s.mutate(ctx, placeID, bson.M{"$set": bson.M{"refPostIds": []string{}}})
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
	out := searchprojection.PlaceSnapshot{PlaceID: s.PlaceID, Name: s.Name, Geo: cloneGeo(s.Geo), Version: s.Version}
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
