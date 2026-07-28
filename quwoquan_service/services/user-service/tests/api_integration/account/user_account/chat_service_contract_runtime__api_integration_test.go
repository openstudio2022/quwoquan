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
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
)

type chatServiceContractRuntime struct {
	server        *httptest.Server
	mu            sync.Mutex
	conversations map[string]string
	verifier      *rtauth.Verifier
}

func startChatServiceContractRuntime() (*chatServiceContractRuntime, application.ConversationGateway) {
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
}

func (runtime *chatServiceContractRuntime) handleDirectConversation(writer http.ResponseWriter, request *http.Request) {
	switch request.Method {
	case http.MethodPost:
		var input struct {
			CreatorID string `json:"creatorId"`
			PeerID    string `json:"peerId"`
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
		key := directConversationPairKey(input.CreatorID, input.PeerID)
		runtime.mu.Lock()
		conversationID := runtime.conversations[key]
		if conversationID == "" {
			conversationID = "conv_" + stableProviderSuffix(key)
			runtime.conversations[key] = conversationID
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
	conversationID, err := conversationGateway.CreateOrReuseDirect(t.Context(), "sa_contract_a", "sa_contract_b")
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
