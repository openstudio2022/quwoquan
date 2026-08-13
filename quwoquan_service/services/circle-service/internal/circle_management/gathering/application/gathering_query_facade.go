package gathering

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	circleerrors "quwoquan_service/services/circle-service/generated/circle_management/circle"
	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	wire "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/client"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

type GatheringIDQuery struct {
	GatheringID string
}

type ListByHostQuery struct {
	Host   HostRef
	Cursor string
	Limit  int
}

// ListMineQuery 是 host 本人私有列表（不做公开披露裁剪）；host 身份只取受信
// persona actor，禁止携带任意 host 引用代查他人。
type ListMineQuery struct {
	Cursor string
	Limit  int
}

type ListBySourceQuery struct {
	Source CanonicalObjectRef
	Cursor string
	Limit  int
}

type GatheringPageQuery struct {
	GatheringID string
	Cursor      string
	Limit       int
}

// Positions are typed storage keysets. The opaque HTTP cursor is decoded by
// the facade before infrastructure sees it.
type PublicListPosition struct {
	StartAt     *time.Time
	GatheringID string
}

type ApplicationListPosition struct {
	ReviewExpectedBy *time.Time
	PersonaID        string
	AttemptNo        int64
}

type RosterListPosition struct {
	PersonaID string
}

type ApplicationReadQuery struct {
	GatheringID        string
	OrganizerPersonaID string
	After              ApplicationListPosition
	Limit              int
}

type RosterReadQuery struct {
	GatheringID string
	ActiveOnly  bool
	After       RosterListPosition
	Limit       int
}

// GatheringQueryReader is an object-local, named query port. It is kept in the
// application package because Scope D cannot alter the aggregate mutation ports.
type GatheringQueryReader interface {
	ReadGathering(context.Context, string) (GatheringReadModel, bool, error)
	ListByHost(context.Context, HostRef, PublicListPosition, int) ([]GatheringReadModel, error)
	// ListMineByHost 返回 persona host 名下全部行动（含 draft 与非公开
	// audiencePolicy）；披露边界由 facade 的 viewer 授权保证（host 本人）。
	ListMineByHost(context.Context, string, PublicListPosition, int) ([]GatheringReadModel, error)
	ListBySource(context.Context, CanonicalObjectRef, PublicListPosition, int) ([]GatheringReadModel, error)
	ListApplications(context.Context, ApplicationReadQuery) ([]ParticipationRecord, error)
	ListRoster(context.Context, RosterReadQuery) ([]ParticipationRecord, error)
}

type GatheringQueryFacade struct {
	reader GatheringQueryReader
	now    func() time.Time
}

func NewGatheringQueryFacade(reader GatheringQueryReader, now func() time.Time) *GatheringQueryFacade {
	if reader == nil {
		panic("GatheringQueryFacade requires a named GatheringQueryReader")
	}
	if now == nil {
		now = time.Now
	}
	return &GatheringQueryFacade{reader: reader, now: now}
}

func (facade *GatheringQueryFacade) GetGathering(
	ctx context.Context,
	query GatheringIDQuery,
) (PrivateDetail, error) {
	viewerPersonaID, err := requiredViewerPersonaID(ctx)
	if err != nil {
		return PrivateDetail{}, err
	}
	value, err := facade.read(ctx, query.GatheringID)
	if err != nil {
		return PrivateDetail{}, err
	}
	viewer := resolveViewerAccess(value, viewerPersonaID)
	if !viewer.IsOrganizer && !isActive(viewer.Participation) {
		if viewer.Participation != nil && viewer.Participation.State == "closed" {
			return PrivateDetail{}, gatheringAccessRevoked("closed Gathering participation")
		}
		return PrivateDetail{}, gatheringActiveParticipationRequired("active Gathering participation is required")
	}
	now := facade.now().UTC()
	return ProjectPrivateDetail(value, viewerPersonaID, now), nil
}

func (facade *GatheringQueryFacade) GetPublicGathering(
	ctx context.Context,
	query GatheringIDQuery,
) (PublicDetail, error) {
	value, err := facade.read(ctx, query.GatheringID)
	if err != nil {
		return PublicDetail{}, err
	}
	if !publicDetailReadable(value.LifecycleStatus) {
		return PublicDetail{}, gatheringerrors.AppErrorFromGatheringNotFound("Gathering is not publicly readable")
	}
	now := facade.now().UTC()
	return ProjectPublicDetail(value, optionalViewerPersonaID(ctx), now), nil
}

type ParticipationStatusQuery struct {
	GatheringID string
	PersonaID   string
}

// GetParticipationStatus 是服务间最小 Participation 状态断言（INTERNAL，principal=service）。
// Content 在接受 post.gatheringRef 回流引用前必须由 Circle owner 确认作者当前参与状态
// （校验不成立 fail-closed）。只回答单人状态，不投影名单、申请答案或私密事实，不转移 owner。
func (facade *GatheringQueryFacade) GetParticipationStatus(
	ctx context.Context,
	query ParticipationStatusQuery,
) (ParticipationStatus, error) {
	personaID := strings.TrimSpace(query.PersonaID)
	if personaID == "" {
		return ParticipationStatus{}, circleerrors.AppErrorFromInvalidArgument("personaId is required")
	}
	value, err := facade.read(ctx, query.GatheringID)
	if err != nil {
		return ParticipationStatus{}, err
	}
	status := ParticipationStatus{
		GatheringID: value.ID,
		PersonaID:   personaID,
		LifecycleStatus: wire.GatheringLifecycleStatus(
			value.LifecycleStatus,
		),
	}
	if participation, found := model.FindParticipation(value, personaID); found {
		status.ParticipationState = wire.GatheringParticipationState(
			participation.State,
		)
	}
	return status, nil
}

func (facade *GatheringQueryFacade) ListByHost(
	ctx context.Context,
	query ListByHostQuery,
) (ByHostPage, error) {
	query.Host.SubjectKind = contract.GatheringHostSubjectKind(
		strings.TrimSpace(string(query.Host.SubjectKind)),
	)
	query.Host.SubjectID = strings.TrimSpace(query.Host.SubjectID)
	if !validHostSubjectKind(query.Host.SubjectKind) || query.Host.SubjectID == "" {
		return ByHostPage{}, gatheringHostAuthorityInvalid("typed Host reference is required")
	}
	limit := normalizeLimit(query.Limit, 20, 50)
	after, err := decodePublicCursor(query.Cursor, "host")
	if err != nil {
		return ByHostPage{}, invalidCursor(err)
	}
	values, err := facade.reader.ListByHost(ctx, query.Host, after, limit+1)
	if err != nil {
		return ByHostPage{}, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	page := facade.publicPage(values, limit, "host")
	return ByHostPage{Items: page.Items, NextCursor: page.NextCursor, HasMore: page.HasMore}, nil
}

// ListMyHostedGatherings 是 host 本人的私有全量列表（REQ-008 我的行动私有读面）：
// 含 draft 与全部 audiencePolicy，不做 publicPage 的公开披露裁剪；卡片投影仍是
// PublicCard typed 形状（host 本人对自己的行动全知，无 disclosure 冲突）。
func (facade *GatheringQueryFacade) ListMyHostedGatherings(
	ctx context.Context,
	query ListMineQuery,
) (ByHostPage, error) {
	viewerPersonaID, err := requiredViewerPersonaID(ctx)
	if err != nil {
		return ByHostPage{}, err
	}
	if viewerPersonaID == "" {
		return ByHostPage{}, circleerrors.AppErrorFromInvalidArgument("trusted persona is required")
	}
	limit := normalizeLimit(query.Limit, 20, 50)
	after, err := decodePublicCursor(query.Cursor, "mine")
	if err != nil {
		return ByHostPage{}, invalidCursor(err)
	}
	values, err := facade.reader.ListMineByHost(ctx, viewerPersonaID, after, limit+1)
	if err != nil {
		return ByHostPage{}, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	hasMore := len(values) > limit
	if hasMore {
		values = values[:limit]
	}
	now := facade.now().UTC()
	items := make([]PublicCard, 0, len(values))
	for _, value := range values {
		items = append(items, ProjectPublicCard(value, now))
	}
	var nextCursor string
	if hasMore && len(values) > 0 {
		cursor, cursorErr := encodePublicCursor(values[len(values)-1], "mine")
		if cursorErr != nil {
			return ByHostPage{}, gatheringerrors.AppErrorFromGatheringStorageFailed(cursorErr.Error())
		}
		nextCursor = cursor
	}
	return ByHostPage{Items: items, NextCursor: nextCursor, HasMore: hasMore}, nil
}

func (facade *GatheringQueryFacade) ListBySource(
	ctx context.Context,
	query ListBySourceQuery,
) (BySourcePage, error) {
	query.Source.ObjectTypeRef = strings.TrimSpace(query.Source.ObjectTypeRef)
	query.Source.ObjectID = strings.TrimSpace(query.Source.ObjectID)
	if query.Source.ObjectTypeRef == "" || query.Source.ObjectID == "" {
		return BySourcePage{}, circleerrors.AppErrorFromInvalidArgument("typed canonical source reference is required")
	}
	limit := normalizeLimit(query.Limit, 20, 50)
	after, err := decodePublicCursor(query.Cursor, "source")
	if err != nil {
		return BySourcePage{}, invalidCursor(err)
	}
	values, err := facade.reader.ListBySource(ctx, query.Source, after, limit+1)
	if err != nil {
		return BySourcePage{}, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	page := facade.publicPage(values, limit, "source")
	return BySourcePage{Items: page.Items, NextCursor: page.NextCursor, HasMore: page.HasMore}, nil
}

func (facade *GatheringQueryFacade) ListApplications(
	ctx context.Context,
	query GatheringPageQuery,
) (ApplicationInboxPage, error) {
	viewerPersonaID, err := requiredViewerPersonaID(ctx)
	if err != nil {
		return ApplicationInboxPage{}, err
	}
	value, err := facade.read(ctx, query.GatheringID)
	if err != nil {
		return ApplicationInboxPage{}, err
	}
	if !resolveViewerAccess(value, viewerPersonaID).IsOrganizer {
		return ApplicationInboxPage{}, gatheringerrors.AppErrorFromGatheringPermissionDenied(
			"active organizer authority is required",
		)
	}
	limit := normalizeLimit(query.Limit, 20, 50)
	after, err := decodeApplicationCursor(query.Cursor)
	if err != nil {
		return ApplicationInboxPage{}, invalidCursor(err)
	}
	values, err := facade.reader.ListApplications(ctx, ApplicationReadQuery{
		GatheringID: value.ID, OrganizerPersonaID: viewerPersonaID,
		After: after, Limit: limit + 1,
	})
	if err != nil {
		return ApplicationInboxPage{}, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	hasMore := len(values) > limit
	if hasMore {
		values = values[:limit]
	}
	items := make([]ApplicationInboxItem, 0, len(values))
	for _, value := range values {
		items = append(items, ProjectApplicationItem(value))
	}
	var nextCursor string
	if hasMore && len(values) > 0 {
		cursor, cursorErr := encodeApplicationCursor(values[len(values)-1])
		if cursorErr != nil {
			return ApplicationInboxPage{}, gatheringerrors.AppErrorFromGatheringStorageFailed(cursorErr.Error())
		}
		nextCursor = cursor
	}
	return ApplicationInboxPage{Items: items, NextCursor: nextCursor, HasMore: hasMore}, nil
}

func (facade *GatheringQueryFacade) ListRoster(
	ctx context.Context,
	query GatheringPageQuery,
) (RosterPage, error) {
	viewerPersonaID, err := requiredViewerPersonaID(ctx)
	if err != nil {
		return RosterPage{}, err
	}
	value, err := facade.read(ctx, query.GatheringID)
	if err != nil {
		return RosterPage{}, err
	}
	viewer := resolveViewerAccess(value, viewerPersonaID)
	if !viewer.IsOrganizer && !isActive(viewer.Participation) {
		if viewer.Participation != nil && viewer.Participation.State == "closed" {
			return RosterPage{}, gatheringAccessRevoked("closed Gathering participation")
		}
		return RosterPage{}, gatheringActiveParticipationRequired("active Gathering participation is required")
	}
	now := facade.now().UTC()
	capacity := deriveCapacity(value, now)
	if !viewer.IsOrganizer && value.PolicySet.DisclosurePolicy.RosterDisclosure != "joined_members" {
		return RosterPage{Items: []RosterItem{}, Capacity: capacity}, nil
	}
	limit := normalizeLimit(query.Limit, 50, 100)
	after, err := decodeRosterCursor(query.Cursor)
	if err != nil {
		return RosterPage{}, invalidCursor(err)
	}
	values, err := facade.reader.ListRoster(ctx, RosterReadQuery{
		GatheringID: value.ID, ActiveOnly: !viewer.IsOrganizer, After: after, Limit: limit + 1,
	})
	if err != nil {
		return RosterPage{}, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	hasMore := len(values) > limit
	if hasMore {
		values = values[:limit]
	}
	items := make([]RosterItem, 0, len(values))
	for _, value := range values {
		items = append(items, ProjectRosterItem(value))
	}
	var nextCursor string
	if hasMore && len(values) > 0 {
		cursor, cursorErr := encodeRosterCursor(values[len(values)-1])
		if cursorErr != nil {
			return RosterPage{}, gatheringerrors.AppErrorFromGatheringStorageFailed(cursorErr.Error())
		}
		nextCursor = cursor
	}
	return RosterPage{
		Items: items, Capacity: capacity, NextCursor: nextCursor, HasMore: hasMore,
	}, nil
}

func (facade *GatheringQueryFacade) read(
	ctx context.Context,
	gatheringID string,
) (GatheringReadModel, error) {
	gatheringID = strings.TrimSpace(gatheringID)
	if gatheringID == "" {
		return GatheringReadModel{}, circleerrors.AppErrorFromInvalidArgument("gatheringId is required")
	}
	value, found, err := facade.reader.ReadGathering(ctx, gatheringID)
	if err != nil {
		return GatheringReadModel{}, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	if !found {
		return GatheringReadModel{}, gatheringerrors.AppErrorFromGatheringNotFound("Gathering not found")
	}
	return value, nil
}

func (facade *GatheringQueryFacade) publicPage(
	values []GatheringReadModel,
	limit int,
	cursorKind string,
) publicCardPage {
	eligible := make([]GatheringReadModel, 0, len(values))
	for _, value := range values {
		if value.PolicySet.AudiencePolicy != contract.GatheringAudiencePolicyPublic ||
			!publicDetailReadable(value.LifecycleStatus) {
			continue
		}
		eligible = append(eligible, value)
	}
	values = eligible
	hasMore := len(values) > limit
	if hasMore {
		values = values[:limit]
	}
	now := facade.now().UTC()
	items := make([]PublicCard, 0, len(values))
	for _, value := range values {
		items = append(items, ProjectPublicCard(value, now))
	}
	var nextCursor string
	if hasMore && len(values) > 0 {
		cursor, err := encodePublicCursor(values[len(values)-1], cursorKind)
		if err == nil {
			nextCursor = cursor
		}
	}
	return publicCardPage{Items: items, NextCursor: nextCursor, HasMore: hasMore}
}

type publicCardPage struct {
	Items      []PublicCard
	NextCursor string
	HasMore    bool
}

func requiredViewerPersonaID(ctx context.Context) (string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", circleerrors.AppErrorFromInvalidArgument("trusted persona is required")
	}
	return strings.TrimSpace(current.Actor.PersonaID), nil
}

func optionalViewerPersonaID(ctx context.Context) string {
	current, ok := operation.FromContext(ctx)
	if !ok {
		return ""
	}
	return strings.TrimSpace(current.Actor.PersonaID)
}

func publicDetailReadable(
	lifecycleStatus contract.GatheringLifecycleStatus,
) bool {
	switch lifecycleStatus {
	case contract.GatheringLifecycleStatusPublished,
		contract.GatheringLifecycleStatusCancelled,
		contract.GatheringLifecycleStatusCompleted:
		return true
	default:
		return false
	}
}

func normalizeLimit(value, fallback, maximum int) int {
	if value <= 0 {
		return fallback
	}
	if value > maximum {
		return maximum
	}
	return value
}

func validHostSubjectKind(value contract.GatheringHostSubjectKind) bool {
	switch value {
	case contract.GatheringHostSubjectKindPersona,
		contract.GatheringHostSubjectKindEntityHomepage,
		contract.GatheringHostSubjectKindCircle:
		return true
	default:
		return false
	}
}

type queryCursor struct {
	Kind             string     `json:"kind"`
	StartAt          *time.Time `json:"startAt,omitempty"`
	GatheringID      string     `json:"gatheringId,omitempty"`
	ReviewExpectedBy *time.Time `json:"reviewExpectedBy,omitempty"`
	PersonaID        string     `json:"personaId,omitempty"`
	AttemptNo        int64      `json:"attemptNo,omitempty"`
}

func encodePublicCursor(value GatheringReadModel, kind string) (string, error) {
	return encodeQueryCursor(queryCursor{
		Kind: kind, StartAt: cloneTimePointer(value.Schedule.StartAt), GatheringID: value.ID,
	})
}

func decodePublicCursor(raw, expectedKind string) (PublicListPosition, error) {
	if strings.TrimSpace(raw) == "" {
		return PublicListPosition{}, nil
	}
	cursor, err := decodeQueryCursor(raw)
	if err != nil {
		return PublicListPosition{}, err
	}
	if cursor.Kind != expectedKind || strings.TrimSpace(cursor.GatheringID) == "" {
		return PublicListPosition{}, fmt.Errorf("cursor does not match %s listing", expectedKind)
	}
	return PublicListPosition{
		StartAt: cloneOptionalTimePointer(cursor.StartAt), GatheringID: cursor.GatheringID,
	}, nil
}

func encodeApplicationCursor(value ParticipationRecord) (string, error) {
	return encodeQueryCursor(queryCursor{
		Kind: "applications", ReviewExpectedBy: cloneTimePointer(value.ReviewExpectedBy),
		PersonaID: value.PersonaID, AttemptNo: value.AttemptNo,
	})
}

func decodeApplicationCursor(raw string) (ApplicationListPosition, error) {
	if strings.TrimSpace(raw) == "" {
		return ApplicationListPosition{}, nil
	}
	cursor, err := decodeQueryCursor(raw)
	if err != nil {
		return ApplicationListPosition{}, err
	}
	if cursor.Kind != "applications" || strings.TrimSpace(cursor.PersonaID) == "" {
		return ApplicationListPosition{}, fmt.Errorf("cursor does not match application listing")
	}
	return ApplicationListPosition{
		ReviewExpectedBy: cloneOptionalTimePointer(cursor.ReviewExpectedBy),
		PersonaID:        cursor.PersonaID, AttemptNo: cursor.AttemptNo,
	}, nil
}

func encodeRosterCursor(value ParticipationRecord) (string, error) {
	return encodeQueryCursor(queryCursor{Kind: "roster", PersonaID: value.PersonaID})
}

func decodeRosterCursor(raw string) (RosterListPosition, error) {
	if strings.TrimSpace(raw) == "" {
		return RosterListPosition{}, nil
	}
	cursor, err := decodeQueryCursor(raw)
	if err != nil {
		return RosterListPosition{}, err
	}
	if cursor.Kind != "roster" || strings.TrimSpace(cursor.PersonaID) == "" {
		return RosterListPosition{}, fmt.Errorf("cursor does not match roster listing")
	}
	return RosterListPosition{PersonaID: cursor.PersonaID}, nil
}

func encodeQueryCursor(cursor queryCursor) (string, error) {
	encoded, err := json.Marshal(cursor)
	if err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(encoded), nil
}

func decodeQueryCursor(raw string) (queryCursor, error) {
	encoded, err := base64.RawURLEncoding.DecodeString(strings.TrimSpace(raw))
	if err != nil {
		return queryCursor{}, fmt.Errorf("decode keyset cursor: %w", err)
	}
	var cursor queryCursor
	if err := json.Unmarshal(encoded, &cursor); err != nil {
		return queryCursor{}, fmt.Errorf("decode keyset cursor payload: %w", err)
	}
	return cursor, nil
}

func invalidCursor(err error) error {
	return circleerrors.AppErrorFromInvalidArgument("invalid Gathering keyset cursor: " + err.Error())
}

// These factories mirror current canonical errors.yaml while source
// generated/errors.go is temporarily stale. They should collapse back to the
// generated factories when canonical codegen is refreshed.
func gatheringHostAuthorityInvalid(debug string) error {
	return rterr.NewAppError(
		rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "gathering_host_authority_invalid"),
		"当前 Host 授权无效，请重新选择或验证",
		debug,
	).WithMetadata("gathering_host_authority_invalid", 403).WithRecovery("surface", 0)
}

func gatheringActiveParticipationRequired(debug string) error {
	return rterr.NewAppError(
		rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "gathering_active_participation_required"),
		"需要有效参与资格才能继续",
		debug,
	).WithMetadata("gathering_active_participation_required", 403).WithRecovery("surface", 0)
}

func gatheringAccessRevoked(debug string) error {
	return rterr.NewAppError(
		rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "gathering_access_revoked"),
		"你的活动访问权限已被撤销",
		debug,
	).WithMetadata("gathering_access_revoked", 403).WithRecovery("surface", 0)
}
