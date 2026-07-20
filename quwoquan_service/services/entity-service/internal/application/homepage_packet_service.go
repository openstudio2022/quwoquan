package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtimpact "quwoquan_service/runtime/impact"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/operation"
	homepageapp "quwoquan_service/services/entity-service/internal/application/homepage"
	claimapp "quwoquan_service/services/entity-service/internal/application/homepage_claim_request"
	statusapp "quwoquan_service/services/entity-service/internal/application/homepage_status_report"
	homepagemodel "quwoquan_service/services/entity-service/internal/domain/homepage/model"
	homepageports "quwoquan_service/services/entity-service/internal/domain/homepage/ports"
	entitygenerated "quwoquan_service/services/entity-service/internal/generated"
)

type GeoPoint = homepageapp.GeoPoint
type HomepageSource = homepageapp.Source
type HomepageIntroductionAsset = homepageapp.IntroductionAsset
type HomepageContentPreview = homepageapp.ContentPreview
type HomepageQuestionPreview = homepageapp.QuestionPreview
type HomepageRelatedGroup = homepageapp.RelatedGroup
type Homepage = homepageapp.View
type HomepageInput = homepageapp.Input
type HomepageBasicInput = homepageapp.BasicInput
type HomepageSearchItemView = homepageapp.SearchItemView

type HomepageDataStore interface {
	homepageports.AggregateStore
	homepageports.Reader
	homepageports.FollowerProjectionStore
	homepageports.OutboxReader
	homepageports.ProjectionCheckpointStore
}

type HomepageClaimFacade interface {
	Create(ctx context.Context, command claimapp.CreateCommand) (claimapp.ClaimRequestView, error)
	Review(ctx context.Context, command claimapp.ReviewCommand) (claimapp.ClaimRequestView, error)
	ListQueue(ctx context.Context, query claimapp.QueueQuery) (claimapp.ClaimRequestSlice, error)
}

type HomepageStatusReportFacade interface {
	Create(ctx context.Context, command statusapp.CreateCommand) (statusapp.StatusReportView, error)
	Review(ctx context.Context, command statusapp.ReviewCommand) (statusapp.StatusReportView, error)
	ListQueue(ctx context.Context, query statusapp.QueueQuery) (statusapp.StatusReportSlice, error)
}

type ObjectIntersectionQuery struct {
	ViewerPersonaID   string
	ObjectID          string
	CanonicalEntityID string
	HomepageType      string
	Limit             int
}

type ObjectIntersectionReader interface {
	ListObjectIntersections(ctx context.Context, query ObjectIntersectionQuery) ([]json.RawMessage, error)
}

type HomepageService struct {
	commands        *homepageapp.CommandFacade
	queries         *homepageapp.QueryFacade
	imports         *homepageapp.ImportFacade
	store           HomepageDataStore
	claims          HomepageClaimFacade
	statusReports   HomepageStatusReportFacade
	intersections   ObjectIntersectionReader
	searchProjector Projector
}

type HomepageServiceOption func(*HomepageService)

func WithProjector(projector Projector) HomepageServiceOption {
	return func(service *HomepageService) { service.searchProjector = projector }
}

func WithClaimFacade(facade HomepageClaimFacade) HomepageServiceOption {
	return func(service *HomepageService) { service.claims = facade }
}

func WithStatusReportFacade(facade HomepageStatusReportFacade) HomepageServiceOption {
	return func(service *HomepageService) { service.statusReports = facade }
}

func (s *HomepageService) SetClaimFacade(facade HomepageClaimFacade) {
	s.claims = facade
}

func (s *HomepageService) SetStatusReportFacade(facade HomepageStatusReportFacade) {
	s.statusReports = facade
}

func WithIntersectionReader(reader ObjectIntersectionReader) HomepageServiceOption {
	return func(service *HomepageService) { service.intersections = reader }
}

func NewHomepageServiceWithStore(
	_ context.Context,
	store HomepageDataStore,
	options ...HomepageServiceOption,
) *HomepageService {
	if store == nil {
		panic("homepage service requires an explicitly injected object store")
	}
	commands, err := homepageapp.NewCommandFacade(store, store)
	if err != nil {
		panic(err)
	}
	queries, err := homepageapp.NewQueryFacade(store, store)
	if err != nil {
		panic(err)
	}
	imports, err := homepageapp.NewImportFacade(commands, store, store)
	if err != nil {
		panic(err)
	}
	service := &HomepageService{
		commands: commands,
		queries:  queries,
		imports:  imports,
		store:    store,
	}
	for _, option := range options {
		option(service)
	}
	commands.WithObserver(homepageCommitObserver{service: service})
	return service
}

type homepageCommitObserver struct{ service *HomepageService }

func (observer homepageCommitObserver) OnHomepageCommitted(
	ctx context.Context,
	event homepageapp.CommittedEvent,
) {
	if observer.service == nil || observer.service.searchProjector == nil {
		return
	}
	view := homepageapp.ViewFromSnapshot(event.Snapshot)
	projectorEvent := ProjectorEvent{
		Type:       ProjectorEventHomepageUpserted,
		HomepageID: view.ID,
		Homepage:   &view,
	}
	if event.Snapshot.Status == homepagemodel.StatusOffline {
		projectorEvent.Type = ProjectorEventHomepageRemoved
		projectorEvent.Homepage = nil
	}
	_ = observer.service.searchProjector.Project(ctx, projectorEvent)
}

func (s *HomepageService) SearchHomepages(
	ctx context.Context,
	query string,
	homepageType string,
	city string,
	status string,
	cursor string,
	limit int,
) (homepageapp.SearchSlice, error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.SearchHomepages",
		attribute.String("search.query", query),
		attribute.String("homepage.type", homepageType))
	var err error
	defer func() { rtobs.EndSpan(span, err) }()
	result, err := s.queries.Search(ctx, homepageports.SearchQuery{
		Query: query, HomepageType: homepageType, City: city, Status: status, Cursor: cursor, Limit: limit,
	})
	return result, err
}

func (s *HomepageService) IntakeHomepageCandidate(
	ctx context.Context,
	input HomepageInput,
	sourceType string,
) (_ *Homepage, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "entity.IntakeHomepageCandidate",
		attribute.String("homepage.type", input.HomepageType),
		attribute.String("source.type", sourceType))
	defer func() { rtobs.EndSpan(span, err) }()
	view, err := s.commands.IntakeCandidate(
		ctx,
		commandMeta(ctx, "homepage-intake", input.HomepageType+":"+input.Title),
		input,
		sourceType,
	)
	if err != nil {
		return nil, err
	}
	return &view, nil
}

func (s *HomepageService) SuggestHomepageCandidate(
	ctx context.Context,
	input HomepageInput,
) (*Homepage, error) {
	view, err := s.commands.SuggestCandidate(
		ctx,
		commandMeta(ctx, "homepage-suggest", input.HomepageType+":"+input.Title),
		input,
	)
	if err != nil {
		return nil, err
	}
	return &view, nil
}

func (s *HomepageService) PublishHomepageCandidate(
	ctx context.Context,
	homepageID string,
) (*Homepage, error) {
	view, err := s.commands.PublishCandidate(
		ctx,
		commandMeta(ctx, "homepage-publish", homepageID),
		homepageID,
	)
	if err != nil {
		return nil, err
	}
	return &view, nil
}

func (s *HomepageService) GetHomepage(
	ctx context.Context,
	homepageID string,
) (*Homepage, error) {
	return s.GetHomepageForViewer(ctx, homepageID, "")
}

func (s *HomepageService) FindHomepageStatus(
	ctx context.Context,
	homepageID string,
) (string, bool, error) {
	return s.queries.FindHomepageStatus(ctx, homepageID)
}

func (s *HomepageService) FindHomepageState(
	ctx context.Context,
	homepageID string,
) (claimapp.HomepageState, bool, error) {
	view, err := s.queries.Get(ctx, homepageID, "", true)
	if err != nil {
		var appError *rterr.AppError
		if errors.As(err, &appError) &&
			appError.Code.String() == entitygenerated.ErrHomepageNotFound.Error() {
			return claimapp.HomepageState{}, false, nil
		}
		return claimapp.HomepageState{}, false, err
	}
	return claimapp.HomepageState{
		Status: view.Status, ClaimStatus: view.ClaimStatus,
	}, true, nil
}

func (s *HomepageService) GetHomepageForViewer(
	ctx context.Context,
	homepageID string,
	viewerPersonaID string,
) (*Homepage, error) {
	view, err := s.queries.Get(ctx, homepageID, viewerPersonaID, false)
	if err != nil {
		return nil, err
	}
	return &view, nil
}

func (s *HomepageService) ApplySubjectFollowState(
	ctx context.Context,
	homepageID string,
	personaID string,
	following bool,
) error {
	status, found, err := s.FindHomepageStatus(ctx, homepageID)
	if err != nil || !found || status == string(homepagemodel.StatusOffline) {
		return err
	}
	now := time.Now().UTC()
	return s.store.UpsertFollowerState(
		ctx,
		homepageID,
		personaID,
		following,
		now.UnixNano(),
		now,
	)
}

type HomepageShellView struct {
	Homepage        Homepage                   `json:"homepage"`
	ReviewSummary   *homepageapp.ReviewSummary `json:"reviewSummary,omitempty"`
	ContentPreview  []HomepageContentPreview   `json:"contentPreview"`
	QuestionPreview []HomepageQuestionPreview  `json:"questionPreview"`
	RelatedGroups   []HomepageRelatedGroup     `json:"relatedGroups"`
}

func (s *HomepageService) GetHomepageShell(
	ctx context.Context,
	homepageID string,
) (*HomepageShellView, error) {
	homepage, err := s.GetHomepage(ctx, homepageID)
	if err != nil {
		return nil, err
	}
	return &HomepageShellView{
		Homepage:        *homepage,
		ReviewSummary:   homepage.ReviewSummary,
		ContentPreview:  emptyContentPreviews(homepage.ContentPreview),
		QuestionPreview: emptyQuestionPreviews(homepage.QuestionPreview),
		RelatedGroups:   emptyRelatedGroups(homepage.RelatedGroups),
	}, nil
}

type HomepageReviewSummaryView struct {
	AverageRating   *float64   `json:"averageRating,omitempty"`
	RatingCount     int        `json:"ratingCount"`
	HighlightTags   []string   `json:"highlightTags"`
	DimensionScores []struct{} `json:"dimensionScores"`
}

func (s *HomepageService) GetHomepageReviewSummary(
	ctx context.Context,
	homepageID string,
) (*HomepageReviewSummaryView, error) {
	homepage, err := s.GetHomepage(ctx, homepageID)
	if err != nil {
		return nil, err
	}
	tags := []string{}
	if homepage.ReviewSummary != nil {
		tags = append(tags, homepage.ReviewSummary.HighlightTags...)
	}
	return &HomepageReviewSummaryView{
		AverageRating:   homepage.AverageRating,
		RatingCount:     homepage.RatingCount,
		HighlightTags:   tags,
		DimensionScores: []struct{}{},
	}, nil
}

func (s *HomepageService) ApplyReviewSummary(
	ctx context.Context,
	homepageID string,
	averageRating *float64,
	ratingCount int,
	highlightTags []string,
) error {
	identity := fmt.Sprintf("%s:%d:%v", homepageID, ratingCount, highlightTags)
	_, err := s.commands.ApplyReviewSummary(
		ctx,
		commandMeta(ctx, "homepage-review-summary", identity),
		homepageID,
		averageRating,
		ratingCount,
		highlightTags,
	)
	return err
}

// ApplyClaimRequestedProjection 是 HomepageClaimRequested 的幂等消费端口。
func (s *HomepageService) ApplyClaimRequestedProjection(
	ctx context.Context,
	eventID string,
	homepageID string,
) error {
	_, err := s.commands.ApplyClaimPending(
		ctx,
		homepageapp.CommandMeta{
			ActorID:        "system:homepage-claim-projector",
			IdempotencyKey: strings.TrimSpace(eventID),
		},
		homepageID,
	)
	return err
}

// ApplyClaimReviewedProjection 是 HomepageClaimReviewed 的幂等消费端口。
func (s *HomepageService) ApplyClaimReviewedProjection(
	ctx context.Context,
	eventID string,
	homepageID string,
	requesterPersonaID string,
	approved bool,
) error {
	_, err := s.commands.ApplyClaimApproved(
		ctx,
		homepageapp.CommandMeta{
			ActorID:        "system:homepage-claim-projector",
			IdempotencyKey: strings.TrimSpace(eventID),
		},
		homepageID,
		requesterPersonaID,
		requesterPersonaID,
		approved,
	)
	return err
}

// ApplyStatusReviewedProjection 是 confirmed_offline 状态上报的幂等消费端口。
func (s *HomepageService) ApplyStatusReviewedProjection(
	ctx context.Context,
	eventID string,
	homepageID string,
) error {
	_, err := s.commands.ApplyOffline(
		ctx,
		homepageapp.CommandMeta{
			ActorID:        "system:homepage-status-projector",
			IdempotencyKey: strings.TrimSpace(eventID),
		},
		homepageID,
	)
	return err
}

type HomepageRelatedGroupSummaryView struct {
	Groups []HomepageRelatedGroup `json:"groups"`
}

func (s *HomepageService) GetHomepageRelatedGroups(
	ctx context.Context,
	homepageID string,
) (*HomepageRelatedGroupSummaryView, error) {
	homepage, err := s.GetHomepage(ctx, homepageID)
	if err != nil {
		return nil, err
	}
	return &HomepageRelatedGroupSummaryView{Groups: emptyRelatedGroups(homepage.RelatedGroups)}, nil
}

type HomepageImpactSummaryView struct {
	HomepageID string               `json:"homepageId"`
	Total      int64                `json:"total"`
	Items      []rtimpact.Statement `json:"items"`
}

func (s *HomepageService) GetHomepageImpact(
	ctx context.Context,
	homepageID string,
) (*HomepageImpactSummaryView, error) {
	homepage, err := s.GetHomepage(ctx, homepageID)
	if err != nil {
		return nil, err
	}
	return buildHomepageImpactSummary(homepage), nil
}

type ObjectPageStats struct {
	RatingCount       int `json:"ratingCount"`
	RelatedGroupCount int `json:"relatedGroupCount"`
	HighlightCount    int `json:"highlightCount"`
}

type ObjectPageContentSections struct {
	Home    []HomepageContentPreview   `json:"home"`
	Reviews *homepageapp.ReviewSummary `json:"reviews,omitempty"`
	Related []HomepageRelatedGroup     `json:"related"`
}

type ObjectPageBundle struct {
	ObjectType          string                    `json:"objectType"`
	ObjectID            string                    `json:"objectId"`
	CanonicalEntityID   string                    `json:"canonicalEntityId"`
	Title               string                    `json:"title"`
	Subtitle            string                    `json:"subtitle,omitempty"`
	CoverURL            string                    `json:"coverUrl,omitempty"`
	ObjectPageTemplate  string                    `json:"objectPageTemplate"`
	TagRefs             []string                  `json:"tagRefs"`
	Stats               ObjectPageStats           `json:"stats"`
	IntersectionReasons []json.RawMessage         `json:"intersectionReasons"`
	HighlightItems      []HomepageContentPreview  `json:"highlightItems"`
	ContentSections     ObjectPageContentSections `json:"contentSections"`
	RelatedObjects      []HomepageRelatedGroup    `json:"relatedObjects"`
	RelationEdges       []json.RawMessage         `json:"relationEdges"`
	AssistantContext    json.RawMessage           `json:"assistantContext,omitempty"`
	RolloutContext      *ObjectPageRolloutContext `json:"rolloutContext,omitempty"`
}

type ObjectPageRolloutContext struct {
	Cohort           string `json:"cohort,omitempty"`
	City             string `json:"city,omitempty"`
	ExperimentBucket string `json:"experimentBucket,omitempty"`
}

func (s *HomepageService) GetObjectPageBundle(
	ctx context.Context,
	viewerPersonaID string,
	homepageID string,
	referralSource string,
	feedRequestID string,
	recommendationTraceID string,
	experimentBucket string,
	rolloutCohort string,
) (*ObjectPageBundle, error) {
	homepage, err := s.GetHomepageForViewer(ctx, homepageID, viewerPersonaID)
	if err != nil {
		return nil, err
	}
	reasons := []json.RawMessage{}
	if s.intersections != nil && strings.TrimSpace(viewerPersonaID) != "" {
		reasons, err = s.intersections.ListObjectIntersections(ctx, ObjectIntersectionQuery{
			ViewerPersonaID:   viewerPersonaID,
			ObjectID:          homepage.ID,
			CanonicalEntityID: homepage.CanonicalEntityID,
			HomepageType:      homepage.HomepageType,
			Limit:             8,
		})
		if err != nil {
			return nil, err
		}
		if reasons == nil {
			reasons = []json.RawMessage{}
		}
	}
	var rollout *ObjectPageRolloutContext
	if rolloutCohort != "" || experimentBucket != "" {
		rollout = &ObjectPageRolloutContext{
			Cohort: rolloutCohort, City: homepage.City, ExperimentBucket: experimentBucket,
		}
	}
	return &ObjectPageBundle{
		ObjectType:         "homepage",
		ObjectID:           homepage.ID,
		CanonicalEntityID:  homepage.CanonicalEntityID,
		Title:              homepage.Title,
		Subtitle:           homepage.Subtitle,
		CoverURL:           homepage.CoverURL,
		ObjectPageTemplate: homepage.ObjectPageTemplate,
		TagRefs:            emptyStrings(homepage.CategoryTags),
		Stats: ObjectPageStats{
			RatingCount:       homepage.RatingCount,
			RelatedGroupCount: len(homepage.RelatedGroups),
			HighlightCount:    len(homepage.ContentPreview),
		},
		IntersectionReasons: reasons,
		HighlightItems:      emptyContentPreviews(homepage.ContentPreview),
		ContentSections: ObjectPageContentSections{
			Home:    emptyContentPreviews(homepage.ContentPreview),
			Reviews: homepage.ReviewSummary,
			Related: emptyRelatedGroups(homepage.RelatedGroups),
		},
		RelatedObjects:   emptyRelatedGroups(homepage.RelatedGroups),
		RelationEdges:    emptyRawMessages(homepage.RelationEdges),
		AssistantContext: append(json.RawMessage(nil), homepage.AssistantContext...),
		RolloutContext:   rollout,
	}, nil
}

func (s *HomepageService) UpdateClaimedHomepageBasics(
	ctx context.Context,
	homepageID string,
	input HomepageBasicInput,
) (*Homepage, error) {
	view, err := s.commands.UpdateClaimedBasics(
		ctx,
		commandMeta(ctx, "homepage-basics", homepageID),
		homepageID,
		input,
	)
	if err != nil {
		return nil, err
	}
	return &view, nil
}

type ReloadHomepageStateResult struct {
	HomepagesBefore int `json:"homepagesBefore"`
	HomepagesAfter  int `json:"homepagesAfter"`
	SnapshotSize    int `json:"snapshotSize"`
}

// ReloadHomepageState 已重定义为权威 homepages 集合与 ES 的即时对账入口。
// 它只扫描权威 homepages 集合，不把任何全局快照加载进进程内存。
func (s *HomepageService) ReloadHomepageState(ctx context.Context) (ReloadHomepageStateResult, error) {
	count, err := s.queries.Count(ctx)
	if err != nil {
		return ReloadHomepageStateResult{}, err
	}
	if s.searchProjector != nil {
		cursor := ""
		for {
			items, next, scanErr := s.queries.Scan(ctx, cursor, 500)
			if scanErr != nil {
				return ReloadHomepageStateResult{}, scanErr
			}
			for index := range items {
				item := items[index]
				event := ProjectorEvent{
					Type: ProjectorEventHomepageUpserted, HomepageID: item.ID, Homepage: &item,
				}
				if item.Status == string(homepagemodel.StatusOffline) {
					event.Type = ProjectorEventHomepageRemoved
					event.Homepage = nil
				}
				_ = s.searchProjector.Project(ctx, event)
			}
			if next == "" {
				break
			}
			cursor = next
		}
	}
	return ReloadHomepageStateResult{
		HomepagesBefore: int(count),
		HomepagesAfter:  int(count),
		SnapshotSize:    0,
	}, nil
}

func buildHomepageImpactSummary(homepage *Homepage) *HomepageImpactSummaryView {
	items := make([]rtimpact.Statement, 0, len(homepage.RelatedGroups))
	for _, group := range homepage.RelatedGroups {
		item, complete := rtimpact.BuildStatement(rtimpact.StatementEvidence{
			HelpType:              rtimpact.HelpCommunity,
			Action:                "join_circle",
			IntersectionDimension: "relationship",
			Source:                "homepage_related_groups",
			Count:                 int64(group.MemberCount),
			SubtitleText:          "关联圈子成员事实来自同一读模型快照。",
			ImpactID:              group.CircleID + "_homepage_members",
			EvidenceSnapshotID:    group.EvidenceSnapshotID,
			RepresentativeActor: rtimpact.RepresentativeActor{
				ActorID:         group.OwnerUserID,
				DisplayName:     group.OwnerDisplayNameSnapshot,
				AvatarURL:       group.OwnerAvatarURLSnapshot,
				RelationLabel:   "圈子主理人",
				PrivacyState:    "visible",
				Target:          &rtimpact.Target{ObjectType: "user", ObjectID: group.OwnerUserID, ObjectKind: "person", RouteID: "profile"},
				EvidenceRank:    1,
				SnapshotVersion: group.EvidenceSnapshotID,
			},
			ObjectName:   group.Name,
			ObjectTarget: rtimpact.Target{ObjectType: "circle", ObjectID: group.CircleID, ObjectKind: "circle", RouteID: "circleDetail"},
		})
		if complete {
			items = append(items, item)
		}
	}
	total := int64(0)
	for _, item := range items {
		total += item.Count
	}
	return &HomepageImpactSummaryView{HomepageID: homepage.ID, Total: total, Items: items}
}

func commandMeta(ctx context.Context, purpose string, identity string) homepageapp.CommandMeta {
	actorID := "entity-service"
	key := ""
	if invocation, ok := operation.FromContext(ctx); ok {
		if value := strings.TrimSpace(invocation.Actor.PersonaID); value != "" {
			actorID = value
		} else if value := strings.TrimSpace(invocation.Actor.AccountID); value != "" {
			actorID = value
		}
		key = strings.TrimSpace(invocation.IdempotencyKey)
	}
	if key == "" {
		sum := sha256.Sum256([]byte(purpose + "\x00" + strings.TrimSpace(identity)))
		key = purpose + ":" + hex.EncodeToString(sum[:16])
	}
	return homepageapp.CommandMeta{ActorID: actorID, IdempotencyKey: key}
}

func emptyStrings(values []string) []string {
	return append([]string{}, values...)
}
func emptyContentPreviews(values []HomepageContentPreview) []HomepageContentPreview {
	return append([]HomepageContentPreview{}, values...)
}
func emptyQuestionPreviews(values []HomepageQuestionPreview) []HomepageQuestionPreview {
	return append([]HomepageQuestionPreview{}, values...)
}
func emptyRelatedGroups(values []HomepageRelatedGroup) []HomepageRelatedGroup {
	return append([]HomepageRelatedGroup{}, values...)
}
func emptyRawMessages(values []json.RawMessage) []json.RawMessage {
	result := make([]json.RawMessage, 0, len(values))
	for _, value := range values {
		result = append(result, append(json.RawMessage(nil), value...))
	}
	return result
}

func newAppError(code error, debugMessage string) *rterr.AppError {
	switch code {
	case entitygenerated.ErrInvalidArgument:
		return entitygenerated.AppErrorFromInvalidArgument(debugMessage)
	case entitygenerated.ErrHomepageNotFound:
		return entitygenerated.AppErrorFromHomepageNotFound(debugMessage)
	case entitygenerated.ErrClaimMaterialMissing:
		return entitygenerated.AppErrorFromClaimMaterialMissing(debugMessage)
	case entitygenerated.ErrAlreadyClaimed:
		return entitygenerated.AppErrorFromAlreadyClaimed(debugMessage)
	case entitygenerated.ErrHomepageOffline:
		return entitygenerated.AppErrorFromHomepageOffline(debugMessage)
	case entitygenerated.ErrInvalidHomepageType:
		return entitygenerated.AppErrorFromInvalidHomepageType(debugMessage)
	case entitygenerated.ErrPermissionDenied:
		return entitygenerated.AppErrorFromPermissionDenied(debugMessage)
	case entitygenerated.ErrClaimNotFound:
		return entitygenerated.AppErrorFromClaimNotFound(debugMessage)
	case entitygenerated.ErrStatusReportNotFound:
		return entitygenerated.AppErrorFromStatusReportNotFound(debugMessage)
	default:
		return entitygenerated.AppErrorFromInternalError(debugMessage)
	}
}

func wrapDependencyError(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return entitygenerated.AppErrorFromInternalError(err.Error())
}
