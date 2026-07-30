package http

import (
	"errors"
	"net/http"

	credentialapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	registrationapp "quwoquan_service/services/user-service/internal/account/device_registration/application"
	accountlifecycleapp "quwoquan_service/services/user-service/internal/account/user_account/application"
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
	usersettingsapp "quwoquan_service/services/user-service/internal/account/user_settings/application"
	followingapp "quwoquan_service/services/user-service/internal/profile_projection/following_subject/application"
	visitapp "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/application"
	greetingapp "quwoquan_service/services/user-service/internal/relationship/greeting_request/application"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	subjectfollowapp "quwoquan_service/services/user-service/internal/relationship/subject_follow/application"
)

// UserHandler composes the UserAccount HTTP surface. Concrete HTTP resources
// keep their operations in focused files in this inbound adapter package.
type UserHandler struct {
	profile                    *application.ProfileService
	search                     *application.SearchService
	relationship               *relationshipapp.PersonaRelationshipService
	greeting                   *greetingapp.GreetingService
	settingsCommands           *usersettingsapp.UserSettingsCommandFacade
	settingsQueries            *usersettingsapp.UserSettingsQueryFacade
	auth                       *application.AuthService
	credentialQueries          *credentialapp.CredentialQueryFacade
	deviceRegistrationCommands *registrationapp.CommandFacade
	deviceRegistrationQueries  *registrationapp.QueryFacade
	persona                    *application.PersonaService
	interestProfile            *application.InterestProfileService
	subjectFollow              *subjectfollowapp.SubjectFollowService
	followedSubjectVisit       *visitapp.VisitService
	followingSubjects          *followingapp.QueryService
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
	relationship *relationshipapp.PersonaRelationshipService,
	greeting *greetingapp.GreetingService,
	settingsCommands *usersettingsapp.UserSettingsCommandFacade,
	settingsQueries *usersettingsapp.UserSettingsQueryFacade,
	auth *application.AuthService,
	credentialQueries *credentialapp.CredentialQueryFacade,
	deviceRegistrationCommands *registrationapp.CommandFacade,
	deviceRegistrationQueries *registrationapp.QueryFacade,
	persona *application.PersonaService,
	interestProfile *application.InterestProfileService,
	subjectFollow *subjectfollowapp.SubjectFollowService,
	followedSubjectVisit *visitapp.VisitService,
	followingSubjects *followingapp.QueryService,
) (*UserHandler, error) {
	if settingsCommands == nil || settingsQueries == nil {
		return nil, errors.New("UserSettings facades are required")
	}
	if credentialQueries == nil {
		return nil, errors.New("CredentialBinding query facade is required")
	}
	if deviceRegistrationCommands == nil || deviceRegistrationQueries == nil {
		return nil, errors.New("DeviceRegistration facades are required")
	}
	handler := &UserHandler{
		profile:                    profile,
		search:                     search,
		relationship:               relationship,
		greeting:                   greeting,
		settingsCommands:           settingsCommands,
		settingsQueries:            settingsQueries,
		auth:                       auth,
		credentialQueries:          credentialQueries,
		deviceRegistrationCommands: deviceRegistrationCommands,
		deviceRegistrationQueries:  deviceRegistrationQueries,
		persona:                    persona,
		interestProfile:            interestProfile,
		subjectFollow:              subjectFollow,
		followedSubjectVisit:       followedSubjectVisit,
		followingSubjects:          followingSubjects,
	}
	return handler, nil
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

	h.registerSubjectFollowRoutes(mux)
	h.registerAccountLifecycleRoutes(mux)
	h.registerDeviceRegistrationRoutes(mux)

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

	mux.HandleFunc("GET /user/settings/notifications", h.handleGetNotificationSettings)
	mux.HandleFunc("PATCH /user/settings/notifications", h.handleUpdateNotificationSettings)
	mux.HandleFunc("GET /user/settings/privacy", h.handleGetPrivacySettings)
	mux.HandleFunc("PATCH /user/settings/privacy", h.handleUpdatePrivacySettings)
	mux.HandleFunc(
		"GET /internal/user/accounts/{userId}/assistant-delivery-policy",
		h.handleResolveAssistantDeliveryPolicy,
	)
	mux.HandleFunc("GET /user/settings/calls", h.handleGetCallSettings)
	mux.HandleFunc("PATCH /user/settings/calls", h.handleUpdateCallSettings)
	mux.HandleFunc("GET /user/settings/appearance", h.handleGetAppearanceSettings)
	mux.HandleFunc("PATCH /user/settings/appearance", h.handleUpdateAppearanceSettings)
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
