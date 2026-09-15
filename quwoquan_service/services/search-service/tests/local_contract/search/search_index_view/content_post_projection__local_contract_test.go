package local_contract_test

import (
	"encoding/json"
	msg "quwoquan_service/runtime/messaging"
	app "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	"testing"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestContentPostGeneratedDeletionWire(t *testing.T) {
	p := map[string]any{"postId": "post", "authorId": "author", "contentType": "article", "contentIdentity": "work", "status": "published", "deletedAt": "2026-09-13T00:00:00Z", "environment": nil, "sourceOwner": nil, "releaseId": nil, "manifestDigest": nil, "releaseDigest": nil, "sourceVersion": 2, "safetyRevision": 1}
	decode := func(p map[string]any) (app.ContentPostChange, error) {
		raw, _ := json.Marshal(p)
		return app.DecodeContentPostDelivery(msg.StreamDelivery{Stream: "events.content.post_lifecycle", ID: "1-0", Fields: []msg.DurableField{{Name: "eventType", Value: "PostDeleted"}, {Name: "eventId", Value: "e"}, {Name: "aggregateType", Value: "Post"}, {Name: "aggregateId", Value: "post"}, {Name: "aggregateVersion", Value: "2"}, {Name: "occurredAt", Value: "2026-09-13T00:00:00Z"}, {Name: "payload", Value: string(raw)}}})
	}
	c, err := decode(p)
	if err != nil || !c.Terminal || !c.Deleted {
		t.Fatal(c, err)
	}
	for _, key := range []string{"postId", "sourceOwner", "sourceVersion", "environment"} {
		q := map[string]any{}
		for k, v := range p {
			if k != key {
				q[k] = v
			}
		}
		if _, err = decode(q); err == nil {
			t.Fatal("missing accepted", key)
		}
	}
	p["unexpected"] = true
	if _, err = decode(p); err == nil {
		t.Fatal("extra accepted")
	}
	delete(p, "unexpected")
	p["sourceOwner"] = ""
	if _, err = decode(p); err == nil {
		t.Fatal("empty source accepted")
	}
}
