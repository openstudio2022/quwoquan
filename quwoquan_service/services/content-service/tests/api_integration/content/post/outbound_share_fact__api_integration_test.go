// spec_ref: specs/feature-tree/product-ops-growth/outbound-share-distribution/share-attribution-and-token/spec.md#gwt-001
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func TestCreateOutboundSharePersistsFactReceiptAndOutbox(t *testing.T) {
	created := submitPublishedPostWithAuthor(
		t,
		"outbound-share-owner",
		`{"contentType":"article","title":"可分享内容","body":"真实站外分享事实","visibility":"public"}`,
	)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("missing postId")
	}
	requestBody := []byte(`{"channel":"system_share_sheet","destinationKind":"contact","destination":"private-recipient@example.com","referralId":"referral-api-1","deliverySucceeded":true,"providerReceiptId":"provider-receipt-secret"}`)

	perform := func() map[string]any {
		request := httptest.NewRequest(
			http.MethodPost,
			"/content/posts/"+postID+"/outbound-shares",
			bytes.NewReader(requestBody),
		)
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("X-Client-User-Id", "outbound-share-actor")
		request.Header.Set("X-Client-Sub-Account-Id", "outbound-share-actor")
		request.Header.Set("Idempotency-Key", "outbound-share-api-1")
		recorder := httptest.NewRecorder()
		testHandler.ServeHTTP(recorder, request)
		if recorder.Code != http.StatusCreated {
			t.Fatalf("CreateOutboundShare status=%d body=%s", recorder.Code, recorder.Body.String())
		}
		var result map[string]any
		if err := json.Unmarshal(recorder.Body.Bytes(), &result); err != nil {
			t.Fatalf("decode result: %v", err)
		}
		return result
	}

	first := perform()
	second := perform()
	if first["eventId"] == "" || second["eventId"] != first["eventId"] || second["replayed"] != true {
		t.Fatalf("idempotent replay mismatch first=%#v second=%#v", first, second)
	}

	ctx := context.Background()
	if count, err := mongoDB.Collection("outbound_share_facts").CountDocuments(ctx, bson.M{"postId": postID}); err != nil || count != 1 {
		t.Fatalf("fact count=%d err=%v", count, err)
	}
	if count, err := mongoDB.Collection("outbound_share_receipts").CountDocuments(ctx, bson.M{"_id": "outbound-share-api-1"}); err != nil || count != 1 {
		t.Fatalf("receipt count=%d err=%v", count, err)
	}
	if count, err := mongoDB.Collection("outbound_share_outbox").CountDocuments(ctx, bson.M{"_id": first["eventId"]}); err != nil || count != 1 {
		t.Fatalf("outbox count=%d err=%v", count, err)
	}
	var fact bson.M
	if err := mongoDB.Collection("outbound_share_facts").FindOne(ctx, bson.M{"_id": first["eventId"]}).Decode(&fact); err != nil {
		t.Fatalf("read fact: %v", err)
	}
	if fact["destination"] != nil || fact["providerReceiptId"] != nil || fact["destinationDigest"] == nil {
		t.Fatalf("sensitive destination leaked or digest missing: %#v", fact)
	}
	for _, target := range []struct {
		collection string
		filter     bson.M
	}{
		{collection: "posts", filter: bson.M{"_id": postID}},
		{collection: "rm_discovery_feed", filter: bson.M{"postId": postID}},
	} {
		var projection struct {
			ShareCount int64 `bson:"shareCount"`
		}
		if err := mongoDB.Collection(target.collection).FindOne(
			ctx,
			target.filter,
		).Decode(&projection); err != nil {
			t.Fatalf("read %s share count: %v", target.collection, err)
		}
		if projection.ShareCount != 1 {
			t.Fatalf(
				"%s shareCount=%d, want authoritative count 1",
				target.collection,
				projection.ShareCount,
			)
		}
	}
}
