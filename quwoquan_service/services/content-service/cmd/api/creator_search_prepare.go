package bootstrap

import (
	"fmt"
	"quwoquan_service/runtime/servicekit"
	inbound "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/creatorsearch"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
	"regexp"
)

func registerCreatorSearchPrepare(asm *servicekit.Assembly, cfg *config) error {
	if !regexp.MustCompile(`^sha256:[0-9a-f]{64}$`).MatchString(cfg.CreatorSearch.BindingDigest) {
		return fmt.Errorf("release preparation requires canonical data-plane binding")
	}
	user, err := asm.Auth.ServiceCredentials("user.creator_search.candidate.read")
	if err != nil {
		return err
	}
	prepare, err := asm.Auth.ServiceCredentials("search.release.prepare")
	if err != nil {
		return err
	}
	query, err := asm.Auth.ServiceCredentials("search.release.read")
	if err != nil {
		return err
	}
	entity, err := asm.Auth.ServiceCredentials("entity.release.source.read")
	if err != nil {
		return err
	}
	client, err := creatorsearch.NewClient(asm.Identity.ServiceBaseURL("user-service"), asm.Identity.ServiceBaseURL("search-service"), user, prepare, query)
	if err != nil {
		return err
	}
	sources := creatorsearch.NewSources(client, asm.Identity.ServiceBaseURL("entity-service"), entity)
	sources.SetPostReader(releaseimport.NewPostCandidateReader(asm.MongoDB, sources))
	publisher := releaseimport.NewQueryPublisher(asm.MongoDB)
	if err = publisher.EnsureIndexes(asm.Context); err != nil {
		return err
	}
	facade, err := app.NewReleaseQueryPrepareFacade(sources, client, publisher, asm.Identity.AppEnv, cfg.CreatorSearch.BindingDigest)
	if err != nil {
		return err
	}
	inbound.RegisterPostCandidateSafety(asm.Mux, releaseimport.NewCandidateSafetyReader(asm.MongoDB, asm.Identity.AppEnv))
	inbound.NewReleaseQueriesHandler(facade, sources).Register(asm.Mux)
	inbound.NewReleaseCommitReceiptHandler(releaseimport.NewCommitReceiptReader(asm.MongoDB, asm.Identity.AppEnv), asm.Identity.AppEnv).Register(asm.Mux)
	return nil
}
