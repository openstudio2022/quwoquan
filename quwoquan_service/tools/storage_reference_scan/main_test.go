package main

import (
	"go/parser"
	"go/token"
	"testing"
)

func TestScanFileResolvesStaticStorageReferences(t *testing.T) {
	file, err := parser.ParseFile(token.NewFileSet(), "store.go", `package store
const (
  collectionPrefix = "alpha_"
  collectionName = collectionPrefix + "items"
  eventStream = "events.alpha.items"
  trimStream = "events.alpha.trimmed"
)
func use(db interface{ Collection(string) any }, redis interface {
  XAdd(any, string, any) any
  XReadGroup(any, string, any) any
  XTrimMinID(any, string, string) any
  Set(any, string, any) any
}) {
  _ = db.Collection(collectionName)
  _ = []any{"$lookup", map[string]any{"from": "joined_items"}}
  _ = redis.XAdd(nil, eventStream, nil)
  _ = redis.XReadGroup(nil, eventStream, nil)
  _ = redis.XTrimMinID(nil, trimStream, "1-0")
  _ = redis.Set(nil, fmt.Sprintf("alpha:item:%s", "item-1"), nil)
}
`, 0)
	if err != nil {
		t.Fatal(err)
	}
	constants := packageConstants{}
	collectConstants(file, constants)
	seen := map[reference]struct{}{}
	scanFile(parsedFile{
		relative:  "quwoquan_service/services/alpha-service/internal/domain/item/store.go",
		packageID: "item",
		file:      file,
	}, constants, seen)
	for _, expected := range []reference{
		{Kind: "collection", Name: "alpha_items", Path: "quwoquan_service/services/alpha-service/internal/domain/item/store.go", Access: "read_write"},
		{Kind: "collection", Name: "joined_items", Path: "quwoquan_service/services/alpha-service/internal/domain/item/store.go", Access: "read"},
		{Kind: "stream", Name: "events.alpha.items", Path: "quwoquan_service/services/alpha-service/internal/domain/item/store.go", Access: "write"},
		{Kind: "stream", Name: "events.alpha.items", Path: "quwoquan_service/services/alpha-service/internal/domain/item/store.go", Access: "read"},
		{Kind: "stream", Name: "events.alpha.trimmed", Path: "quwoquan_service/services/alpha-service/internal/domain/item/store.go", Access: "write"},
		{Kind: "redis_key", Name: "alpha:item:", Path: "quwoquan_service/services/alpha-service/internal/domain/item/store.go", Access: "read_write"},
	} {
		if _, ok := seen[expected]; !ok {
			t.Fatalf("missing storage reference: %#v; got %#v", expected, seen)
		}
	}
}

func TestRedisKeyRejectsURLsAndAcceptsCanonicalPrefix(t *testing.T) {
	if !isRedisKey("cache:item:{itemId}") {
		t.Fatal("canonical Redis key was rejected")
	}
	for _, value := range []string{"https://example.test", "Upper:key", "missing-separator"} {
		if isRedisKey(value) {
			t.Fatalf("non-key value %q was accepted", value)
		}
	}
}
