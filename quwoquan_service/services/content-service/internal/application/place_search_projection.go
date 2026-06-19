package application

import (
	"crypto/sha1"
	"encoding/hex"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

// PlaceRef is the first-party place reference a single post contributes from its
// free-text location. It is the unit the place snapshot store aggregates by
// canonical id. It is produced ONLY for posts whose location is NOT yet bound to
// a canonical entity / homepage — those places are carried by entity.homepage
// (single source of truth: a place appears once).
type PlaceRef struct {
	PlaceID string
	Name    string
	Geo     *rtsearch.GeoPoint
}

// PlaceSnapshot is the aggregated first-party place record: one per canonical
// place id, carrying every post that references it. It is a derived read model
// over posts (posts remain the write truth source); the place store materializes
// it and the place projector keeps it + the unified ES index in sync.
type PlaceSnapshot struct {
	PlaceID    string
	Name       string
	Geo        *rtsearch.GeoPoint
	RefPostIDs []string
}

// placeGeohashPrecision is the coarse geohash length (~±2.4km cells) mixed into
// the canonical place id so two same-named places far apart stay distinct while
// the same place referenced by multiple posts converges.
const placeGeohashPrecision = 5

// DerivePlaceRef returns the first-party place reference a post contributes, and
// ok=false when the post must NOT materialize a place: not published+public, no
// location name, or already bound to a canonical entity / homepage (single
// source of truth — those places are carried by entity.homepage, never twice).
func DerivePlaceRef(post postmodel.Post) (PlaceRef, bool) {
	if !strings.EqualFold(strings.TrimSpace(post.Status), "published") {
		return PlaceRef{}, false
	}
	if !strings.EqualFold(strings.TrimSpace(post.Visibility), "public") {
		return PlaceRef{}, false
	}
	name := strings.TrimSpace(post.LocationName)
	if name == "" {
		return PlaceRef{}, false
	}
	// Bound to a canonical entity / homepage => entity.homepage carries it.
	if strings.TrimSpace(post.CanonicalEntityId) != "" || strings.TrimSpace(post.PrimaryHomepageId) != "" {
		return PlaceRef{}, false
	}
	var geo *rtsearch.GeoPoint
	if post.Location.Latitude != 0 || post.Location.Longitude != 0 {
		geo = &rtsearch.GeoPoint{Lat: post.Location.Latitude, Lng: post.Location.Longitude}
	}
	id := CanonicalPlaceID(name, geo)
	if id == "" {
		return PlaceRef{}, false
	}
	return PlaceRef{PlaceID: id, Name: name, Geo: geo}, true
}

// CanonicalPlaceID computes the stable first-party place id from a normalized
// name (+ a coarse geohash when coordinates exist). It NEVER uses a third-party
// POI id, so identity stays first-party and dedup-stable across posts. Returns
// "" for an empty name.
func CanonicalPlaceID(name string, geo *rtsearch.GeoPoint) string {
	norm := normalizePlaceName(name)
	if norm == "" {
		return ""
	}
	bucket := ""
	if geo != nil && (geo.Lat != 0 || geo.Lng != 0) {
		bucket = geohashEncode(geo.Lat, geo.Lng, placeGeohashPrecision)
	}
	sum := sha1.Sum([]byte(norm + "|" + bucket))
	return "place_" + hex.EncodeToString(sum[:])[:16]
}

// ProjectPlaceToSearchDocument projects a place snapshot into the unified search
// Document. It reuses the cross-object geo dimension (Document.Geo +
// Fields[placeName]) rather than introducing parallel fields, and is the single
// source of truth for place→Document, shared by the place projector + backfill.
func ProjectPlaceToSearchDocument(p PlaceSnapshot) rtsearch.Document {
	doc := rtsearch.Document{
		ObjectType:   rtsearch.ObjectTypeLocation,
		ObjectID:     p.PlaceID,
		Title:        p.Name,
		SourceDomain: "content",
		Visibility:   "public",
		BadgeLabel:   "地点",
		// Popularity reflects how many posts reference this place.
		Popularity: float64(len(p.RefPostIDs)),
		Fields: map[string]string{
			// placeName is the cross-object location dimension; for a place
			// object it IS the place name (also Title, so terms match it).
			"placeName": p.Name,
		},
	}
	if p.Geo != nil {
		doc.Geo = &rtsearch.GeoPoint{Lat: p.Geo.Lat, Lng: p.Geo.Lng}
	}
	return doc
}

// normalizePlaceName folds case and collapses whitespace so name variants
// converge to one canonical place identity.
func normalizePlaceName(raw string) string {
	return strings.Join(strings.Fields(strings.ToLower(strings.TrimSpace(raw))), " ")
}

// geohashBase32 is the standard geohash alphabet (no a/i/l/o).
const geohashBase32 = "0123456789bcdefghjkmnpqrstuvwxyz"

// geohashEncode is the standard geohash encoder. It is used only to derive a
// coarse, deterministic geo bucket for the canonical place id (proximity search
// itself uses Document.Geo, never this string), so a small self-contained
// implementation avoids a third-party dependency.
func geohashEncode(lat, lng float64, precision int) string {
	if precision <= 0 {
		return ""
	}
	latMin, latMax := -90.0, 90.0
	lngMin, lngMax := -180.0, 180.0
	bits := []int{16, 8, 4, 2, 1}
	var out strings.Builder
	even := true
	bit := 0
	ch := 0
	for out.Len() < precision {
		if even {
			mid := (lngMin + lngMax) / 2
			if lng >= mid {
				ch |= bits[bit]
				lngMin = mid
			} else {
				lngMax = mid
			}
		} else {
			mid := (latMin + latMax) / 2
			if lat >= mid {
				ch |= bits[bit]
				latMin = mid
			} else {
				latMax = mid
			}
		}
		even = !even
		if bit < 4 {
			bit++
		} else {
			out.WriteByte(geohashBase32[ch])
			bit = 0
			ch = 0
		}
	}
	return out.String()
}
