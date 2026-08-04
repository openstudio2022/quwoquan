package orchestration

import (
	"errors"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	consentapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
	consentports "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/ports"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	subscriptionports "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/ports"
)

const pageContextTTL = 5 * time.Minute

type AssistantService struct {
	consents             consentports.Reader
	consentQueries       *consentapplication.QueryFacade
	cache                rtredis.Client
	notificationMessages ports.NotificationAppMessageCommandWriter
	subscriptions        subscriptionports.Store
	deliveryPolicies     ports.AssistantDeliveryPolicyReader
	chatGrounding        ports.ChatGroundingClient
	skillCatalog         skillpkg.Loader
	sessions             ports.SessionStore
	runCommands          *runruntime.CommandService
	now                  func() time.Time
}

type AssistantServiceOption func(*AssistantService)

func WithSkillCatalog(catalog skillpkg.Loader) AssistantServiceOption {
	return func(service *AssistantService) { service.skillCatalog = catalog }
}

func WithRunCommandService(
	commands *runruntime.CommandService,
) AssistantServiceOption {
	return func(service *AssistantService) {
		service.runCommands = commands
	}
}

func (s *AssistantService) RunCommandService() *runruntime.CommandService {
	if s == nil {
		return nil
	}
	return s.runCommands
}

func WithSkillSubscriptionStore(store subscriptionports.Store) AssistantServiceOption {
	return func(s *AssistantService) { s.subscriptions = store }
}

func WithAssistantDeliveryPolicyReader(
	reader ports.AssistantDeliveryPolicyReader,
) AssistantServiceOption {
	return func(s *AssistantService) { s.deliveryPolicies = reader }
}

func NewAssistantService(
	consents consentports.Reader,
	cache rtredis.Client,
	opts ...AssistantServiceOption,
) *AssistantService {
	svc := &AssistantService{
		consents: consents,
		cache:    cache,
		now: func() time.Time {
			return time.Now().UTC()
		},
	}
	for _, opt := range opts {
		opt(svc)
	}
	svc.consentQueries = consentapplication.NewQueryFacade(consents)
	return svc
}

func IsNotFound(err error) bool {
	return errors.Is(err, rtredis.ErrKeyNotFound)
}
