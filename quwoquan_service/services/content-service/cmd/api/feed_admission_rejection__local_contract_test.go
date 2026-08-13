// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
//
// CONTENT.SYSTEM.feed_capacity_unavailable 的唯一发射点是装配层的
// feed admission 拒绝 writer；本白盒测试真实调用生产 writer，锁定
// wire code、HTTP 状态与 Retry-After 语义。
package bootstrap

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rtgov "quwoquan_service/runtime/governance"
)

func TestWriteContentFeedAdmissionRejectionEmitsFeedCapacityUnavailable(t *testing.T) {
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/content/feed", nil)

	writeContentFeedAdmissionRejection(
		recorder,
		request,
		rtgov.OperationAdmissionInflightFull,
	)

	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf(
			"feed admission rejection status=%d want=%d body=%s",
			recorder.Code,
			http.StatusServiceUnavailable,
			recorder.Body.String(),
		)
	}
	if !strings.Contains(
		recorder.Body.String(),
		`"code":"CONTENT.SYSTEM.feed_capacity_unavailable"`,
	) {
		t.Fatalf(
			"feed admission rejection must carry the declared wire code: %s",
			recorder.Body.String(),
		)
	}
	if recorder.Header().Get("Retry-After") != "1" {
		t.Fatalf(
			"feed admission rejection must advertise Retry-After=1, got %q",
			recorder.Header().Get("Retry-After"),
		)
	}
}
