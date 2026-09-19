// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#sit-003
package recommendation_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"

	transport "quwoquan_service/services/content-service/generated/content/feed_delivery_page"
	recommendation "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/recommendation"
)

// capturedContract 记录服务端真正收到的 body 能力声明。窗口能力只能来自 body，
// 缺席会让对端退回固定基线，与首刷不再是同一个窗口。
func capturedContract(
	t *testing.T,
	body map[string]json.RawMessage,
) transport.ClientContentPresentationContract {
	t.Helper()
	raw, present := body["clientPresentationContract"]
	if !present {
		t.Fatalf("request body does not carry clientPresentationContract: %v", body)
	}
	contract, err := transport.DecodeClientContentPresentationContract(raw)
	if err != nil {
		t.Fatalf("decode carried contract: %v", err)
	}
	return contract
}

func declaredMediaContract(t *testing.T) transport.ClientContentPresentationContract {
	t.Helper()
	contract := transport.ClientContentPresentationContract{
		ContentTypes:        []transport.ContentType{"image", "video"},
		ListObjectKinds:     []transport.ListObjectKind{"post"},
		OpenSurfaces:        []transport.ContentUiSurface{"media_immersive"},
		PresentationRecipes: []transport.FeedPresentationRecipe{"cover_media_card"},
	}
	digest, err := transport.DigestClientContentPresentationContract(contract)
	if err != nil {
		t.Fatalf("digest contract: %v", err)
	}
	contract.ContractDigest = digest
	return contract
}

func mediaRankedPageWire(
	windowID string,
	contract transport.ClientContentPresentationContract,
) map[string]any {
	payload := rankedPageWire(windowID, 0)
	payload["clientPresentationContract"] = contract
	payload["items"] = []map[string]any{{
		"ordinal": 0,
		"envelope": map[string]any{
			"objectKind": "post", "contentType": "image", "openSurface": "media_immersive",
			"post": map[string]any{"postId": "post-1"},
		},
		"score":                 1.0,
		"featureSnapshotDigest": strings.Repeat("b", 64),
		"itemFeatureSnapshot":   map[string]any{"qualityScore": 1.0},
	}}
	return payload
}

func TestHTTPClientCarriesClientPresentationContractOnCreateAndGetPage(t *testing.T) {
	contract := declaredMediaContract(t)
	var createBody, pageBody map[string]json.RawMessage
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		var body map[string]json.RawMessage
		if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
			t.Fatalf("decode body: %v", err)
		}
		if request.URL.Path == transport.CreateRankedRecommendationWindowPath {
			createBody = body
		} else {
			pageBody = body
			if _, leaked := body["windowId"]; leaked {
				t.Fatalf("path window identity leaked into query body: %v", body)
			}
		}
		writer.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(writer).Encode(
			mediaRankedPageWire("window-contract", contract),
		); err != nil {
			t.Fatalf("encode response: %v", err)
		}
	}))
	defer server.Close()

	client, err := recommendation.NewHTTPClient(server.URL, staticCredentials{})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}
	if _, err := client.Create(context.Background(), transport.CreateRankedRecommendationWindowCommand{
		IdempotencyKey:             "feed-request-contract",
		SubjectId:                  "subject-contract",
		Scenario:                   "content_feed",
		ClientPresentationContract: contract,
		Limit:                      20,
	}); err != nil {
		t.Fatalf("create: %v", err)
	}
	fromOrdinal := 0
	limit := 20
	if _, err := client.GetPage(context.Background(), transport.GetRankedRecommendationPageQuery{
		SubjectId:                  "subject-contract",
		WindowId:                   "window-contract",
		ClientPresentationContract: contract,
		FromOrdinal:                &fromOrdinal,
		Limit:                      &limit,
	}); err != nil {
		t.Fatalf("get page: %v", err)
	}

	for name, body := range map[string]map[string]json.RawMessage{
		"create":  createBody,
		"getPage": pageBody,
	} {
		if got := capturedContract(t, body); !reflect.DeepEqual(got, contract) {
			t.Fatalf("%s body contract\n got: %+v\nwant: %+v", name, got, contract)
		}
	}
}

// 建窗与续页都不接受零值或伪造摘要的能力：窗口身份不能建立在无法重算的声明上。
func TestHTTPClientRejectsUnverifiableOutboundPresentationContract(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("unverifiable outbound contract must never reach the wire")
	}))
	defer server.Close()

	client, err := recommendation.NewHTTPClient(server.URL, staticCredentials{})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}
	forged := declaredMediaContract(t)
	forged.ContractDigest = "sha256:" + strings.Repeat("0", 64)
	fromOrdinal := 0
	limit := 20
	for name, call := range map[string]func(transport.ClientContentPresentationContract) error{
		"create": func(contract transport.ClientContentPresentationContract) error {
			_, callErr := client.Create(context.Background(), transport.CreateRankedRecommendationWindowCommand{
				IdempotencyKey:             "feed-request-forged",
				SubjectId:                  "subject-forged",
				Scenario:                   "content_feed",
				ClientPresentationContract: contract,
				Limit:                      20,
			})
			return callErr
		},
		"getPage": func(contract transport.ClientContentPresentationContract) error {
			_, callErr := client.GetPage(context.Background(), transport.GetRankedRecommendationPageQuery{
				SubjectId:                  "subject-forged",
				WindowId:                   "window-forged",
				ClientPresentationContract: contract,
				FromOrdinal:                &fromOrdinal,
				Limit:                      &limit,
			})
			return callErr
		},
	} {
		t.Run(name+"/absent", func(t *testing.T) {
			if err := call(transport.ClientContentPresentationContract{}); err == nil {
				t.Fatal("zero-value presentation contract must be rejected")
			}
		})
		t.Run(name+"/forged", func(t *testing.T) {
			if err := call(forged); err == nil {
				t.Fatal("forged presentation contract digest must be rejected")
			}
		})
	}
}

func TestHTTPClientRejectsWindowWhoseEchoedContractIsUnverifiable(t *testing.T) {
	contract := declaredMediaContract(t)
	echoed := contract
	echoed.ContractDigest = "sha256:" + strings.Repeat("1", 64)
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		writer.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(writer).Encode(
			mediaRankedPageWire("window-echoed", echoed),
		); err != nil {
			t.Fatalf("encode response: %v", err)
		}
	}))
	defer server.Close()

	client, err := recommendation.NewHTTPClient(server.URL, staticCredentials{})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}
	if _, err := client.Create(context.Background(), transport.CreateRankedRecommendationWindowCommand{
		IdempotencyKey:             "feed-request-echoed",
		SubjectId:                  "subject-echoed",
		Scenario:                   "content_feed",
		ClientPresentationContract: contract,
		Limit:                      20,
	}); err == nil || !strings.Contains(err.Error(), "presentation contract is invalid") {
		t.Fatalf("self-inconsistent echoed contract must be rejected: %v", err)
	}
}

// 窗口条目不得越过窗口自己声明的能力：越界条目让整个窗口 fail-closed，
// 不能靠读侧静默丢弃兜底。
func TestHTTPClientRejectsItemOutsideEchoedPresentationContract(t *testing.T) {
	contract := declaredMediaContract(t)
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		payload := mediaRankedPageWire("window-out-of-contract", contract)
		payload["items"] = []map[string]any{{
			"ordinal": 0,
			"envelope": map[string]any{
				"objectKind": "post", "contentType": "article", "openSurface": "article_reader",
				"post": map[string]any{"postId": "post-article"},
			},
			"score":                 1.0,
			"featureSnapshotDigest": strings.Repeat("b", 64),
			"itemFeatureSnapshot":   map[string]any{"qualityScore": 1.0},
		}}
		writer.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(writer).Encode(payload); err != nil {
			t.Fatalf("encode response: %v", err)
		}
	}))
	defer server.Close()

	client, err := recommendation.NewHTTPClient(server.URL, staticCredentials{})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}
	if _, err := client.Create(context.Background(), transport.CreateRankedRecommendationWindowCommand{
		IdempotencyKey:             "feed-request-out-of-contract",
		SubjectId:                  "subject-out-of-contract",
		Scenario:                   "content_feed",
		ClientPresentationContract: contract,
		Limit:                      20,
	}); err == nil || !strings.Contains(err.Error(), "outside the window presentation contract") {
		t.Fatalf("out-of-contract item must be rejected: %v", err)
	}
}
