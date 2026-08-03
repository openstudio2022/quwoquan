package http

import (
	"context"
	"errors"
	"net/http"

	credentialapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	accountlifecycleapp "quwoquan_service/services/user-service/internal/account/user_account/application"
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
	greetingapp "quwoquan_service/services/user-service/internal/relationship/greeting_request/application"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
)

type objectRouteRegistrar interface{ RegisterRoutes(*http.ServeMux) }

// UserHandler composes the UserAccount HTTP surface. Concrete HTTP resources
// keep their operations in focused files in this inbound adapter package.
type UserHandler struct {
	profile                    *application.ProfileService
	search                     *application.SearchService
	relationship               relationshipapp.Facade
	greeting                   *greetingapp.GreetingService
	settingsRoutes             objectRouteRegistrar
	auth                       *application.AuthService
	credentialQueries          *credentialapp.CredentialQueryFacade
	deviceRegistrationRoutes   objectRouteRegistrar
	persona                    *application.PersonaService
	interestProfile            *application.InterestProfileService
	subjectFollowRoutes        objectRouteRegistrar
	followedSubjectVisitRoutes objectRouteRegistrar
	followingSubjectRoutes     objectRouteRegistrar
	accountLifecycle           *accountlifecycleapp.CloseAccountFacade
	accountEnforcement         *accountlifecycleapp.AccountEnforcementCommandFacade
	accountSecurity            accountports.AccountSecurityReader
	wechatLogin                *application.FederatedLoginFacade
	alipayLogin                *application.FederatedLoginFacade
	qqLogin                    *application.FederatedLoginFacade
}

// WithAccountLifecycle 注入 UserAccount 生命周期终态 facade（CloseAccount）。
func (h *UserHandler) WithAccountLifecycle(
	facade *accountlifecycleapp.CloseAccountFacade,
) *UserHandler {
	h.accountLifecycle = facade
	return h
}

// WithAccountEnforcement 注入受信 Suspend/Restore command facade。
func (h *UserHandler) WithAccountEnforcement(
	facade *accountlifecycleapp.AccountEnforcementCommandFacade,
) *UserHandler {
	h.accountEnforcement = facade
	return h
}

// WithAccountSecurityReader 注入认证后终端用户请求的 fail-closed 安全状态校验。
func (h *UserHandler) WithAccountSecurityReader(
	reader accountports.AccountSecurityReader,
) *UserHandler {
	h.accountSecurity = reader
	return h
}

// WithInterestProfile 注入用户兴趣画像的只读 application service。
func (h *UserHandler) WithInterestProfile(
	service *application.InterestProfileService,
) *UserHandler {
	h.interestProfile = service
	return h
}

// WithFederatedLogins injects the explicitly bound authorization capabilities
// for the corresponding published HTTP routes.
func (h *UserHandler) WithFederatedLogins(
	wechat *application.FederatedLoginFacade,
	alipay *application.FederatedLoginFacade,
	qq *application.FederatedLoginFacade,
) *UserHandler {
	h.wechatLogin = wechat
	h.alipayLogin = alipay
	h.qqLogin = qq
	return h
}

const (
	PullUserSyncPath   = "/user/sync"
	LoginAnonymousPath = "/auth/login/anonymous"
)

func NewUserHandler(
	profile *application.ProfileService,
	search *application.SearchService,
	relationship relationshipapp.Facade,
	greeting *greetingapp.GreetingService,
	auth *application.AuthService,
	credentialQueries *credentialapp.CredentialQueryFacade,
	persona *application.PersonaService,
	interestProfile *application.InterestProfileService,
) (*UserHandler, error) {
	if credentialQueries == nil {
		return nil, errors.New("CredentialBinding query facade is required")
	}
	handler := &UserHandler{
		profile:           profile,
		search:            search,
		relationship:      relationship,
		greeting:          greeting,
		auth:              auth,
		credentialQueries: credentialQueries,
		persona:           persona,
		interestProfile:   interestProfile,
	}
	return handler, nil
}

func (h *UserHandler) WithDeviceRegistrationRoutes(routes objectRouteRegistrar) *UserHandler {
	h.deviceRegistrationRoutes = routes
	return h
}

func (h *UserHandler) WithUserSettingsRoutes(routes objectRouteRegistrar) *UserHandler {
	h.settingsRoutes = routes
	return h
}

func (h *UserHandler) WithSubjectObjectRoutes(
	subjectFollow objectRouteRegistrar,
	followedSubjectVisit objectRouteRegistrar,
	followingSubject objectRouteRegistrar,
) *UserHandler {
	h.subjectFollowRoutes = subjectFollow
	h.followedSubjectVisitRoutes = followedSubjectVisit
	h.followingSubjectRoutes = followingSubject
	return h
}

// ResolveActorPersonaID is the composition port used by relationship object
// adapters. Identity selection remains owned by UserAccount; object adapters do
// not trust headers or request bodies on their own.
func (h *UserHandler) ResolveActorPersonaID(
	ctx context.Context,
	r *http.Request,
	explicitActorID string,
) (string, error) {
	return h.resolveActorPersonaID(ctx, r, explicitActorID)
}

func (h *UserHandler) Routes() http.Handler {
	mux := http.NewServeMux()
	h.RegisterRoutes(mux)
	return h.WrapAccountSecurity(mux)
}

// RegisterRoutes 只注册 UserAccount 所拥有的 HTTP 路由；跨对象路由由 cmd
// composition root 装配到同一个 mux。
func (h *UserHandler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /healthz", h.handleHealthz)
	mux.HandleFunc("GET /livez", h.handleHealthz)
	mux.HandleFunc("GET /startupz", h.handleHealthz)

	mux.HandleFunc("GET /user/profile/{userId}", h.handleGetProfile)
	mux.HandleFunc("GET /user/profile/edit-snapshot", h.handleGetProfileEditSnapshot)
	mux.HandleFunc("GET /user/profile/qr-card", h.handleGetProfileQRCard)
	mux.HandleFunc("GET /public/profile/qr/resolve", h.handleResolveProfileQRToken)
	mux.HandleFunc("PATCH /user/profile", h.handleUpdateProfile)
	mux.HandleFunc("POST "+PullUserSyncPath, h.handlePullUserSync)
	mux.HandleFunc("GET /me", h.handleGetMeProfile)
	mux.HandleFunc("GET /user/{personaId}", h.handleGetPersonaProfile)
	mux.HandleFunc("GET /user/personas/{personaId}/homepage-bundle", h.handleGetUserHomepageBundle)
	mux.HandleFunc("GET /user/search/social-relations", h.handleSearchSocialRelations)

	mux.HandleFunc("POST /user/personas/{targetPersonaId}/follow", h.handleFollow)
	mux.HandleFunc("DELETE /user/personas/{targetPersonaId}/follow", h.handleUnfollow)
	mux.HandleFunc("GET /user/personas/{personaId}/following", h.handleListFollowing)
	mux.HandleFunc("GET /user/personas/{personaId}/followers", h.handleListFollowers)
	mux.HandleFunc("GET /user/personas/{personaId}/relationship", h.handleGetRelationship)
	mux.HandleFunc("GET /user/personas/{personaId}/relationship/capability", h.handleGetRelationshipCapability)

	mux.HandleFunc("POST /user/personas/{targetPersonaId}/block", h.handleBlock)
	mux.HandleFunc("DELETE /user/personas/{targetPersonaId}/block", h.handleUnblock)
	mux.HandleFunc("GET /user/blocked", h.handleListBlocked)

	for _, registrar := range []objectRouteRegistrar{
		h.settingsRoutes,
		h.deviceRegistrationRoutes,
		h.subjectFollowRoutes,
		h.followedSubjectVisitRoutes,
		h.followingSubjectRoutes,
	} {
		if registrar != nil {
			registrar.RegisterRoutes(mux)
		}
	}
	h.registerAccountLifecycleRoutes(mux)

	mux.HandleFunc("GET /user/personas", h.handleListPersonas)
	mux.HandleFunc("GET /user/personas/summary", h.handleGetPersonaManagementSummary)
	mux.HandleFunc("GET /user/personas/active", h.handleGetActivePersonaContext)
	mux.HandleFunc("POST /user/personas", h.handleCreatePersona)
	mux.HandleFunc("PATCH /user/personas/{personaId}", h.handleUpdatePersona)
	mux.HandleFunc("POST /user/personas/{personaId}/profile-sync", h.handleApplyPersonaProfileSync)
	mux.HandleFunc("GET /user/personas/{personaId}/lifecycle-guard", h.handleGetPersonaLifecycleGuard)
	mux.HandleFunc("POST /user/personas/{personaId}/retire", h.handleRetirePersona)
	mux.HandleFunc("POST /user/personas/{personaId}/activate", h.handleActivatePersona)

	mux.HandleFunc("GET /users/{userId}/interest-profile", h.handleGetUserInterestProfile)

	// Auth & Credentials
	mux.HandleFunc("POST /auth/otp/send", h.handleSendOtp)
	mux.HandleFunc("POST /internal/auth/otp-deliveries:callback", h.handleOtpDeliveryCallback)
	mux.HandleFunc("POST /auth/login/phone", h.handleLoginWithPhone)
	mux.HandleFunc("POST /auth/authorization/alipay", h.handleCreateAlipayAuthorizationRequest)
	mux.HandleFunc("POST /auth/login/wechat", h.handleLoginWithWechat)
	mux.HandleFunc("POST /auth/login/alipay", h.handleLoginWithAlipay)
	mux.HandleFunc("POST /auth/login/qq", h.handleLoginWithQq)
	mux.HandleFunc("POST /auth/login/one-tap", h.handleOneTapLogin)
	mux.HandleFunc("POST /auth/login/one-tap/hint", h.handleOneTapLoginHint)
	mux.HandleFunc("POST "+LoginAnonymousPath, h.handleAnonymousLogin)
	mux.HandleFunc("POST /auth/token/refresh", h.handleRefreshToken)
	mux.HandleFunc("POST /auth/logout", h.handleLogout)
	mux.HandleFunc("GET /owner/credentials", h.handleListCredentials)
	mux.HandleFunc("POST /owner/credentials/phone/bind", h.handleBindPhoneCredential)
	mux.HandleFunc("POST /owner/credentials/carrier-phone/bind", h.handleBindCarrierPhoneCredential)
	mux.HandleFunc("DELETE /owner/credentials/{credType}", h.handleUnbindCredential)
}

// WrapAccountSecurity 将账号终态保护应用到完整的 user-service HTTP surface。
func (h *UserHandler) WrapAccountSecurity(next http.Handler) http.Handler {
	return h.enforceAccountSecurity(next)
}
