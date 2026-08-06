// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/content-action-intent-contract/spec.md#gwt-001
// readiness_case: list-my-reports-local
// readiness_case: grant-gathering-safety-termination-local
// readiness_case: revoke-gathering-safety-termination-local
// readiness_case: authorize-gathering-safety-termination-local
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003
package report_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/commandmeta"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
	reportapp "quwoquan_service/services/content-service/internal/trust_safety/report/application"
	reportmodel "quwoquan_service/services/content-service/internal/trust_safety/report/domain/model"
	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
)

func TestReportCommandAndQueryFacetsStaySeparated(t *testing.T) {
	t.Parallel()

	store := testsupport.NewReportStore()
	service := reportapp.NewReportService(reportapp.BindDataPorts(store))
	createCommand := reportapp.CreateReportCommand{
		ReporterID:        "persona-reporter",
		ReporterAccountID: "account-reporter",
		TargetType:        reportmodel.TargetPost,
		TargetID:          "post-1",
		Reason:            reportmodel.ReasonSpam,
		Description:       "重复广告",
	}

	createContext := commandmeta.WithIdempotencyKey(
		context.Background(),
		"create-report-1",
	)
	created, err := service.CreateReport(createContext, createCommand)
	if err != nil {
		t.Fatalf("create report: %v", err)
	}
	replayed, err := service.CreateReport(createContext, createCommand)
	if err != nil {
		t.Fatalf("replay create report: %v", err)
	}
	if !replayed.Replayed ||
		replayed.ID != created.ID ||
		replayed.Version != created.Version {
		t.Fatalf("unexpected idempotent replay: %+v vs %+v", replayed, created)
	}
	_, err = service.CreateReport(
		createContext,
		reportapp.CreateReportCommand{
			ReporterID:        createCommand.ReporterID,
			ReporterAccountID: createCommand.ReporterAccountID,
			TargetType:        createCommand.TargetType,
			TargetID:          createCommand.TargetID,
			Reason:            createCommand.Reason,
			Description:       "不同的命令摘要",
		},
	)
	if err == nil || !strings.Contains(err.Error(), "idempotency_conflict") {
		t.Fatalf("different command must preserve idempotency conflict, got %v", err)
	}

	detail, err := service.GetReport(
		context.Background(),
		reportapp.GetReportQuery{ReportID: created.ID},
	)
	if err != nil {
		t.Fatalf("query report detail: %v", err)
	}
	if detail.ID != created.ID ||
		detail.Status != reportmodel.StatusPending ||
		detail.ReporterID != createCommand.ReporterID {
		t.Fatalf("unexpected detail slice: %+v", detail)
	}

	if _, err := service.Resolve(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			"resolve-pending-report-1",
		),
		reportapp.ResolveReportCommand{
			ReportID:   created.ID,
			ReviewerID: "persona-reviewer",
			Resolution: reportmodel.ResolutionDeleteContent,
		},
	); err == nil {
		t.Fatal("pending report must not skip the begin-review command")
	}

	reviewContext := commandmeta.WithIdempotencyKey(
		context.Background(),
		"begin-review-report-1",
	)
	reviewCommand := reportapp.BeginReviewReportCommand{
		ReportID:   created.ID,
		ReviewerID: "persona-reviewer",
	}
	reviewing, err := service.BeginReview(
		reviewContext,
		reviewCommand,
	)
	if err != nil {
		t.Fatalf("begin review: %v", err)
	}
	if reviewing.Version != 2 ||
		reviewing.Status != reportmodel.StatusReviewing {
		t.Fatalf("unexpected reviewing result: %+v", reviewing)
	}
	replayedReview, err := service.BeginReview(reviewContext, reviewCommand)
	if err != nil {
		t.Fatalf("replay begin review: %v", err)
	}
	if !replayedReview.Replayed ||
		replayedReview.ID != reviewing.ID ||
		replayedReview.Version != reviewing.Version {
		t.Fatalf("unexpected begin-review replay: %+v vs %+v", replayedReview, reviewing)
	}

	resolveContext := commandmeta.WithIdempotencyKey(
		context.Background(),
		"resolve-report-1",
	)
	resolveCommand := reportapp.ResolveReportCommand{
		ReportID:   created.ID,
		ReviewerID: "persona-reviewer",
		Resolution: reportmodel.ResolutionDeleteContent,
	}
	resolved, err := service.Resolve(
		resolveContext,
		resolveCommand,
	)
	if err != nil {
		t.Fatalf("resolve report: %v", err)
	}
	if resolved.Version != 3 || resolved.Status != reportmodel.StatusResolved {
		t.Fatalf("unexpected resolved result: %+v", resolved)
	}
	replayedResolve, err := service.Resolve(resolveContext, resolveCommand)
	if err != nil {
		t.Fatalf("replay resolve report: %v", err)
	}
	if !replayedResolve.Replayed ||
		replayedResolve.ID != resolved.ID ||
		replayedResolve.Version != resolved.Version {
		t.Fatalf("unexpected resolve replay: %+v vs %+v", replayedResolve, resolved)
	}

	queue, err := service.ListReports(
		context.Background(),
		reportapp.ListReportsQuery{Limit: 20},
	)
	if err != nil {
		t.Fatalf("query report queue: %v", err)
	}
	if queue.Total != 1 ||
		len(queue.Items) != 1 ||
		queue.Items[0].Status != reportmodel.StatusResolved {
		t.Fatalf("unexpected queue slice: %+v", queue)
	}
}

func TestDismissReportClosesLifecycleAndObservesSLO(t *testing.T) {
	t.Parallel()

	store := testsupport.NewReportStore()
	observer := &recordingReportObserver{}
	service := reportapp.NewReportService(
		reportapp.BindDataPorts(store),
		reportapp.WithLifecycleObserver(observer),
	)
	created, err := service.CreateReport(
		commandmeta.WithIdempotencyKey(context.Background(), "dismiss-create"),
		reportapp.CreateReportCommand{
			ReporterID:        "persona-reporter",
			ReporterAccountID: "account-reporter",
			TargetType:        reportmodel.TargetPost,
			TargetID:          "post-dismiss",
			Reason:            reportmodel.ReasonSpam,
		},
	)
	if err != nil {
		t.Fatalf("create report: %v", err)
	}
	if _, err := service.BeginReview(
		commandmeta.WithIdempotencyKey(context.Background(), "dismiss-review"),
		reportapp.BeginReviewReportCommand{
			ReportID: created.ID, ReviewerID: "operator-1",
		},
	); err != nil {
		t.Fatalf("begin report review: %v", err)
	}
	dismissed, err := service.Dismiss(
		commandmeta.WithIdempotencyKey(context.Background(), "dismiss-close"),
		reportapp.DismissReportCommand{
			ReportID: created.ID, ReviewerID: "operator-1",
		},
	)
	if err != nil {
		t.Fatalf("dismiss report: %v", err)
	}
	if dismissed.Status != reportmodel.StatusDismissed {
		t.Fatalf("status=%s want dismissed", dismissed.Status)
	}
	if observer.created != 1 ||
		len(observer.closed) != 1 ||
		observer.closed[0] != string(reportmodel.StatusDismissed) {
		t.Fatalf("unexpected lifecycle observation: %+v", observer)
	}
}

type recordingReportObserver struct {
	created int
	closed  []string
}

func (observer *recordingReportObserver) ReportCreated(context.Context) {
	observer.created++
}

func (observer *recordingReportObserver) ReportClosed(
	_ context.Context,
	status string,
	_ time.Time,
	_ time.Time,
) {
	observer.closed = append(observer.closed, status)
}

// TestReportNoopIntentPersistsReceiptBeforeLaterStateChange 锁定命名状态
// 迁移的 no-op 规则（design.md）：目标状态已满足的首个 Idempotency-Key 仍持久化
// no-op receipt（不递增版本、不产伪事实事件），后续状态继续演进后同 key 仍只
// 重放该次 no-op 的原始结果。
func TestReportNoopIntentPersistsReceiptBeforeLaterStateChange(t *testing.T) {
	t.Parallel()

	store := testsupport.NewReportStore()
	service := reportapp.NewReportService(reportapp.BindDataPorts(store))
	created, err := service.CreateReport(
		commandmeta.WithIdempotencyKey(context.Background(), "noop-report-create"),
		reportapp.CreateReportCommand{
			ReporterID:        "persona-reporter",
			ReporterAccountID: "account-reporter",
			TargetType:        reportmodel.TargetPost,
			TargetID:          "post-noop",
			Reason:            reportmodel.ReasonSpam,
			Description:       "no-op receipt 契约",
		},
	)
	if err != nil {
		t.Fatalf("create report: %v", err)
	}
	begin := reportapp.BeginReviewReportCommand{
		ReportID:   created.ID,
		ReviewerID: "operator-1",
	}
	first, err := service.BeginReview(
		commandmeta.WithIdempotencyKey(context.Background(), "noop-begin-first"),
		begin,
	)
	if err != nil {
		t.Fatalf("begin review: %v", err)
	}
	// 目标状态（reviewing/operator-1）已满足：新 key 的首次到达持久化 no-op
	// receipt，返回当前版本且不递增。
	noopContext := commandmeta.WithIdempotencyKey(
		context.Background(),
		"noop-begin-second",
	)
	noop, err := service.BeginReview(noopContext, begin)
	if err != nil {
		t.Fatalf("record begin-review no-op: %v", err)
	}
	if noop.Replayed || noop.Version != first.Version {
		t.Fatalf("first no-op must persist its current result: %+v vs %+v", noop, first)
	}
	// 状态继续演进（resolve）。
	resolve := reportapp.ResolveReportCommand{
		ReportID:   created.ID,
		ReviewerID: "operator-1",
		Resolution: reportmodel.ResolutionDeleteContent,
	}
	resolved, err := service.Resolve(
		commandmeta.WithIdempotencyKey(context.Background(), "noop-resolve-first"),
		resolve,
	)
	if err != nil {
		t.Fatalf("resolve report: %v", err)
	}
	// 同一 no-op key 重放：必须返回原 no-op 结果（reviewing 版本），
	// 而不是演进后的 resolved 状态。
	replayed, err := service.BeginReview(noopContext, begin)
	if err != nil {
		t.Fatalf("replay begin-review no-op: %v", err)
	}
	if !replayed.Replayed || replayed.Version != noop.Version {
		t.Fatalf("no-op retry must replay its original result: %+v", replayed)
	}
	// resolve 的目标状态已满足（同 reviewer 同 resolution）：no-op receipt。
	resolveNoop, err := service.Resolve(
		commandmeta.WithIdempotencyKey(context.Background(), "noop-resolve-second"),
		resolve,
	)
	if err != nil {
		t.Fatalf("record resolve no-op: %v", err)
	}
	if resolveNoop.Replayed || resolveNoop.Version != resolved.Version {
		t.Fatalf("resolve no-op must persist current result: %+v vs %+v", resolveNoop, resolved)
	}
}

func TestReportCommandRequiresTransportIdempotencyContext(t *testing.T) {
	t.Parallel()

	store := testsupport.NewReportStore()
	service := reportapp.NewReportService(reportapp.BindDataPorts(store))
	_, err := service.CreateReport(
		context.Background(),
		reportapp.CreateReportCommand{
			ReporterID:        "persona-reporter",
			ReporterAccountID: "account-reporter",
			TargetType:        reportmodel.TargetPost,
			TargetID:          "post-1",
			Reason:            reportmodel.ReasonSpam,
		},
	)
	if err == nil {
		t.Fatal("command without idempotency context must fail")
	}
}

func TestListMyReportsReturnsOnlyVerifiedPersonaReports(t *testing.T) {
	t.Parallel()

	store := testsupport.NewReportStore()
	service := reportapp.NewReportService(reportapp.BindDataPorts(store))
	facade := reportapp.BindFacades(service)
	create := func(key, reporterID, targetID string) {
		t.Helper()
		if _, err := service.CreateReport(
			commandmeta.WithIdempotencyKey(context.Background(), key),
			reportapp.CreateReportCommand{
				ReporterID:        reporterID,
				ReporterAccountID: "account-" + reporterID,
				TargetType:        reportmodel.TargetPost,
				TargetID:          targetID,
				Reason:            reportmodel.ReasonSpam,
			},
		); err != nil {
			t.Fatalf("create report %s: %v", targetID, err)
		}
	}
	create("my-report-1", "persona-owner", "post-1")
	create("other-report", "persona-other", "post-other")
	create("my-report-2", "persona-owner", "post-2")

	first, err := facade.ListMyReports(
		context.Background(),
		reportapp.ListMyReportsQuery{
			ReporterID: "persona-owner",
			Limit:      1,
		},
	)
	if err != nil {
		t.Fatalf("list first page: %v", err)
	}
	if len(first.Items) != 1 || first.NextCursor == "" {
		t.Fatalf("unexpected first page: %+v", first)
	}
	if first.Items[0].TargetID == "post-other" {
		t.Fatalf("other persona report leaked: %+v", first.Items[0])
	}

	second, err := facade.ListMyReports(
		context.Background(),
		reportapp.ListMyReportsQuery{
			ReporterID: "persona-owner",
			Cursor:     first.NextCursor,
			Limit:      1,
		},
	)
	if err != nil {
		t.Fatalf("list second page: %v", err)
	}
	if len(second.Items) != 1 ||
		second.Items[0].ID == first.Items[0].ID ||
		second.Items[0].TargetID == "post-other" {
		t.Fatalf("unexpected second page: %+v", second)
	}
	if second.NextCursor != "" {
		t.Fatalf("last page must not expose next cursor: %+v", second)
	}

	if _, err := facade.ListMyReports(
		context.Background(),
		reportapp.ListMyReportsQuery{ReporterID: "persona-owner", Cursor: "bad"},
	); err == nil {
		t.Fatal("invalid cursor must fail closed")
	}
	if _, err := facade.ListMyReports(
		context.Background(),
		reportapp.ListMyReportsQuery{Limit: 1},
	); err == nil {
		t.Fatal("missing verified reporter persona must fail closed")
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003
func TestGatheringSafetyAuthorityGrantAndFailClosedDecisions(t *testing.T) {
	t.Parallel()
	store := &gatheringSafetyReportStore{ReportStore: testsupport.NewReportStore()}
	service := reportapp.NewReportService(reportapp.BindDataPorts(store))
	if _, err := service.GrantGatheringSafetyTermination(
		context.Background(),
		reportapp.GrantGatheringSafetyTerminationCommand{
			ReportID:              "report-1",
			ExpectedReportVersion: 3,
			ActorPersonaID:        "persona-safety",
			ExpiresAt:             time.Now().UTC().Add(6 * time.Minute),
			IdempotencyKey:        "grant-too-long",
		},
	); err == nil ||
		!strings.Contains(err.Error(), "gathering_safety_authorization_invalid") ||
		store.issueCalls != 0 {
		t.Fatalf("grant beyond five-minute TTL must fail before persistence: %v", err)
	}
	expiresAt := time.Now().UTC().Add(2 * time.Minute)
	grant, err := service.GrantGatheringSafetyTermination(
		context.Background(),
		reportapp.GrantGatheringSafetyTerminationCommand{
			ReportID:              "report-1",
			ExpectedReportVersion: 3,
			ActorPersonaID:        "persona-safety",
			ExpiresAt:             expiresAt,
			IdempotencyKey:        "grant-1",
		},
	)
	if err != nil {
		t.Fatalf("grant Gathering safety authority: %v", err)
	}
	if grant.DecisionVersion != 3 ||
		grant.ActorPersonaID != "persona-safety" ||
		grant.GatheringID != "gathering-1" ||
		grant.Action != reportapp.GatheringSafetyActionTerminate ||
		grant.EvidenceRef != "content.report/report-1" ||
		grant.DecisionRef != "content.report/report-1@3#terminate_gathering" ||
		grant.DecisionDigest == "" ||
		!grant.ExpiresAt.Equal(expiresAt) {
		t.Fatalf("grant omitted canonical decision binding: %+v", grant)
	}
	query := reportapp.AuthorizeGatheringSafetyTerminationQuery{
		ActorPersonaID: grant.ActorPersonaID,
		GatheringID:    grant.GatheringID,
		Action:         grant.Action,
		EvidenceRef:    grant.EvidenceRef,
		DecisionRef:    grant.DecisionRef,
	}
	allowed, err := service.AuthorizeGatheringSafetyTermination(
		context.Background(),
		query,
	)
	if err != nil || !allowed.Allowed ||
		allowed.DecisionVersion != grant.DecisionVersion ||
		allowed.DecisionDigest != grant.DecisionDigest {
		t.Fatalf("exact authority decision was not allowed: %+v err=%v", allowed, err)
	}

	mismatch := query
	mismatch.ActorPersonaID = "persona-attacker"
	denied, err := service.AuthorizeGatheringSafetyTermination(
		context.Background(),
		mismatch,
	)
	if err != nil || denied.Allowed {
		t.Fatalf("identity mismatch must return opaque deny: %+v err=%v", denied, err)
	}

	store.authorization.ExpiresAt = time.Now().UTC().Add(-time.Second)
	expired, err := service.AuthorizeGatheringSafetyTermination(
		context.Background(),
		query,
	)
	if err != nil || expired.Allowed {
		t.Fatalf("expired authority must fail closed: %+v err=%v", expired, err)
	}

	store.authorization.ExpiresAt = time.Now().UTC().Add(time.Minute)
	revocation, err := service.RevokeGatheringSafetyTermination(
		context.Background(),
		reportapp.RevokeGatheringSafetyTerminationCommand{
			ReportID:       "report-1",
			DecisionRef:    grant.DecisionRef,
			IdempotencyKey: "revoke-1",
		},
	)
	if err != nil || revocation.RevokedAt == nil {
		t.Fatalf("revoke Gathering safety authority: %+v err=%v", revocation, err)
	}
	revoked, err := service.AuthorizeGatheringSafetyTermination(
		context.Background(),
		query,
	)
	if err != nil || revoked.Allowed {
		t.Fatalf("revoked authority must fail closed: %+v err=%v", revoked, err)
	}

	store.readErr = errors.New("authority database unavailable")
	if _, err := service.AuthorizeGatheringSafetyTermination(
		context.Background(),
		query,
	); err == nil || !strings.Contains(
		err.Error(),
		"gathering_safety_authority_unavailable",
	) {
		t.Fatalf("dependency failure must map to canonical unavailable: %v", err)
	}
}

type gatheringSafetyReportStore struct {
	*testsupport.ReportStore
	authorization reportports.GatheringSafetyAuthorization
	issueCalls    int
	readErr       error
}

func (store *gatheringSafetyReportStore) IssueGatheringSafetyAuthorization(
	_ context.Context,
	request reportports.IssueGatheringSafetyAuthorizationRequest,
) (reportports.GatheringSafetyAuthorization, bool, error) {
	store.issueCalls++
	store.authorization = reportports.GatheringSafetyAuthorization{
		ActorPersonaID:  request.ActorPersonaID,
		GatheringID:     "gathering-1",
		Action:          reportports.GatheringSafetyActionTerminate,
		EvidenceRef:     "content.report/" + request.ReportID,
		DecisionRef:     "content.report/" + request.ReportID + "@3#terminate_gathering",
		DecisionVersion: request.ExpectedReportVersion,
		DecisionDigest:  strings.Repeat("ab", 32),
		ExpiresAt:       request.ExpiresAt,
		IssuedAt:        time.Now().UTC(),
	}
	return store.authorization, false, nil
}

func (store *gatheringSafetyReportStore) RevokeGatheringSafetyAuthorization(
	_ context.Context,
	request reportports.RevokeGatheringSafetyAuthorizationRequest,
) (reportports.GatheringSafetyAuthorization, bool, error) {
	store.authorization.RevokedAt = request.RevokedAt
	return store.authorization, false, nil
}

func (store *gatheringSafetyReportStore) ReadGatheringSafetyAuthorization(
	_ context.Context,
	decisionRef string,
) (reportports.GatheringSafetyAuthorization, bool, error) {
	if store.readErr != nil {
		return reportports.GatheringSafetyAuthorization{}, false, store.readErr
	}
	return store.authorization, store.authorization.DecisionRef == decisionRef, nil
}
