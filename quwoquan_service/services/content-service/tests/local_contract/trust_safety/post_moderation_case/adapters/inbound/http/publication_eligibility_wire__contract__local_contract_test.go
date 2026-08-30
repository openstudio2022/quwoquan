// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-008
// readiness_case: get-post-publication-eligibility-local
//
// PostPublicationEligibility 的 inbound HTTP 契约证据。application 层用例断言
// 的是 PublicationEligibilitySlice 这个 Go 值，看不到 handler 之上的两层折算：
// query 参数到 int64 的解析，以及 slice 到 wire 的投影（omitempty 与 false
// 布尔的去留）。这两层漂移时端侧 decoder 会失配，而现有测试全绿。
//
// 用例只走同步的请求-应答路径：直接调用 handler 方法，不启动 outbox relay、
// 不推进时钟、不依赖 goroutine 调度，因此在任何宿主上执行的语句集合相同。
package http_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/runtime/commandmeta"
	mediacontract "quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport/media_contract"
	moderationhttp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/adapters/inbound/http"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
)

func TestPendingModerationCaseIsIneligibleOverPublicationEligibilityWire(t *testing.T) {
	t.Parallel()

	const (
		postID = "post-publication-eligibility-wire"
		digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	)
	service := moderationapp.NewModerationService(
		moderationapp.BindDataPorts(mediacontract.NewModerationStore()),
		moderationapp.WithClock(func() time.Time {
			return time.Date(2030, time.October, 11, 12, 13, 14, 0, time.UTC)
		}),
		moderationapp.WithIdentifierGenerator(func(string) (string, error) {
			return "pmc-eligibility-wire", nil
		}),
	)
	opened, err := service.OpenPostModerationCase(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			"open-publication-eligibility-wire",
		),
		moderationapp.OpenPostModerationCaseCommand{
			PostID: postID, PostVersion: 3, ContentDigest: digest,
		},
	)
	if err != nil {
		t.Fatalf("open moderation case fixture: %v", err)
	}

	handler := moderationhttp.NewHandler(moderationapp.BindFacades(service))
	request := httptest.NewRequest(
		http.MethodGet,
		"/internal/content/posts/"+postID+
			"/publication-eligibility?postVersion=3&contentDigest="+digest,
		nil,
	)
	request.SetPathValue("postId", postID)
	recorder := httptest.NewRecorder()
	handler.GetPublicationEligibility(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"publication eligibility status=%d want=%d body=%s",
			recorder.Code,
			http.StatusOK,
			recorder.Body.String(),
		)
	}
	var wire map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &wire); err != nil {
		t.Fatalf("decode publication eligibility wire: %v body=%s", err, recorder.Body.String())
	}

	// eligible 必须以显式 false 出现：拒绝发布是一个答案，不是「字段缺席」。
	eligible, present := wire["eligible"]
	if !present || eligible != false {
		t.Fatalf("pending case must answer eligible=false: %s", recorder.Body.String())
	}
	// 逐字段对齐 Open 命令的返回值：wire 上的 case 身份必须就是刚开出的那一个，
	// failureReason 必须原样透传而不是在投影时被吞掉。
	if wire["caseId"] != opened.CaseID ||
		wire["caseVersion"] != float64(opened.Version) ||
		wire["moderation"] != "pending" ||
		wire["failureReason"] != "moderation_approval_required" {
		t.Fatalf("publication eligibility wire drifted: %#v", wire)
	}
	// 未决案件没有决策时间，omitempty 必须让该键整体缺席，而不是写 zero time。
	if _, present := wire["decisionAt"]; present {
		t.Fatalf("pending case leaked decisionAt: %s", recorder.Body.String())
	}
	checkedAt, ok := wire["checkedAt"].(string)
	if !ok {
		t.Fatalf("publication eligibility wire has no checkedAt: %s", recorder.Body.String())
	}
	if _, err := time.Parse(time.RFC3339Nano, checkedAt); err != nil {
		t.Fatalf("checkedAt=%q is not an RFC3339 instant: %v", checkedAt, err)
	}
}
