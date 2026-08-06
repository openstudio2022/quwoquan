// spec_ref: specs/feature-tree/product-ops-growth/outbound-share-distribution/share-attribution-and-token/spec.md#gwt-001
// readiness_case: create-outbound-share-api
package outbound_share_fact_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/commandmeta"
	"quwoquan_service/runtime/operation"
	sharehttp "quwoquan_service/services/content-service/internal/content/outbound_share_fact/adapters/inbound/http"
	shareapp "quwoquan_service/services/content-service/internal/content/outbound_share_fact/application/command"
	sharepersistence "quwoquan_service/services/content-service/internal/content/outbound_share_fact/infrastructure/persistence"
)

type publishedPostReader struct{}

func (publishedPostReader) FindShareablePost(
	context.Context,
	string,
) (shareapp.ShareablePostSlice, bool, error) {
	return shareapp.ShareablePostSlice{
		PostID: "post-outbound-share",
		Status: "published",
	}, true, nil
}

func TestCreateOutboundShareHTTPCommitsFactReceiptAndOutboxInRealMongoTransaction(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "outbound_share_fact_http")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	sink := sharepersistence.NewMongoAppendSink(runtime.Database)
	if err := sink.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure OutboundShareFact indexes: %v", err)
	}
	handler := sharehttp.NewHandler(shareapp.BindFacades(shareapp.NewService(
		sink,
		publishedPostReader{},
	)))

	perform := func() (int, map[string]any) {
		request := httptest.NewRequest(
			http.MethodPost,
			"/content/posts/post-outbound-share/outbound-shares",
			strings.NewReader(`{"channel":"system_share","destinationKind":"external_app","destination":"private-recipient@example.com","referralId":"referral-transaction","deliverySucceeded":true,"providerReceiptId":"provider-receipt-secret","clientConfirmedAt":"2026-08-02T08:00:00Z"}`),
		)
		request.Header.Set("Content-Type", "application/json")
		request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
			OperationID:    "content.outbound_share_fact.CreateOutboundShare",
			RequestID:      "request-outbound-share",
			TraceID:        "trace-outbound-share",
			IdempotencyKey: "outbound-share-once",
			Actor: operation.ActorContext{
				AccountID: "account-share-actor",
				PersonaID: "persona-share-actor",
			},
		}))
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
			Actor: operation.ActorContext{
				AccountID: "account-share-actor",
				PersonaID: "persona-share-actor",
			},
		}))
		request = request.WithContext(commandmeta.WithIdempotencyKey(
			request.Context(),
			"outbound-share-once",
		))
		recorder := httptest.NewRecorder()
		handler.CreateOutboundShare(recorder, request)
		var response map[string]any
		if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
			t.Fatalf("decode response status=%d body=%s: %v", recorder.Code, recorder.Body.String(), err)
		}
		return recorder.Code, response
	}

	firstStatus, first := perform()
	if firstStatus != http.StatusCreated {
		t.Fatalf("CreateOutboundShare status=%d response=%#v", firstStatus, first)
	}
	replayStatus, replay := perform()
	if replayStatus != http.StatusCreated {
		t.Fatalf("CreateOutboundShare replay status=%d response=%#v", replayStatus, replay)
	}
	if first["eventId"] == "" || replay["eventId"] != first["eventId"] || replay["replayed"] != true {
		t.Fatalf("idempotent replay mismatch first=%#v replay=%#v", first, replay)
	}

	for _, collection := range []string{
		"outbound_share_facts",
		"outbound_share_receipts",
		"outbound_share_outbox",
	} {
		count, countErr := runtime.Database.Collection(collection).CountDocuments(
			context.Background(),
			bson.M{},
		)
		if countErr != nil {
			t.Fatalf("count %s: %v", collection, countErr)
		}
		if count != 1 {
			t.Fatalf("%s count=%d want=1", collection, count)
		}
	}
	var fact bson.M
	if err := runtime.Database.Collection("outbound_share_facts").FindOne(
		context.Background(),
		bson.M{"_id": first["eventId"]},
	).Decode(&fact); err != nil {
		t.Fatalf("read OutboundShareFact: %v", err)
	}
	if fact["destination"] != nil || fact["providerReceiptId"] != nil || fact["destinationDigest"] == nil {
		t.Fatalf("sensitive destination leaked or digest missing: %#v", fact)
	}
}
