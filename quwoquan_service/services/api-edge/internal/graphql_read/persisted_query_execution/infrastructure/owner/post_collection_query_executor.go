package owner

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	auth "quwoquan_service/runtime/auth"
	app "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/application"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
	"strings"
	"time"
)

func collectionOwnerCalls(authenticated bool) int {
	if authenticated {
		return 3
	}
	return 1
}

const CollectionExecutorKey = "content.postCollection.query"
const CollectionReadScope = "content.post_collection.graphql.read"
const collectionReadHash = "aabadb9772a276ea6c2837d0b04508e7fcbb1d8be5d6194e01ba837a6dee0f5a"
const collectionManagementHash = "a57f5fda7db3268872328cb520504de42bd12fe34e97bff61d804674b112d4db"

type CollectionGrantIssuer interface {
	Issue(context.Context, string, auth.CollectionQueryBinding) (auth.CollectionQueryGrantResult, error)
}
type PostCollectionQueryExecutor struct {
	Origin           *url.URL
	Client           *http.Client
	Credentials      auth.ServiceAuthorizationProvider
	Authority        CollectionGrantIssuer
	SourceCredential func(context.Context) (string, error)
	GraphHash        string
}

func collectionResponseSpec(management bool) objectSpec {
	stringSpec := responseValueSpec{kind: responseString}
	nullableString := responseValueSpec{kind: responseString, nullable: true}
	intSpec := responseValueSpec{kind: responseInt}
	boolSpec := responseValueSpec{kind: responseBool}
	fields := map[string]responseValueSpec{"collectionId": stringSpec, "name": stringSpec, "coverAssetId": nullableString, "visibility": stringSpec, "version": intSpec}
	member := objectSpec{fields: map[string]responseValueSpec{"postId": stringSpec, "title": stringSpec, "contentType": stringSpec}}
	if management {
		member.fields = map[string]responseValueSpec{"postId": stringSpec, "title": nullableString, "readable": boolSpec}
	} else {
		fields["ownerPersonaId"] = stringSpec
		fields["visibleCount"] = intSpec
		fields["nextCursor"] = nullableString
		fields["canManage"] = boolSpec
	}
	item := responseValueSpec{kind: responseObject, object: &member}
	fields["members"] = responseValueSpec{kind: responseList, item: &item, maxItems: 100}
	return objectSpec{fields: fields}
}

func ValidateCollectionEntry(e domain.Entry) error {
	hash := collectionReadHash
	operation := "content.post_collection.GetPostCollection"
	if e.OperationName == "PostCollectionManagement" {
		hash = collectionManagementHash
		operation = "content.post_collection.GetPostCollectionManagement"
	} else if e.OperationName != "PostCollection" {
		return errors.New("unknown collection operation")
	}
	if e.SHA256Hash != hash || e.CanonicalOperationID != operation || e.ExecutorKey != CollectionExecutorKey || e.OperationType != "query" || len(e.ObjectIDs) != 1 || e.ObjectIDs[0] != "content.post_collection" {
		return errors.New("collection persisted identity mismatch")
	}
	return nil
}
func (e *PostCollectionQueryExecutor) Execute(ctx context.Context, entry domain.Entry, variables map[string]any) (app.ExecutionResult, error) {
	if err := ValidateCollectionEntry(entry); err != nil {
		return app.ExecutionResult{}, err
	}
	if e == nil || e.Origin == nil || e.Client == nil || e.Credentials == nil || e.GraphHash == "" {
		return app.ExecutionResult{}, errors.New("collection executor unavailable")
	}
	id, ok := variables["collectionId"].(string)
	if !ok || id == "" || strings.TrimSpace(id) != id || len(id) > 128 {
		return app.ExecutionResult{}, app.ErrRequestRejected
	}
	management := entry.OperationName == "PostCollectionManagement"
	allowed := map[string]bool{"collectionId": true, "first": true}
	if !management {
		allowed["first"] = true
		allowed["after"] = true
	}
	for key := range variables {
		if !allowed[key] {
			return app.ExecutionResult{}, app.ErrRequestRejected
		}
	}
	if management {
		number, ok := variables["first"].(json.Number)
		first, err := number.Int64()
		if !ok || err != nil || first != 100 {
			return app.ExecutionResult{}, app.ErrRequestRejected
		}
	}
	if !management {
		number, ok := variables["first"].(json.Number)
		first, parseErr := number.Int64()
		if !ok || parseErr != nil || first < 1 || first > 100 {
			return app.ExecutionResult{}, app.ErrRequestRejected
		}
		if after, present := variables["after"]; present && after != nil {
			if _, ok := after.(string); !ok {
				return app.ExecutionResult{}, app.ErrRequestRejected
			}
		}
	}
	ctx, cancel := context.WithTimeout(ctx, 2500*time.Millisecond)
	defer cancel()
	payload, err := json.Marshal(internalPersistedRequest{OperationName: entry.OperationName, Variables: variables, Extensions: internalPersistedExtensions{PersistedQuery: internalPersistedDescriptor{Version: 1, SHA256Hash: entry.SHA256Hash}}})
	if err != nil {
		return app.ExecutionResult{}, err
	}
	endpoint := *e.Origin
	endpoint.Path = "/internal/graphql"
	endpoint.RawPath = ""
	request, err := http.NewRequestWithContext(ctx, "POST", endpoint.String(), bytes.NewReader(payload))
	if err != nil {
		return app.ExecutionResult{}, err
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Contract-Graph-SHA256", e.GraphHash)
	requestID := fmt.Sprintf("collection-%d", time.Now().UnixNano())
	request.Header.Set("X-Request-ID", requestID)
	request.Header.Set("X-Client-Surface", "postCollection")
	principal, authenticated := auth.PrincipalFromContext(ctx)
	if authenticated && (principal.Actor.PersonaID == "" || principal.Actor.AccountID == "" || strings.HasPrefix(principal.Actor.AccountID, "service:")) {
		return app.ExecutionResult{}, app.ErrForbidden
	}
	if authenticated {
		if e.Authority == nil || e.SourceCredential == nil {
			return app.ExecutionResult{}, app.ErrOwnerUnavailable
		}
		source, err := e.SourceCredential(ctx)
		if err != nil || source == "" {
			return app.ExecutionResult{}, app.ErrForbidden
		}
		grant, err := e.Authority.Issue(ctx, source, auth.CollectionQueryBinding{OperationID: entry.CanonicalOperationID, CollectionID: id, PersistedHash: entry.SHA256Hash, BodyDigest: auth.DelegatedRequestDigest(payload), Method: "POST", Path: "/internal/graphql", Surface: "postCollection", RequestID: requestID})
		if err != nil {
			return app.ExecutionResult{}, app.ErrOwnerUnavailable
		}
		request.Header.Set("X-Collection-Query-Grant", grant.Grant)
	} else if management {
		return app.ExecutionResult{}, app.ErrForbidden
	}
	token, err := e.Credentials.AuthorizationHeader(ctx)
	if err != nil {
		return app.ExecutionResult{}, app.ErrOwnerUnavailable
	}
	request.Header.Set("Authorization", token)
	client := *e.Client
	client.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	response, err := client.Do(request)
	if err != nil {
		return app.ExecutionResult{}, app.ErrOwnerUnavailable
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return app.ExecutionResult{}, app.ErrOwnerUnavailable
	}
	if response.Header.Get("X-Contract-Graph-SHA256") != e.GraphHash {
		return app.ExecutionResult{}, app.ErrOwnerUnavailable
	}
	raw, err := io.ReadAll(io.LimitReader(response.Body, 262145))
	if err != nil || len(raw) > 262144 {
		return app.ExecutionResult{}, app.ErrOwnerUnavailable
	}
	root := "postCollection"
	if management {
		root = "postCollectionManagement"
	}
	data, err := decodeOwnerGraphQLData(raw, contentBundleBinding{rootField: root, response: collectionResponseSpec(management)})
	if err != nil || data["collectionId"] != id {
		return app.ExecutionResult{}, app.ErrOwnerUnavailable
	}
	result, err := json.Marshal(map[string]any{root: data})
	if err != nil {
		return app.ExecutionResult{}, err
	}
	return app.ExecutionResult{Data: result, Usage: app.ExecutionUsage{OwnerCalls: collectionOwnerCalls(authenticated), BatchKeys: 1, ResponseBytes: len(result)}}, nil
}
