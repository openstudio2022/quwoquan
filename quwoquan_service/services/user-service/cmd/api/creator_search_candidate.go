package bootstrap

import (
	"net/http"
	inbound "quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/http"
	app "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	creator "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/application"
)

func registerCreatorSearchCandidate(mux *http.ServeMux, store creator.SearchCandidateStore, personas app.CreatorSearchPersonaReader, accounts app.CreatorSearchAccountReader, environment string) {
	inbound.NewCreatorSearchCandidateHandler(app.NewCreatorSearchCandidateQueryFacade(creator.NewSearchCandidateReader(store), personas, accounts, environment)).Register(mux)
}
