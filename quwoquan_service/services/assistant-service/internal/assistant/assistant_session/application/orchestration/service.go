package orchestration

import (
	"errors"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/skill"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	consentapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
	consentports "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/ports"
	subscriptionports "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/ports"
)

const pageContextTTL = 5 * time.Minute

type AssistantService struct {
	consents                   consentports.Reader
	consentQueries             *consentapplication.QueryFacade
	cache                      rtredis.Client
	notificationMessages       ports.NotificationAppMessageCommandWriter
	subscriptions              subscriptionports.Store
	deliveryPolicies           ports.AssistantDeliveryPolicyReader
	intersectionInbox          ports.IntersectionInboxReader
	learningProjection         ports.LearningProjectionReader
	chatGrounding              ports.ChatGroundingClient
	agentLoop                  *AgentLoop
	skillCatalog               skillpkg.Loader
	sessions                   ports.SessionStore
	preferenceSnapshots        ports.PreferenceSnapshotReader
	runCommands                *runruntime.CommandService
	intersectionReminderPolicy IntersectionReminderPolicy
	now                        func() time.Time
}

type AssistantServiceOption func(*AssistantService)

func WithAgentLoop(loop *AgentLoop) AssistantServiceOption {
	return func(s *AssistantService) { s.agentLoop = loop }
}

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

func WithPreferenceSnapshotReader(reader ports.PreferenceSnapshotReader) AssistantServiceOption {
	return func(s *AssistantService) { s.preferenceSnapshots = reader }
}

func WithSkillSubscriptionStore(store subscriptionports.Store) AssistantServiceOption {
	return func(s *AssistantService) { s.subscriptions = store }
}

func WithAssistantDeliveryPolicyReader(
	reader ports.AssistantDeliveryPolicyReader,
) AssistantServiceOption {
	return func(s *AssistantService) { s.deliveryPolicies = reader }
}

func WithIntersectionInboxReader(reader ports.IntersectionInboxReader) AssistantServiceOption {
	return func(s *AssistantService) { s.intersectionInbox = reader }
}

func WithLearningProjectionReader(
	reader ports.LearningProjectionReader,
) AssistantServiceOption {
	return func(service *AssistantService) {
		service.learningProjection = reader
	}
}

func WithIntersectionReminderPolicy(policy IntersectionReminderPolicy) AssistantServiceOption {
	return func(s *AssistantService) {
		s.intersectionReminderPolicy = normalizeIntersectionReminderPolicy(policy)
	}
}

func NewAssistantService(
	consents consentports.Reader,
	cache rtredis.Client,
	opts ...AssistantServiceOption,
) *AssistantService {
	svc := &AssistantService{
		consents:                   consents,
		cache:                      cache,
		intersectionReminderPolicy: defaultIntersectionReminderPolicy(),
		now: func() time.Time {
			return time.Now().UTC()
		},
	}
	for _, opt := range opts {
		opt(svc)
	}
	svc.consentQueries = consentapplication.NewQueryFacade(consents)
	if svc.agentLoop == nil {
		svc.agentLoop = NewAgentLoop(nil, ReactRuntime{}, svc.now)
	}
	return svc
}

func IsNotFound(err error) bool {
	return errors.Is(err, rtredis.ErrKeyNotFound)
}
