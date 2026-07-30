package api_integration

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sort"
	"strings"
	"sync"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
	greetingapplication "quwoquan_service/services/user-service/internal/relationship/greeting_request/application"
)

type chatServiceContractRuntime struct {
	server        *httptest.Server
	mu            sync.Mutex
	conversations map[string]string
	// promotions 记录每个会话最后一次收到的破冰升级上下文，用于断言生产客户端
	// 真的把 greetingRequestId 与那句话送到了 Chat（不是本地丢弃）。
	promotions map[string]directPromotionRecord
	verifier   *rtauth.Verifier
}

type directPromotionRecord struct {
	GreetingRequestID string
	OpeningMessage    string
}

// 返回生产客户端本体：它同时实现账号编排口（CreateOrReuseDirect）与打招呼升级口
// （PromoteGreetingToDirect），两条内部调用必须在同一个客户端上都被验证。
func startChatServiceContractRuntime() (*chatServiceContractRuntime, *integration.ChatServiceClient) {
	credentials, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		testAccessConfig,
		"user-service",
		[]string{"chat.conversation.internal_direct"},
	)
	if err != nil {
		panic(err)
	}
	runtime := &chatServiceContractRuntime{
		conversations: make(map[string]string),
		promotions:    make(map[string]directPromotionRecord),
		verifier:      testAccessVerifier,
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/internal/chat/conversations/direct", runtime.handleDirectConversation)
	runtime.server = httptest.NewServer(mux)
	client, err := integration.NewAuthorizedChatServiceClient(
		runtime.server.URL,
		runtime.server.Client(),
		credentials,
	)
	if err != nil {
		panic(err)
	}
	return runtime, client
}

func (runtime *chatServiceContractRuntime) Close() {
	if runtime != nil && runtime.server != nil {
		runtime.server.Close()
	}
}

func (runtime *chatServiceContractRuntime) Reset() {
	runtime.mu.Lock()
	defer runtime.mu.Unlock()
	runtime.conversations = make(map[string]string)
	runtime.promotions = make(map[string]directPromotionRecord)
}

func (runtime *chatServiceContractRuntime) promotionFor(left, right string) (directPromotionRecord, bool) {
	runtime.mu.Lock()
	defer runtime.mu.Unlock()
	record, ok := runtime.promotions[directConversationPairKey(left, right)]
	return record, ok
}

func (runtime *chatServiceContractRuntime) handleDirectConversation(writer http.ResponseWriter, request *http.Request) {
	switch request.Method {
	case http.MethodPost:
		var input struct {
			CreatorID         string `json:"creatorId"`
			PeerID            string `json:"peerId"`
			GreetingRequestID string `json:"greetingRequestId"`
			OpeningMessage    string `json:"openingMessage"`
		}
		decoder := json.NewDecoder(request.Body)
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&input); err != nil ||
			strings.TrimSpace(input.CreatorID) == "" ||
			strings.TrimSpace(input.PeerID) == "" {
			http.Error(writer, "invalid direct conversation request", http.StatusBadRequest)
			return
		}
		if !runtime.hasDelegatedUserServicePersona(request, input.CreatorID) {
			http.Error(writer, "delegated internal attribution required", http.StatusUnauthorized)
			return
		}
		if strings.TrimSpace(input.OpeningMessage) != "" &&
			strings.TrimSpace(input.GreetingRequestID) == "" {
			// 与 chat-service 内部路由同一判定：没有打招呼来源就不许带首条消息。
			http.Error(writer, "openingMessage requires greetingRequestId", http.StatusBadRequest)
			return
		}
		key := directConversationPairKey(input.CreatorID, input.PeerID)
		runtime.mu.Lock()
		conversationID := runtime.conversations[key]
		if conversationID == "" {
			conversationID = "conv_" + stableProviderSuffix(key)
			runtime.conversations[key] = conversationID
		}
		if strings.TrimSpace(input.GreetingRequestID) != "" {
			runtime.promotions[key] = directPromotionRecord{
				GreetingRequestID: input.GreetingRequestID,
				OpeningMessage:    input.OpeningMessage,
			}
		}
		runtime.mu.Unlock()
		writeJSON(writer, map[string]any{"conversationId": conversationID})
	case http.MethodGet:
		memberA := strings.TrimSpace(request.URL.Query().Get("memberA"))
		memberB := strings.TrimSpace(request.URL.Query().Get("memberB"))
		if memberA == "" || memberB == "" {
			http.Error(writer, "invalid direct conversation lookup", http.StatusBadRequest)
			return
		}
		if !runtime.hasDelegatedUserServicePersona(request, memberA) {
			http.Error(writer, "delegated internal attribution required", http.StatusUnauthorized)
			return
		}
		runtime.mu.Lock()
		_, exists := runtime.conversations[directConversationPairKey(memberA, memberB)]
		runtime.mu.Unlock()
		if !exists {
			http.Error(writer, "not found", http.StatusNotFound)
			return
		}
		writeJSON(writer, map[string]any{"exists": true})
	default:
		http.Error(writer, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (runtime *chatServiceContractRuntime) hasDelegatedUserServicePersona(
	request *http.Request,
	personaID string,
) bool {
	if runtime == nil || runtime.verifier == nil {
		return false
	}
	if strings.TrimSpace(request.Header.Get("X-Internal-Service")) != "" ||
		strings.TrimSpace(request.Header.Get("X-Client-User-Id")) != "" {
		return false
	}
	token := strings.TrimSpace(strings.TrimPrefix(
		request.Header.Get("Authorization"),
		"Bearer ",
	))
	claims, err := runtime.verifier.Verify(token)
	if err != nil ||
		claims.Subject != "service:user-service" ||
		claims.Persona != personaID ||
		!strings.Contains(" "+claims.Scope+" ", " chat.conversation.internal_direct ") {
		return false
	}
	return strings.Contains(" "+strings.Join(claims.Roles, " ")+" ", " service ")
}

func directConversationPairKey(left, right string) string {
	members := []string{strings.TrimSpace(left), strings.TrimSpace(right)}
	sort.Strings(members)
	return fmt.Sprintf("%s:%s", members[0], members[1])
}

func TestChatServiceContractRuntime_ProductionClientPreservesDirectConversation(t *testing.T) {
	if conversationGateway == nil {
		t.Fatal("chat service contract runtime is not initialized")
	}
	conversationID, err := conversationGateway.CreateOrReuseDirect(
		t.Context(), "sa_contract_a", "sa_contract_b")
	if err != nil {
		t.Fatalf("create direct conversation through production client: %v", err)
	}
	if conversationID == "" {
		t.Fatal("expected conversationId")
	}
	exists, err := conversationGateway.HasDirectBetween(t.Context(), "sa_contract_b", "sa_contract_a")
	if err != nil {
		t.Fatalf("lookup direct conversation through production client: %v", err)
	}
	if !exists {
		t.Fatal("expected direct conversation lookup to converge")
	}
}

// 打招呼被回复时，生产客户端必须把破冰上下文一起送到 Chat：
// greetingRequestId 决定会话来源归因，openingMessage 决定回复方打开会话时
// 能不能看到对方当初说的那句话。少任何一个，「同意」之后就是一个空会话。
func TestChatServiceContractRuntime_GreetingPromotionCarriesOpeningMessage(t *testing.T) {
	if conversationGateway == nil {
		t.Fatal("chat service contract runtime is not initialized")
	}
	var greetingGateway greetingapplication.ConversationGateway = conversationGateway
	conversationID, err := greetingGateway.PromoteGreetingToDirect(
		t.Context(),
		"sa_promote_target",
		"sa_promote_requester",
		greetingapplication.GreetingPromotion{
			GreetingRequestID: "greet_promote_1",
			OpeningMessage:    "你也去过老君山？下次拼个车",
		},
	)
	if err != nil {
		t.Fatalf("promote greeting through production client: %v", err)
	}
	if conversationID == "" {
		t.Fatal("expected conversationId from greeting promotion")
	}
	record, found := chatContractRuntime.promotionFor("sa_promote_target", "sa_promote_requester")
	if !found {
		t.Fatal("chat runtime never received the greeting promotion context")
	}
	if record.GreetingRequestID != "greet_promote_1" {
		t.Fatalf("greetingRequestId = %q, want greet_promote_1", record.GreetingRequestID)
	}
	if record.OpeningMessage != "你也去过老君山？下次拼个车" {
		t.Fatalf("openingMessage must reach chat verbatim, got %q", record.OpeningMessage)
	}
}
