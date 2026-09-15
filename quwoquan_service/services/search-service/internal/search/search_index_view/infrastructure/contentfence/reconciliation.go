package contentfence

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	"net/http"
	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/runtime/auth"
	rt "quwoquan_service/runtime/search"
	wire "quwoquan_service/services/search-service/generated/search/search_index_view/commitreceipt"
	app "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	"strings"
	"time"
)

const receiptCollection = "search_content_fence_receipts"

type ReconciliationStore struct{ collection *mongo.Collection }

func NewReconciliationStore(db *mongo.Database) *ReconciliationStore {
	return &ReconciliationStore{db.Collection(receiptCollection)}
}
func (s *ReconciliationStore) EnsureIndexes(ctx context.Context) error {
	_, err := s.collection.Indexes().CreateMany(ctx, []mongo.IndexModel{{Keys: bson.D{{Key: "eventDigest", Value: 1}}, Options: options.Index().SetUnique(true).SetName("uq_search_content_fence_event")}, {Keys: bson.D{{Key: "scopeDigest", Value: 1}, {Key: "revision", Value: 1}}, Options: options.Index().SetUnique(true).SetName("uq_search_content_fence_revision")}})
	return err
}
func (s *ReconciliationStore) FindFenceReceipt(ctx context.Context, key string) (app.ContentFenceReceipt, bool, error) {
	var r app.ContentFenceReceipt
	err := s.collection.FindOne(ctx, bson.M{"eventDigest": key}).Decode(&r)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return r, false, nil
	}
	return r, err == nil, err
}
func (s *ReconciliationStore) SaveFenceReceipt(ctx context.Context, r app.ContentFenceReceipt) error {
	_, err := s.collection.InsertOne(ctx, r)
	if mongo.IsDuplicateKeyError(err) {
		prior, ok, e := s.FindFenceReceipt(ctx, r.EventDigest)
		if e == nil && ok && prior.PayloadDigest == r.PayloadDigest {
			return nil
		}
		return app.ErrContentPostConflict
	}
	return err
}

type CommitReader struct {
	base        string
	credentials auth.ServiceAuthorizationProvider
	client      *http.Client
}

func NewCommitReader(base string, credentials auth.ServiceAuthorizationProvider) (*CommitReader, error) {
	if credentials == nil || !strings.HasPrefix(base, "http") {
		return nil, fmt.Errorf("Content receipt endpoint/credentials required")
	}
	return &CommitReader{strings.TrimRight(base, "/"), credentials, &http.Client{Timeout: 500 * time.Millisecond, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}}, nil
}
func (r *CommitReader) ReadCommit(ctx context.Context, q wire.ReadContentReleaseCommitReceiptQuery) (wire.ContentReleaseCommitReceipt, error) {
	var result wire.ContentReleaseCommitReceipt
	path := ""
	for _, d := range operationsecurity.ForDomain("content") {
		if d.CanonicalOperationID == "content.post.ReadContentReleaseCommitReceipt" {
			path = d.PathTemplate
		}
	}
	if path == "" {
		return result, fmt.Errorf("Content commit operation missing")
	}
	raw, err := json.Marshal(q)
	if err != nil {
		return result, err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, r.base+path, bytes.NewReader(raw))
	if err != nil {
		return result, err
	}
	token, err := r.credentials.AuthorizationHeader(ctx)
	if err != nil {
		return result, err
	}
	request.Header.Set("Authorization", token)
	request.Header.Set("Content-Type", "application/json")
	response, err := r.client.Do(request)
	if err != nil {
		return result, err
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return result, fmt.Errorf("Content exact receipt unavailable status=%d", response.StatusCode)
	}
	err = rt.DecodeCreatorValue(response.Body, &result)
	return result, err
}
