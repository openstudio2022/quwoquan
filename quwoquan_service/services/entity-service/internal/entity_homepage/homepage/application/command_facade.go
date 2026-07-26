package homepage

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
	homepageports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
)

const receiptTTL = 24 * time.Hour

const (
	EventCandidateIntaken     = "HomepageCandidateIntaken"
	EventPublished            = "HomepagePublished"
	EventBasicsUpdated        = "HomepageClaimedBasicsUpdated"
	EventClaimProjection      = "HomepageClaimProjectionApplied"
	EventClaimPending         = "HomepageClaimPendingApplied"
	EventOffline              = "HomepageTakenOffline"
	EventReviewSummaryApplied = "HomepageReviewSummaryApplied"
	EventImported             = "HomepageImportedProjectionApplied"
)

type CommandMeta struct {
	ActorID        string
	IdempotencyKey string
}

type CommittedEvent struct {
	Type     string
	Snapshot homepagemodel.Snapshot
}

// CommitObserver 是 outbox 成功提交后的同进程 best-effort 投影边界。
// durable homepage_outbox 才是事实源；observer 失败不得回滚主事务。
type CommitObserver interface {
	OnHomepageCommitted(ctx context.Context, event CommittedEvent)
}

type CommandFacade struct {
	store    homepageports.AggregateStore
	reader   homepageports.Reader
	observer CommitObserver
	now      func() time.Time
}

func NewCommandFacade(store homepageports.AggregateStore, reader homepageports.Reader) (*CommandFacade, error) {
	if store == nil || reader == nil {
		return nil, errors.New("homepage command facade requires aggregate store and reader")
	}
	return &CommandFacade{store: store, reader: reader, now: time.Now}, nil
}

func (f *CommandFacade) WithObserver(observer CommitObserver) *CommandFacade {
	f.observer = observer
	return f
}

func (f *CommandFacade) SetClock(now func() time.Time) {
	if now != nil {
		f.now = now
	}
}

func (f *CommandFacade) IntakeCandidate(
	ctx context.Context,
	meta CommandMeta,
	input Input,
	sourceType string,
) (View, error) {
	return f.intake(ctx, meta, input, sourceType, false)
}

func (f *CommandFacade) SuggestCandidate(
	ctx context.Context,
	meta CommandMeta,
	input Input,
) (View, error) {
	if err := validateSuggestionLookupAliases(input.LookupAliases); err != nil {
		return View{}, err
	}
	return f.intake(ctx, meta, input, "user_suggested", false)
}

func (f *CommandFacade) intake(
	ctx context.Context,
	meta CommandMeta,
	input Input,
	sourceType string,
	publishImmediately bool,
) (View, error) {
	if err := validateMeta(meta); err != nil {
		return View{}, err
	}
	if err := validateInput(input); err != nil {
		return View{}, err
	}
	command := struct {
		Input      Input
		SourceType string
		Published  bool
	}{input, strings.TrimSpace(sourceType), publishImmediately}
	digest, err := commandDigest("IntakeHomepageCandidate", command)
	if err != nil {
		return View{}, err
	}
	if replayed, found, replayErr := f.replay(ctx, meta, "IntakeHomepageCandidate", digest); replayErr != nil || found {
		return replayed, replayErr
	}
	now := f.now().UTC()
	aggregate, createErr := homepagemodel.Intake(homepagemodel.IntakeParams{
		Title:                input.Title,
		Subtitle:             input.Subtitle,
		HomepageType:         input.HomepageType,
		CanonicalEntityID:    input.CanonicalEntityID,
		LookupAliases:        input.LookupAliases,
		ObjectPageTemplate:   input.ObjectPageTemplate,
		SourceType:           strings.TrimSpace(sourceType),
		CategoryTags:         input.CategoryTags,
		CoverURL:             input.CoverURL,
		Address:              input.Address,
		City:                 input.City,
		Location:             input.Location,
		IntroductionMarkdown: input.IntroductionMarkdown,
		IntroductionAssets:   input.IntroductionAssets,
		PublishImmediately:   publishImmediately,
		Now:                  now,
	})
	if createErr != nil {
		return View{}, mapDomainError(createErr)
	}
	if existing, found, loadErr := f.store.Load(ctx, aggregate.ID()); loadErr != nil {
		return View{}, unavailable(loadErr)
	} else if found {
		if snapshotsEquivalent(existing.Snapshot(), aggregate.Snapshot()) {
			return f.recordNoop(ctx, meta, existing, "IntakeHomepageCandidate", digest)
		}
		return View{}, generated.AppErrorFromVersionConflict("stable homepage identity already exists")
	}
	return f.commit(ctx, meta, aggregate, 0, "IntakeHomepageCandidate", digest, EventCandidateIntaken, now)
}

func (f *CommandFacade) PublishCandidate(
	ctx context.Context,
	meta CommandMeta,
	homepageID string,
) (View, error) {
	return f.mutate(ctx, meta, homepageID, "PublishHomepageCandidate", func(aggregate *homepagemodel.Homepage) (string, error) {
		if aggregate.Status() == homepagemodel.StatusPublished {
			return "", nil
		}
		if err := aggregate.Publish(f.now().UTC()); err != nil {
			return "", err
		}
		return EventPublished, nil
	})
}

func (f *CommandFacade) UpdateClaimedBasics(
	ctx context.Context,
	meta CommandMeta,
	homepageID string,
	input BasicInput,
) (View, error) {
	return f.mutateWithCommand(ctx, meta, homepageID, "UpdateClaimedHomepageBasics", input, func(aggregate *homepagemodel.Homepage) (string, error) {
		ownerPersonaID := strings.TrimSpace(aggregate.Snapshot().OwnerSubAccountID)
		if ownerPersonaID == "" || strings.TrimSpace(meta.ActorID) != ownerPersonaID {
			return "", generated.AppErrorFromPermissionDenied(
				"claimed homepage basics can only be updated by its owner persona",
			)
		}
		err := aggregate.UpdateClaimedBasics(homepagemodel.BasicChanges{
			Title:           input.Title,
			Subtitle:        input.Subtitle,
			CategoryTags:    input.CategoryTags,
			CoverURL:        input.CoverURL,
			Address:         input.Address,
			City:            input.City,
			Location:        input.Location,
			Verified:        input.Verified,
			EstablishedYear: input.EstablishedYear,
			Now:             f.now().UTC(),
		})
		return EventBasicsUpdated, err
	})
}

func (f *CommandFacade) ApplyClaimApproved(
	ctx context.Context,
	meta CommandMeta,
	homepageID string,
	ownerUserID string,
	ownerSubAccountID string,
	approved bool,
) (View, error) {
	command := struct {
		OwnerUserID       string
		OwnerSubAccountID string
		Approved          bool
	}{ownerUserID, ownerSubAccountID, approved}
	return f.mutateWithCommand(ctx, meta, homepageID, "ApplyHomepageClaimApproved", command, func(aggregate *homepagemodel.Homepage) (string, error) {
		err := aggregate.ApplyClaimApproved(ownerUserID, ownerSubAccountID, approved, f.now().UTC())
		return EventClaimProjection, err
	})
}

func (f *CommandFacade) ApplyClaimPending(
	ctx context.Context,
	meta CommandMeta,
	homepageID string,
) (View, error) {
	return f.mutate(ctx, meta, homepageID, "ApplyHomepageClaimPending", func(aggregate *homepagemodel.Homepage) (string, error) {
		if aggregate.Snapshot().ClaimStatus == "pending_review" {
			return "", nil
		}
		if err := aggregate.ApplyClaimPending(f.now().UTC()); err != nil {
			return "", err
		}
		return EventClaimPending, nil
	})
}

func (f *CommandFacade) ApplyOffline(
	ctx context.Context,
	meta CommandMeta,
	homepageID string,
) (View, error) {
	return f.mutate(ctx, meta, homepageID, "ApplyHomepageOffline", func(aggregate *homepagemodel.Homepage) (string, error) {
		if aggregate.Status() == homepagemodel.StatusOffline {
			return "", nil
		}
		if err := aggregate.ApplyOffline(f.now().UTC()); err != nil {
			return "", err
		}
		return EventOffline, nil
	})
}

func (f *CommandFacade) ApplyReviewSummary(
	ctx context.Context,
	meta CommandMeta,
	homepageID string,
	averageRating *float64,
	ratingCount int,
	highlightTags []string,
) (View, error) {
	command := struct {
		AverageRating *float64
		RatingCount   int
		HighlightTags []string
	}{averageRating, ratingCount, highlightTags}
	return f.mutateWithCommand(ctx, meta, homepageID, "ApplyHomepageReviewSummary", command, func(aggregate *homepagemodel.Homepage) (string, error) {
		err := aggregate.ApplyReviewSummary(averageRating, ratingCount, highlightTags, f.now().UTC())
		return EventReviewSummaryApplied, err
	})
}

func (f *CommandFacade) mutate(
	ctx context.Context,
	meta CommandMeta,
	homepageID string,
	commandName string,
	mutation func(*homepagemodel.Homepage) (string, error),
) (View, error) {
	return f.mutateWithCommand(ctx, meta, homepageID, commandName, struct{}{}, mutation)
}

func (f *CommandFacade) mutateWithCommand(
	ctx context.Context,
	meta CommandMeta,
	homepageID string,
	commandName string,
	commandPayload any,
	mutation func(*homepagemodel.Homepage) (string, error),
) (View, error) {
	if err := validateMeta(meta); err != nil {
		return View{}, err
	}
	digest, err := commandDigest(commandName, struct {
		HomepageID string
		Payload    any
	}{strings.TrimSpace(homepageID), commandPayload})
	if err != nil {
		return View{}, err
	}
	if replayed, found, replayErr := f.replay(ctx, meta, commandName, digest); replayErr != nil || found {
		return replayed, replayErr
	}
	for attempt := 0; attempt < 3; attempt++ {
		aggregate, found, loadErr := f.loadResolved(ctx, homepageID)
		if loadErr != nil {
			return View{}, unavailable(loadErr)
		}
		if !found {
			return View{}, generated.AppErrorFromHomepageNotFound("homepage not found")
		}
		expected := aggregate.Version()
		eventType, mutationErr := mutation(aggregate)
		if mutationErr != nil {
			return View{}, mapDomainError(mutationErr)
		}
		if eventType == "" {
			return f.recordNoop(ctx, meta, aggregate, commandName, digest)
		}
		now := aggregate.Snapshot().UpdatedAt
		result, commitErr := f.commit(ctx, meta, aggregate, expected, commandName, digest, eventType, now)
		if commitErr == nil {
			return result, nil
		}
		if !isVersionConflict(commitErr) || attempt == 2 {
			return View{}, commitErr
		}
	}
	panic("unreachable homepage mutation retry")
}

func (f *CommandFacade) loadResolved(
	ctx context.Context,
	rawID string,
) (*homepagemodel.Homepage, bool, error) {
	snapshot, found, err := f.reader.FindExact(ctx, homepageports.ExactLookup{
		ID:          strings.TrimSpace(rawID),
		LookupAlias: homepagemodel.NormalizeLookupAlias(rawID),
	})
	if err != nil || !found {
		return nil, found, err
	}
	return f.store.Load(ctx, snapshot.ID)
}

func (f *CommandFacade) replay(
	ctx context.Context,
	meta CommandMeta,
	commandName string,
	digest string,
) (View, bool, error) {
	result, found, err := f.store.FindReceipt(
		ctx,
		strings.TrimSpace(meta.ActorID),
		strings.TrimSpace(meta.IdempotencyKey),
		commandName,
		digest,
	)
	if err != nil {
		return View{}, false, unavailable(err)
	}
	if !found {
		return View{}, false, nil
	}
	if result.Aggregate == nil {
		return View{}, false, unavailable(errors.New("homepage receipt has no aggregate"))
	}
	return ViewFromSnapshot(result.Aggregate.Snapshot()), true, nil
}

func (f *CommandFacade) recordNoop(
	ctx context.Context,
	meta CommandMeta,
	aggregate *homepagemodel.Homepage,
	commandName string,
	digest string,
) (View, error) {
	result, err := f.store.RecordNoopReceipt(ctx, homepageports.NoopReceipt{
		Aggregate:        aggregate,
		ActorID:          strings.TrimSpace(meta.ActorID),
		IdempotencyKey:   strings.TrimSpace(meta.IdempotencyKey),
		CommandName:      commandName,
		CommandDigest:    digest,
		ReceiptExpiresAt: f.now().UTC().Add(receiptTTL),
	})
	if err != nil {
		return View{}, unavailable(err)
	}
	if result.Aggregate == nil {
		return View{}, unavailable(errors.New("homepage no-op receipt has no aggregate"))
	}
	return ViewFromSnapshot(result.Aggregate.Snapshot()), nil
}

func (f *CommandFacade) commit(
	ctx context.Context,
	meta CommandMeta,
	aggregate *homepagemodel.Homepage,
	expectedVersion int64,
	commandName string,
	digest string,
	eventType string,
	now time.Time,
) (View, error) {
	snapshot := aggregate.Snapshot()
	payload, err := json.Marshal(LifecycleEventPayloadFromSnapshot(snapshot))
	if err != nil {
		return View{}, unavailable(err)
	}
	eventID := stableEventID(meta.ActorID, meta.IdempotencyKey, eventType)
	result, err := f.store.Commit(ctx, homepageports.Commit{
		Aggregate:        aggregate,
		ExpectedVersion:  expectedVersion,
		ActorID:          strings.TrimSpace(meta.ActorID),
		IdempotencyKey:   strings.TrimSpace(meta.IdempotencyKey),
		CommandName:      commandName,
		CommandDigest:    digest,
		ReceiptExpiresAt: now.UTC().Add(receiptTTL),
		Event: homepageports.OutboxEvent{
			EventID:          eventID,
			EventType:        eventType,
			AggregateID:      aggregate.ID(),
			AggregateVersion: aggregate.Version(),
			Payload:          payload,
			OccurredAt:       now.UTC(),
		},
	})
	if err != nil {
		return View{}, wrapStoreError(err)
	}
	if result.Aggregate == nil {
		return View{}, unavailable(errors.New("homepage commit has no aggregate"))
	}
	committed := result.Aggregate.Snapshot()
	if f.observer != nil && !result.Replayed {
		f.observer.OnHomepageCommitted(ctx, CommittedEvent{Type: eventType, Snapshot: committed})
	}
	return ViewFromSnapshot(committed), nil
}

func validateMeta(meta CommandMeta) error {
	if strings.TrimSpace(meta.ActorID) == "" {
		return generated.AppErrorFromPermissionDenied("homepage command requires actor")
	}
	if strings.TrimSpace(meta.IdempotencyKey) == "" {
		return generated.AppErrorFromInvalidArgument("homepage command requires idempotency key")
	}
	return nil
}

func validateInput(input Input) error {
	if strings.TrimSpace(input.Title) == "" {
		return generated.AppErrorFromInvalidArgument("homepage title is empty")
	}
	if !homepagemodel.ValidHomepageType(input.HomepageType) {
		return generated.AppErrorFromInvalidHomepageType("unsupported homepage type")
	}
	return nil
}

// validateSuggestionLookupAliases narrows a user suggestion's persisted lookup
// identity to the one first-party location.place it was opened from. General
// aliases are controlled by internal import/intake flows and must never be
// client-supplied, otherwise a suggestion could hijack another homepage's
// redirect identity.
func validateSuggestionLookupAliases(aliases []string) error {
	if len(aliases) > 1 {
		return generated.AppErrorFromInvalidArgument("homepage suggestion accepts at most one source place id")
	}
	if len(aliases) == 0 {
		return nil
	}
	if !isCanonicalPlaceID(aliases[0]) {
		return generated.AppErrorFromInvalidArgument("homepage suggestion source place id is invalid")
	}
	return nil
}

func isCanonicalPlaceID(raw string) bool {
	const prefix = "place_"
	id := strings.TrimSpace(raw)
	if len(id) != len(prefix)+16 || !strings.HasPrefix(id, prefix) {
		return false
	}
	for _, char := range id[len(prefix):] {
		if !((char >= '0' && char <= '9') || (char >= 'a' && char <= 'f')) {
			return false
		}
	}
	return true
}

func commandDigest(name string, command any) (string, error) {
	payload, err := json.Marshal(command)
	if err != nil {
		return "", unavailable(err)
	}
	sum := sha256.Sum256(append([]byte(name+"\x00"), payload...))
	return hex.EncodeToString(sum[:]), nil
}

func stableEventID(actorID, key, eventType string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + strings.TrimSpace(key) + "\x00" + eventType))
	return "hp-event-" + hex.EncodeToString(sum[:16])
}

func snapshotsEquivalent(left, right homepagemodel.Snapshot) bool {
	left.Version = 0
	right.Version = 0
	left.CreatedAt = time.Time{}
	right.CreatedAt = time.Time{}
	left.UpdatedAt = time.Time{}
	right.UpdatedAt = time.Time{}
	return fmt.Sprintf("%#v", left) == fmt.Sprintf("%#v", right)
}

func mapDomainError(err error) error {
	switch {
	case errors.Is(err, homepagemodel.ErrInvalidHomepageType):
		return generated.AppErrorFromInvalidHomepageType(err.Error())
	case errors.Is(err, homepagemodel.ErrHomepageNotClaimed):
		return generated.AppErrorFromPermissionDenied(err.Error())
	case errors.Is(err, homepagemodel.ErrInvalidTransition),
		errors.Is(err, homepagemodel.ErrCanonicalIdentityEdit),
		errors.Is(err, homepagemodel.ErrInvalidHomepage):
		return generated.AppErrorFromInvalidArgument(err.Error())
	default:
		return unavailable(err)
	}
}

func isVersionConflict(err error) bool {
	var appError *rterr.AppError
	return errors.As(err, &appError) &&
		appError.Code.String() == generated.ErrVersionConflict.Error()
}

func wrapStoreError(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return unavailable(err)
}

func unavailable(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return generated.AppErrorFromInternalError(err.Error())
}
