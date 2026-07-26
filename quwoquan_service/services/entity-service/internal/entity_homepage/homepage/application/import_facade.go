package homepage

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"

	"quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
	homepageports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
)

type ImportMode string

const (
	ImportModeUpsert ImportMode = "upsert"
	ImportModeSync   ImportMode = "sync"
)

type ImportedInput struct {
	EntityRef            string
	Title                string
	HomepageType         string
	City                 string
	IntroductionMarkdown string
	IntroductionAssets   []IntroductionAsset
	PrimarySource        *Source
	SourceURLs           []string
	CategoryTags         []string
	SourceTaskID         string
}

type ImportRequest struct {
	Mode            ImportMode
	SourceOwner     string
	SourceReleaseID string
	RunID           string
	Inputs          []ImportedInput
}

type ImportReport struct {
	Mode                  ImportMode        `json:"mode"`
	SourceOwner           string            `json:"sourceOwner"`
	Created               []string          `json:"created"`
	Updated               []string          `json:"updated"`
	Offlined              []string          `json:"offlined"`
	Skipped               []string          `json:"skipped"`
	EntityRefToHomepageID map[string]string `json:"entityRefToHomepageId"`
}

type ImportFacade struct {
	commands *CommandFacade
	store    homepageports.AggregateStore
	reader   homepageports.Reader
	now      func() time.Time
}

func NewImportFacade(
	commands *CommandFacade,
	store homepageports.AggregateStore,
	reader homepageports.Reader,
) (*ImportFacade, error) {
	if commands == nil || store == nil || reader == nil {
		return nil, fmt.Errorf("homepage import facade requires command facade, store and reader")
	}
	return &ImportFacade{commands: commands, store: store, reader: reader, now: time.Now}, nil
}

func (f *ImportFacade) SetClock(now func() time.Time) {
	if now != nil {
		f.now = now
	}
}

// Reconcile 按 sourceOwner+sourceEntityRef 做幂等 upsert；sync 仅下线同来源中
// 不在 desired state 的对象。每个对象独立 CAS+receipt+outbox，禁止全局快照提交。
func (f *ImportFacade) Reconcile(ctx context.Context, request ImportRequest) (ImportReport, error) {
	request.Mode = ImportMode(strings.TrimSpace(string(request.Mode)))
	request.SourceOwner = strings.TrimSpace(request.SourceOwner)
	request.SourceReleaseID = strings.TrimSpace(request.SourceReleaseID)
	request.RunID = strings.TrimSpace(request.RunID)
	if request.Mode != ImportModeUpsert && request.Mode != ImportModeSync {
		return ImportReport{}, generated.AppErrorFromInvalidArgument(
			fmt.Sprintf("unsupported homepage import mode %q", request.Mode),
		)
	}
	if request.SourceOwner == "" || request.SourceReleaseID == "" || request.RunID == "" {
		return ImportReport{}, generated.AppErrorFromInvalidArgument(
			"homepage import source owner, release id, and run id are required",
		)
	}
	if err := validateImportedInputs(request.Inputs); err != nil {
		return ImportReport{}, err
	}
	report := ImportReport{
		Mode:                  request.Mode,
		SourceOwner:           request.SourceOwner,
		Created:               []string{},
		Updated:               []string{},
		Offlined:              []string{},
		Skipped:               []string{},
		EntityRefToHomepageID: map[string]string{},
	}
	desired := make(map[string]struct{}, len(request.Inputs))
	for _, input := range request.Inputs {
		entityRef := strings.TrimSpace(input.EntityRef)
		desired[entityRef] = struct{}{}
		aggregate, found, err := f.store.FindBySource(ctx, request.SourceOwner, entityRef)
		if err != nil {
			return report, unavailable(err)
		}
		meta := CommandMeta{
			ActorID:        request.SourceOwner,
			IdempotencyKey: "import:" + request.RunID + ":" + entityRef,
		}
		if !found {
			created, createErr := f.createImported(ctx, meta, request, input)
			if createErr != nil {
				return report, createErr
			}
			report.Created = append(report.Created, created.ID)
			report.EntityRefToHomepageID[entityRef] = created.ID
			continue
		}
		updated, updateErr := f.updateImported(ctx, meta, aggregate, request, input)
		if updateErr != nil {
			return report, updateErr
		}
		report.Updated = append(report.Updated, updated.ID)
		report.EntityRefToHomepageID[entityRef] = updated.ID
	}
	if request.Mode == ImportModeSync {
		if err := f.offlineStale(ctx, request, desired, &report); err != nil {
			return report, err
		}
	}
	sort.Strings(report.Created)
	sort.Strings(report.Updated)
	sort.Strings(report.Offlined)
	return report, nil
}

func (f *ImportFacade) createImported(
	ctx context.Context,
	meta CommandMeta,
	request ImportRequest,
	input ImportedInput,
) (View, error) {
	now := f.now().UTC()
	canonical := homepagemodel.CanonicalEntityID(input.HomepageType, input.Title)
	aggregate, err := homepagemodel.Intake(homepagemodel.IntakeParams{
		Title:                input.Title,
		HomepageType:         input.HomepageType,
		CanonicalEntityID:    canonical,
		LookupAliases:        []string{input.EntityRef, input.Title},
		SourceType:           "official_seed",
		SourceOwner:          request.SourceOwner,
		SourceEntityRef:      input.EntityRef,
		SourceReleaseID:      request.SourceReleaseID,
		CategoryTags:         input.CategoryTags,
		City:                 input.City,
		IntroductionMarkdown: input.IntroductionMarkdown,
		IntroductionAssets:   input.IntroductionAssets,
		PrimarySource:        input.PrimarySource,
		SourceURLs:           input.SourceURLs,
		PublishImmediately:   true,
		Now:                  now,
	})
	if err != nil {
		return View{}, mapDomainError(err)
	}
	digest, err := commandDigest("ImportHomepageProjection", struct {
		Request ImportRequest
		Input   ImportedInput
	}{request, input})
	if err != nil {
		return View{}, err
	}
	if replayed, found, replayErr := f.commands.replay(ctx, meta, "ImportHomepageProjection", digest); replayErr != nil || found {
		return replayed, replayErr
	}
	return f.commands.commit(
		ctx, meta, aggregate, 0, "ImportHomepageProjection", digest, EventImported, now,
	)
}

func (f *ImportFacade) updateImported(
	ctx context.Context,
	meta CommandMeta,
	aggregate *homepagemodel.Homepage,
	request ImportRequest,
	input ImportedInput,
) (View, error) {
	digest, err := commandDigest("ImportHomepageProjection", struct {
		Request ImportRequest
		Input   ImportedInput
	}{request, input})
	if err != nil {
		return View{}, err
	}
	if replayed, found, replayErr := f.commands.replay(ctx, meta, "ImportHomepageProjection", digest); replayErr != nil || found {
		return replayed, replayErr
	}
	for attempt := 0; attempt < 3; attempt++ {
		expected := aggregate.Version()
		now := f.now().UTC()
		if err := aggregate.ApplyImportedProjection(homepagemodel.ImportedProjection{
			Title:                input.Title,
			HomepageType:         input.HomepageType,
			City:                 input.City,
			IntroductionMarkdown: input.IntroductionMarkdown,
			IntroductionAssets:   input.IntroductionAssets,
			PrimarySource:        input.PrimarySource,
			SourceURLs:           input.SourceURLs,
			CategoryTags:         input.CategoryTags,
			SourceOwner:          request.SourceOwner,
			SourceEntityRef:      input.EntityRef,
			SourceReleaseID:      request.SourceReleaseID,
			Now:                  now,
		}); err != nil {
			return View{}, mapDomainError(err)
		}
		view, commitErr := f.commands.commit(
			ctx, meta, aggregate, expected,
			"ImportHomepageProjection", digest, EventImported, now,
		)
		if commitErr == nil {
			return view, nil
		}
		if !isVersionConflict(commitErr) || attempt == 2 {
			return View{}, commitErr
		}
		reloaded, found, loadErr := f.store.FindBySource(ctx, request.SourceOwner, input.EntityRef)
		if loadErr != nil {
			return View{}, unavailable(loadErr)
		}
		if !found {
			return View{}, generated.AppErrorFromVersionConflict("imported homepage disappeared during retry")
		}
		aggregate = reloaded
	}
	panic("unreachable homepage import retry")
}

func (f *ImportFacade) offlineStale(
	ctx context.Context,
	request ImportRequest,
	desired map[string]struct{},
	report *ImportReport,
) error {
	cursor := ""
	for {
		page, err := f.reader.ListBySourceOwner(ctx, request.SourceOwner, cursor, 200)
		if err != nil {
			return unavailable(err)
		}
		for _, snapshot := range page.Items {
			if _, retained := desired[strings.TrimSpace(snapshot.SourceEntityRef)]; retained {
				continue
			}
			if snapshot.Status == homepagemodel.StatusOffline && snapshot.SourceReleaseID == request.SourceReleaseID {
				continue
			}
			meta := CommandMeta{
				ActorID:        request.SourceOwner,
				IdempotencyKey: "import-sync:" + request.RunID + ":" + snapshot.ID,
			}
			if _, err := f.commands.ApplyOffline(ctx, meta, snapshot.ID); err != nil {
				return err
			}
			report.Offlined = append(report.Offlined, snapshot.ID)
		}
		if page.NextCursor == "" {
			return nil
		}
		cursor = page.NextCursor
	}
}

func validateImportedInputs(inputs []ImportedInput) error {
	seen := make(map[string]struct{}, len(inputs))
	for index, input := range inputs {
		ref := strings.TrimSpace(input.EntityRef)
		if ref == "" {
			return generated.AppErrorFromInvalidArgument(
				fmt.Sprintf("homepage import input[%d] has empty entity ref", index),
			)
		}
		if _, duplicate := seen[ref]; duplicate {
			return generated.AppErrorFromInvalidArgument(
				fmt.Sprintf("homepage import has duplicate entity ref %q", ref),
			)
		}
		seen[ref] = struct{}{}
		if strings.TrimSpace(input.Title) == "" || !homepagemodel.ValidHomepageType(input.HomepageType) {
			return generated.AppErrorFromInvalidArgument(
				fmt.Sprintf("homepage import input %q is invalid", ref),
			)
		}
	}
	return nil
}
