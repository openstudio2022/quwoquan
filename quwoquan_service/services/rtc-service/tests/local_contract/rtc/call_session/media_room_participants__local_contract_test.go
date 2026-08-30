package local_contract

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/livekit"
)

// 房间参与者快照是 JoinCall 判定「房间是否已被账号安全销毁」的唯一依据，
// 因此供应商 state 编码必须在 adapter 边界折成中立字面量，不能把数字外泄给应用层。
func TestMediaRoomListParticipantsMapsProviderStateToCanonicalSnapshot(t *testing.T) {
	var path, authorization string
	var request map[string]any
	upstream := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			path = r.URL.Path
			authorization = r.Header.Get("Authorization")
			_ = json.NewDecoder(r.Body).Decode(&request)
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"participants":[` +
				`{"identity":"caller","sid":"PA_1","state":0},` +
				`{"identity":"callee","sid":"PA_2","state":1},` +
				`{"identity":"observer","sid":"PA_3","state":3}` +
				`]}`))
		},
	))
	t.Cleanup(upstream.Close)

	rooms := application.NewRoomService(
		livekit.NewLiveKitRoomAdapter(upstream.URL, "api-key", "api-secret"),
	)
	participants, err := rooms.ListParticipants(context.Background(), "call-123")
	if err != nil {
		t.Fatalf("ListParticipants() error = %v", err)
	}
	if path != "/twirp/livekit.RoomService/ListParticipants" {
		t.Fatalf("TWIRP path = %q", path)
	}
	if request["room"] != "call-123" {
		t.Fatalf("request body = %v, want room=call-123", request)
	}
	// 管理令牌由 adapter 自己签发；缺了它供应商会静默返回空房间，
	// 而空房间恰好与「房间已销毁」同形，撤销判定就会失效。
	if !strings.HasPrefix(authorization, "Bearer ") {
		t.Fatalf("admin authorization = %q", authorization)
	}
	want := []application.RoomParticipant{
		{Identity: "caller", SID: "PA_1", State: "ACTIVE"},
		{Identity: "callee", SID: "PA_2", State: "JOINING"},
		{Identity: "observer", SID: "PA_3", State: "DISCONNECTED"},
	}
	if len(participants) != len(want) {
		t.Fatalf("participants = %+v, want %+v", participants, want)
	}
	for index, participant := range participants {
		if participant != want[index] {
			t.Fatalf("participant[%d] = %+v, want %+v", index, participant, want[index])
		}
	}
}

func TestMediaRoomListParticipantsFailsClosedOnRevokedRoom(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"code":"not_found","msg":"provider diagnostic must remain private"}`))
		},
	))
	t.Cleanup(upstream.Close)

	rooms := application.NewRoomService(
		livekit.NewLiveKitRoomAdapter(upstream.URL, "api-key", "api-secret"),
	)
	participants, err := rooms.ListParticipants(context.Background(), "call-123")
	if err == nil {
		t.Fatal("revoked room must not resolve as a readable room")
	}
	// 房间已撤销是「失败」不是「在场为空」：塌陷成空切片会让 JoinCall
	// 把被账号安全销毁的房间当成可重建的空房间。
	if participants != nil {
		t.Fatalf("failed lookup returned %#v, want nil", participants)
	}
	if !strings.Contains(err.Error(), "status=404") ||
		!strings.Contains(err.Error(), "body_digest=") {
		t.Fatalf("bounded provider error = %v", err)
	}
	if strings.Contains(err.Error(), "provider diagnostic") {
		t.Fatalf("provider payload leaked through adapter: %v", err)
	}
}

func TestMediaRoomRemoveParticipantCarriesRoomAndIdentity(t *testing.T) {
	var path string
	var request map[string]any
	upstream := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			path = r.URL.Path
			_ = json.NewDecoder(r.Body).Decode(&request)
			_, _ = w.Write([]byte(`{}`))
		},
	))
	t.Cleanup(upstream.Close)

	rooms := application.NewRoomService(
		livekit.NewLiveKitRoomAdapter(upstream.URL, "api-key", "api-secret"),
	)
	if err := rooms.RemoveParticipant(context.Background(), "call-123", "callee"); err != nil {
		t.Fatalf("RemoveParticipant() error = %v", err)
	}
	if path != "/twirp/livekit.RoomService/RemoveParticipant" {
		t.Fatalf("TWIRP path = %q", path)
	}
	// 房间与身份是两个独立入参，一旦对调就会把留在通话里的人踢出去。
	if request["room"] != "call-123" || request["identity"] != "callee" {
		t.Fatalf("request body = %v, want room=call-123 identity=callee", request)
	}
}

func TestMediaRoomParticipantAccessBindsIdentityIntoSignedGrant(t *testing.T) {
	const apiKey, apiSecret = "api-key", "api-secret"
	adapter := livekit.NewLiveKitRoomAdapter("wss://rtc.example.test", apiKey, apiSecret)

	access, err := adapter.IssueParticipantAccess(
		context.Background(),
		"call-123",
		"callee",
	)
	if err != nil {
		t.Fatalf("IssueParticipantAccess() error = %v", err)
	}
	segments := strings.Split(access.AccessToken, ".")
	if len(segments) != 3 {
		t.Fatalf("access token segments = %d, want 3", len(segments))
	}
	// 令牌未经本服务密钥签名就等于任何人都能进任意房间，
	// 因此签名必须在这里重算比对，而不是只看令牌形状。
	mac := hmac.New(sha256.New, []byte(apiSecret))
	mac.Write([]byte(segments[0] + "." + segments[1]))
	if segments[2] != base64.RawURLEncoding.EncodeToString(mac.Sum(nil)) {
		t.Fatal("access token signature does not verify against the service secret")
	}
	claimsJSON, err := base64.RawURLEncoding.DecodeString(segments[1])
	if err != nil {
		t.Fatalf("decode claims: %v", err)
	}
	var claims struct {
		ISS   string `json:"iss"`
		SUB   string `json:"sub"`
		IAT   int64  `json:"iat"`
		EXP   int64  `json:"exp"`
		Video struct {
			Room       string `json:"room"`
			RoomJoin   bool   `json:"roomJoin"`
			RoomCreate bool   `json:"roomCreate"`
			RoomAdmin  bool   `json:"roomAdmin"`
		} `json:"video"`
	}
	if err := json.Unmarshal(claimsJSON, &claims); err != nil {
		t.Fatalf("unmarshal claims: %v", err)
	}
	if claims.ISS != apiKey || claims.SUB != "callee" ||
		claims.Video.Room != "call-123" || !claims.Video.RoomJoin {
		t.Fatalf("participant grant = %+v", claims)
	}
	// 参与者令牌拿到房间管理权就能删除房间或踢人，权限必须止步于 join。
	if claims.Video.RoomCreate || claims.Video.RoomAdmin {
		t.Fatalf("participant grant carries admin privileges: %+v", claims.Video)
	}
	if claims.EXP-claims.IAT != int64(6*time.Hour/time.Second) {
		t.Fatalf("grant lifetime = %ds, want 6h", claims.EXP-claims.IAT)
	}
}
