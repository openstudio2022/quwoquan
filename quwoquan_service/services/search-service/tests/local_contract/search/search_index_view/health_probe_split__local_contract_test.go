package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

// TestSearchHealthProbeSplitKeepsDeepChecksOffLiveness 锁定探针语义分离：
// /healthz 的纯 liveness 与 /readyz 的依赖就绪由 servicekit 统一挂载，服务侧
// 只允许把依赖检查注册到 asm.Health（即 /readyz 的 checker）。把 ES、消费者或
// authority 检查挂到 liveness 上会让下游抖动直接触发容器重启。
func TestSearchHealthProbeSplitKeepsDeepChecksOffLiveness(t *testing.T) {
	t.Parallel()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve caller path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(thisFile), "../../../.."))
	bootstrapSource, err := os.ReadFile(filepath.Join(serviceRoot, "cmd/api/bootstrap.go"))
	if err != nil {
		t.Fatalf("read bootstrap.go: %v", err)
	}
	composeSource, err := os.ReadFile(filepath.Join(serviceRoot, "deploy/compose.yaml"))
	if err != nil {
		t.Fatalf("read compose.yaml: %v", err)
	}
	// 去空白后比对：断言的是装配契约，不是 gofmt 对参数换行的选择。
	bootstrapText := stripSearchProbeWhitespace(string(bootstrapSource))
	composeText := string(composeSource)

	if !strings.Contains(bootstrapText, `servicekit.Bootstrap(serviceName`) {
		t.Fatal("search-service must take its /healthz + /readyz split from servicekit.Bootstrap")
	}
	// 服务侧不得自建探针路由：那会绕过骨架的 liveness/readiness 分离与
	// admission 门，产出第二套探针语义。
	for _, forbidden := range []string{
		`HandleFunc("/healthz"`,
		`HandleFunc("/readyz"`,
		`Handle("/metrics"`,
	} {
		if strings.Contains(bootstrapText, forbidden) {
			t.Fatalf("probe route %s must stay owned by servicekit", forbidden)
		}
	}
	if !strings.Contains(
		bootstrapText,
		`ifreadiness:=built.ReadinessCheck();readiness!=nil{asm.Health.Register("elasticsearch",readiness)`,
	) {
		t.Fatal("search /readyz must register the functional Elasticsearch query check")
	}
	for _, deep := range []string{
		`asm.Health.Register("elasticsearch"`,
		`asm.Health.Register("experiment-policy-consumer"`,
		`asm.Health.Register("feedback-signal-relay"`,
		`asm.Health.Register("user-account-closed-consumer"`,
		`asm.Health.Register("user-account-restriction-consumer"`,
		`asm.Health.Register("user-profile-search-projection-consumer"`,
	} {
		if !strings.Contains(bootstrapText, deep) {
			t.Fatalf("deep readiness check must stay registered: %s", deep)
		}
	}

	// compose healthcheck 是 depends_on: service_healthy 的判据，必须停在浅层
	// /healthz：深层就绪要求上游依赖全部可用，而上游自身又在等下游 healthy，
	// 会形成级联启动死锁。深层就绪由 k8s readinessProbe 与环境编排消费。
	if !strings.Contains(composeText, "http://127.0.0.1:18095/healthz") {
		t.Fatal("compose healthcheck must probe shallow /healthz to avoid depends_on deadlock")
	}
	if strings.Contains(composeText, "http://127.0.0.1:18095/readyz") {
		t.Fatal("compose healthcheck must not probe deep /readyz")
	}
	if !strings.Contains(
		composeText,
		`QWQ_RELEASE_CANDIDATE_DIGEST: "${QWQ_RELEASE_CANDIDATE_DIGEST:?release candidate digest is required}"`,
	) {
		t.Fatal("compose must bind search cursors to the immutable release candidate")
	}
}

func stripSearchProbeWhitespace(source string) string {
	return strings.Join(strings.Fields(source), "")
}
