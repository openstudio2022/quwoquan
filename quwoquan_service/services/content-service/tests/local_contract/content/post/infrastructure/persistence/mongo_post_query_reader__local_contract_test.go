package persistence_test

import (
	"encoding/json"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	"reflect"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

func TestMongoPostQueryReaderProjectionMatchesTypedSliceWhitelist(t *testing.T) {
	assertProjectionMatchesSlice(
		t,
		"PostRevisionSlice",
		PostRevisionProjection(),
		postports.PostRevisionSlice{},
	)
	assertProjectionMatchesSlice(
		t,
		"PostDetailSlice",
		PostDetailProjection(),
		postports.PostDetailSlice{},
	)
	assertProjectionMatchesSlice(
		t,
		"AuthorPostItemSlice",
		AuthorPostProjection(),
		postports.AuthorPostItemSlice{},
	)

	for _, forbidden := range []string{
		"version",
		"embedding",
		"contentDigest",
		"authorQualitySignals",
		"publishLocation",
		"deviceInfo",
	} {
		assertProjectionExcludes(t, PostDetailProjection(), forbidden)
		assertProjectionExcludes(t, AuthorPostProjection(), forbidden)
	}
	if got := bsonFieldValue(PostDetailProjection(), "moderationStatus"); got != 1 {
		t.Fatalf("PostDetailSlice must read internal moderationStatus gate, got %#v", got)
	}
	assertProjectionExcludes(t, AuthorPostProjection(), "moderationStatus")
}

func TestPostDetailSliceDropsAggregateOnlyFieldsDuringDirectBSONDecode(t *testing.T) {
	raw, err := bson.Marshal(bson.D{
		{Key: "_id", Value: "post-typed-reader"},
		{Key: "authorId", Value: "persona-author"},
		{Key: "contentType", Value: "article"},
		{Key: "title", Value: "typed query slice"},
		{Key: "status", Value: "published"},
		{Key: "visibility", Value: "public"},
		{Key: "createdAt", Value: time.Date(2026, time.July, 13, 12, 0, 0, 0, time.UTC)},
		{Key: "updatedAt", Value: time.Date(2026, time.July, 13, 12, 1, 0, 0, time.UTC)},
		{Key: "embedding", Value: bson.A{0.1, 0.2}},
		{Key: "moderationStatus", Value: "pending"},
		{Key: "contentDigest", Value: "internal-digest"},
		{Key: "authorQualitySignals", Value: bson.D{{Key: "risk", Value: "internal"}}},
	})
	if err != nil {
		t.Fatalf("marshal fixture BSON: %v", err)
	}

	var detail postports.PostDetailSlice
	if err := bson.Unmarshal(raw, &detail); err != nil {
		t.Fatalf("direct BSON decode into PostDetailSlice: %v", err)
	}
	if detail.PostID != postports.NewPostID("post-typed-reader") || detail.Title != "typed query slice" {
		t.Fatalf("whitelisted fields did not decode: %+v", detail)
	}

	serialized, err := json.Marshal(detail)
	if err != nil {
		t.Fatalf("marshal typed detail slice: %v", err)
	}
	for _, forbidden := range []string{
		"embedding",
		"moderationStatus",
		"contentDigest",
		"authorQualitySignals",
	} {
		if strings.Contains(string(serialized), forbidden) {
			t.Fatalf("typed detail slice leaked %q: %s", forbidden, serialized)
		}
	}
}

func TestAuthorPostFilterSeparatesPublicAndOwnerVisibility(t *testing.T) {
	authorID := postports.NewPersonaID("persona-author")
	publicFilter, err := AuthorPostFilter(postports.NewAuthorPostReadRequest(
		authorID,
		postports.AuthorPostAccessPublic,
		"",
		"",
		"",
		postports.AuthorPostCursor{},
		10,
	))
	if err != nil {
		t.Fatalf("build public author filter: %v", err)
	}
	if got := bsonFieldValue(publicFilter, "status"); got != "published" {
		t.Fatalf("public filter status = %#v, want published", got)
	}
	if got := bsonFieldValue(publicFilter, "visibility"); got != "public" {
		t.Fatalf("public filter visibility = %#v, want public", got)
	}
	if got := bsonFieldValue(publicFilter, "moderationStatus"); got != "approved" {
		t.Fatalf("public filter moderationStatus = %#v, want approved", got)
	}

	ownerFilter, err := AuthorPostFilter(postports.NewAuthorPostReadRequest(
		authorID,
		postports.AuthorPostAccessOwner,
		"",
		"",
		postports.PostVisibility("private"),
		postports.AuthorPostCursor{},
		10,
	))
	if err != nil {
		t.Fatalf("build owner author filter: %v", err)
	}
	if got := bsonFieldValue(ownerFilter, "visibility"); got != "private" {
		t.Fatalf("owner filter visibility = %#v, want private", got)
	}
	status, ok := bsonFieldValue(ownerFilter, "status").(bson.D)
	if !ok || len(status) != 1 || status[0].Key != "$ne" || status[0].Value != "deleted" {
		t.Fatalf("owner filter must exclude only deleted records, got %#v", status)
	}
}

func assertProjectionMatchesSlice(
	t *testing.T,
	reader string,
	projection bson.D,
	slice any,
) {
	t.Helper()

	allowed := bsonFieldNames(slice)
	if len(projection) != len(allowed) {
		t.Fatalf(
			"%s projection field count = %d, want slice whitelist count %d",
			reader,
			len(projection),
			len(allowed),
		)
	}
	seen := make(map[string]struct{}, len(projection))
	for _, field := range projection {
		if field.Value != 1 {
			t.Fatalf("%s projection %q must be explicit inclusion, got %#v", reader, field.Key, field.Value)
		}
		if _, allowedField := allowed[field.Key]; !allowedField {
			t.Fatalf("%s projection leaks non-slice field %q", reader, field.Key)
		}
		if _, duplicate := seen[field.Key]; duplicate {
			t.Fatalf("%s projection repeats field %q", reader, field.Key)
		}
		seen[field.Key] = struct{}{}
	}
	for field := range allowed {
		if _, projected := seen[field]; !projected {
			t.Fatalf("%s slice whitelist field %q is not projected", reader, field)
		}
	}
}

func bsonFieldNames(slice any) map[string]struct{} {
	typeOfSlice := reflect.TypeOf(slice)
	if typeOfSlice.Kind() == reflect.Pointer {
		typeOfSlice = typeOfSlice.Elem()
	}
	fields := make(map[string]struct{}, typeOfSlice.NumField())
	for index := 0; index < typeOfSlice.NumField(); index++ {
		tag := strings.Split(typeOfSlice.Field(index).Tag.Get("bson"), ",")[0]
		if tag == "" || tag == "-" {
			continue
		}
		fields[tag] = struct{}{}
	}
	return fields
}

func assertProjectionExcludes(t *testing.T, projection bson.D, forbidden string) {
	t.Helper()
	if value := bsonFieldValue(projection, forbidden); value != nil {
		t.Fatalf("projection must not include aggregate-only field %q", forbidden)
	}
}

func bsonFieldValue(document bson.D, key string) any {
	for _, field := range document {
		if field.Key == key {
			return field.Value
		}
	}
	return nil
}
