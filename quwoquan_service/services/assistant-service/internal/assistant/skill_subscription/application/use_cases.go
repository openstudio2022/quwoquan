package application

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtid "quwoquan_service/runtime/id"
	rtobs "quwoquan_service/runtime/observability"
	subscriptionerrors "quwoquan_service/services/assistant-service/generated/assistant/skill_subscription"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/ports"
)

const (
	defaultMaxPerDay      = 1
	defaultCooldownMinute = 60
	maxDeliveriesPerDay   = 24
	maxCooldownMinutes    = 7 * 24 * 60
)

type DestinationMembershipReader interface {
	ResolveAssistantDeliveryMembership(
		context.Context,
		string,
		string,
		string,
	) (bool, error)
}

type CronTicker interface {
	TickSkillSubscriptionCron(
		context.Context,
		model.SkillSubscriptionCronTickInput,
	) (model.SkillSubscriptionCronTickResult, error)
}

type UseCases struct {
	store       ports.Store
	memberships DestinationMembershipReader
	ticker      CronTicker
	now         func() time.Time
}

func NewUseCases(
	store ports.Store,
	memberships DestinationMembershipReader,
	ticker CronTicker,
	now func() time.Time,
) *UseCases {
	if store == nil {
		panic("skill subscription store is required")
	}
	if now == nil {
		now = time.Now
	}
	return &UseCases{
		store:       store,
		memberships: memberships,
		ticker:      ticker,
		now:         now,
	}
}

func (s *UseCases) Create(
	ctx context.Context,
	userID string,
	input model.CreateSkillSubscriptionInput,
) (_ model.SkillSubscription, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"assistant.CreateSkillSubscription",
		attribute.String("user.id", userID),
		attribute.String("skill.id", input.SkillID),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	userID = strings.TrimSpace(userID)
	commandID := strings.TrimSpace(input.ClientRequestID)
	if userID == "" || commandID == "" {
		return model.SkillSubscription{}, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(
			"trusted userId and clientRequestId are required",
		)
	}
	normalized, err := s.normalizeInput(userID, input)
	if err != nil {
		return model.SkillSubscription{}, err
	}
	digest, err := commandDigest("create", createDigestPayload(normalized))
	if err != nil {
		return model.SkillSubscription{}, storageUnavailable("create command digest", err)
	}
	if replayed, found, replayErr := s.store.GetSkillSubscriptionCommandResult(
		ctx, userID, commandID, "create", digest,
	); replayErr != nil {
		return model.SkillSubscription{}, mapStoreError(replayErr)
	} else if found {
		return replayed, nil
	}
	if err := s.requireDestinationAccess(ctx, normalized); err != nil {
		return model.SkillSubscription{}, err
	}
	created, _, err := s.store.CreateSkillSubscription(
		ctx, commandID, digest, normalized,
	)
	if err != nil {
		return model.SkillSubscription{}, mapStoreError(err)
	}
	return created, nil
}

func (s *UseCases) List(
	ctx context.Context,
	userID, status string,
	limit int,
) (model.SkillSubscriptionListView, error) {
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return model.SkillSubscriptionListView{}, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(
			"trusted userId is required",
		)
	}
	status = strings.TrimSpace(status)
	if status != "" {
		parsed, err := model.ParseStatus(status)
		if err != nil {
			return model.SkillSubscriptionListView{}, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(err.Error())
		}
		status = string(parsed)
	}
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	items, err := s.store.ListSkillSubscriptions(ctx, userID, status, limit)
	if err != nil {
		return model.SkillSubscriptionListView{}, mapStoreError(err)
	}
	return model.SkillSubscriptionListView{Items: items}, nil
}

func (s *UseCases) Get(
	ctx context.Context,
	userID, subscriptionID string,
) (model.SkillSubscription, error) {
	item, err := s.store.GetSkillSubscription(
		ctx,
		strings.TrimSpace(userID),
		strings.TrimSpace(subscriptionID),
	)
	if err != nil {
		return model.SkillSubscription{}, mapStoreError(err)
	}
	return item, nil
}

func (s *UseCases) UpdateStatus(
	ctx context.Context,
	userID, subscriptionID string,
	input model.UpdateSkillSubscriptionStatusInput,
) (_ model.SkillSubscription, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"assistant.UpdateSkillSubscriptionStatus",
		attribute.String("subscription.id", subscriptionID),
		attribute.String("subscription.status", input.Status),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	userID = strings.TrimSpace(userID)
	subscriptionID = strings.TrimSpace(subscriptionID)
	commandID := strings.TrimSpace(input.ClientRequestID)
	status, err := model.ParseStatus(input.Status)
	if err != nil || userID == "" || subscriptionID == "" || commandID == "" {
		return model.SkillSubscription{}, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(
			"trusted userId, subscriptionId, status and clientRequestId are required",
		)
	}
	digest, err := commandDigest("update_status", struct {
		OwnerID        string `json:"ownerId"`
		SubscriptionID string `json:"subscriptionId"`
		Status         string `json:"status"`
	}{OwnerID: userID, SubscriptionID: subscriptionID, Status: string(status)})
	if err != nil {
		return model.SkillSubscription{}, storageUnavailable("status command digest", err)
	}
	if replayed, found, replayErr := s.store.GetSkillSubscriptionCommandResult(
		ctx, userID, commandID, "update_status", digest,
	); replayErr != nil {
		return model.SkillSubscription{}, mapStoreError(replayErr)
	} else if found {
		return replayed, nil
	}
	current, err := s.store.GetSkillSubscription(ctx, userID, subscriptionID)
	if err != nil {
		return model.SkillSubscription{}, mapStoreError(err)
	}
	if err := model.ValidateTransition(current.Status, string(status)); err != nil {
		return model.SkillSubscription{}, subscriptionerrors.AppErrorFromSubscriptionInvalidTransition(err.Error())
	}
	now := s.now().UTC().Truncate(time.Millisecond)
	var nextAttemptAt *time.Time
	if status == model.SkillSubscriptionStatusActive && current.Status != string(status) {
		next, ok := NextCronTrigger(
			current.Trigger.Cron,
			current.Trigger.Timezone,
			now,
		)
		if !ok {
			return model.SkillSubscription{}, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(
				"cron has no trigger in the supported scheduling window",
			)
		}
		nextAttemptAt = &next
	}
	updated, _, err := s.store.UpdateSkillSubscriptionStatus(
		ctx,
		userID,
		subscriptionID,
		string(status),
		nextAttemptAt,
		now,
		commandID,
		digest,
	)
	if err != nil {
		return model.SkillSubscription{}, mapStoreError(err)
	}
	return updated, nil
}

func (s *UseCases) Tick(
	ctx context.Context,
	input model.SkillSubscriptionCronTickInput,
) (model.SkillSubscriptionCronTickResult, error) {
	if s.ticker == nil {
		return model.SkillSubscriptionCronTickResult{}, subscriptionerrors.AppErrorFromSubscriptionDeliveryFailed(
			"skill subscription scheduler application is not configured",
		)
	}
	return s.ticker.TickSkillSubscriptionCron(ctx, input)
}

func (s *UseCases) normalizeInput(
	userID string,
	input model.CreateSkillSubscriptionInput,
) (model.SkillSubscription, error) {
	skillID := strings.TrimSpace(input.SkillID)
	domainID := strings.TrimSpace(input.DomainID)
	if skillID == "" || domainID == "" {
		return model.SkillSubscription{}, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(
			"skillId and domainId are required",
		)
	}
	trigger := input.Trigger
	trigger.Type = strings.TrimSpace(trigger.Type)
	if trigger.Type == "" {
		trigger.Type = "cron"
	}
	trigger.Cron = strings.TrimSpace(trigger.Cron)
	trigger.Timezone = strings.TrimSpace(trigger.Timezone)
	if trigger.Type != "cron" ||
		!CronSupported(trigger.Cron) ||
		!TimezoneSupported(trigger.Timezone) {
		return model.SkillSubscription{}, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(
			"only a valid canonical cron trigger with an explicit IANA timezone is supported",
		)
	}
	destination := input.Destination
	destination.DestinationType = model.SkillSubscriptionDestinationType(
		strings.TrimSpace(string(destination.DestinationType)),
	)
	if destination.DestinationType == "" {
		destination.DestinationType = model.SkillSubscriptionDestinationUser
	}
	destination.DestinationID = strings.TrimSpace(destination.DestinationID)
	if destination.DestinationType == model.SkillSubscriptionDestinationUser && destination.DestinationID == "" {
		destination.DestinationID = userID
	}
	if destination.DestinationID == "" ||
		(destination.DestinationType == model.SkillSubscriptionDestinationUser && destination.DestinationID != userID) {
		return model.SkillSubscription{}, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(
			"destination must belong to the subscription owner",
		)
	}
	destination.QuietHoursPolicy = strings.TrimSpace(destination.QuietHoursPolicy)
	if destination.QuietHoursPolicy == "" {
		destination.QuietHoursPolicy = "inherit_user_setting"
	}
	if destination.QuietHoursPolicy != "inherit_user_setting" {
		return model.SkillSubscription{}, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(
			"quietHoursPolicy must be inherit_user_setting",
		)
	}
	if destination.MaxPerDay == 0 {
		destination.MaxPerDay = defaultMaxPerDay
	}
	if destination.MaxPerDay < 1 || destination.MaxPerDay > maxDeliveriesPerDay {
		return model.SkillSubscription{}, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(
			"maxPerDay is outside the supported range",
		)
	}
	if destination.CooldownMinutes == 0 {
		destination.CooldownMinutes = defaultCooldownMinute
	}
	if destination.CooldownMinutes < 1 || destination.CooldownMinutes > maxCooldownMinutes {
		return model.SkillSubscription{}, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(
			"cooldownMinutes is outside the supported range",
		)
	}
	switch destination.DestinationType {
	case model.SkillSubscriptionDestinationUser,
		model.SkillSubscriptionDestinationChatConversation:
	default:
		return model.SkillSubscription{}, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(
			"unsupported destination type",
		)
	}
	createdByPersonaID := strings.TrimSpace(input.CreatedByPersonaID)
	if destination.DestinationType == model.SkillSubscriptionDestinationChatConversation && createdByPersonaID == "" {
		return model.SkillSubscription{}, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(
			"chat destination requires creator persona",
		)
	}
	searchPlan := input.SearchQueryPlan
	searchPlan.RawText = strings.TrimSpace(searchPlan.RawText)
	searchPlan.Queries = CompactStrings(searchPlan.Queries)
	if len(searchPlan.Queries) == 0 && searchPlan.RawText != "" {
		searchPlan.Queries = []string{searchPlan.RawText}
	}
	subscriptionID, err := rtid.Generate(rtid.PrefixSkillSubscription)
	if err != nil {
		return model.SkillSubscription{}, storageUnavailable("generate subscription identity", err)
	}
	now := s.now().UTC().Truncate(time.Millisecond)
	nextAttemptAt, ok := NextCronTrigger(trigger.Cron, trigger.Timezone, now)
	if !ok {
		return model.SkillSubscription{}, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(
			"cron has no trigger in the supported scheduling window",
		)
	}
	return model.SkillSubscription{
		SubscriptionID:     subscriptionID,
		Version:            1,
		Owner:              model.SkillSubscriptionOwner{OwnerType: "user", OwnerID: userID},
		CreatedByUserID:    userID,
		CreatedByPersonaID: createdByPersonaID,
		SkillID:            skillID,
		DomainID:           domainID,
		TagRefs:            CompactStrings(input.TagRefs),
		Status:             model.SkillSubscriptionStatusActive,
		SearchQueryPlan:    searchPlan,
		Trigger:            trigger,
		Destination:        destination,
		DeliveryState: model.SkillSubscriptionDeliveryState{
			NextAttemptAt: &nextAttemptAt,
		},
		CreatedAt: now,
		UpdatedAt: now,
	}, nil
}

func (s *UseCases) requireDestinationAccess(
	ctx context.Context,
	subscription model.SkillSubscription,
) error {
	if subscription.Destination.DestinationType == model.SkillSubscriptionDestinationUser {
		return nil
	}
	if s.memberships == nil {
		return subscriptionerrors.AppErrorFromSubscriptionDestinationValidationUnavailable(
			"chat membership reader is not configured",
		)
	}
	current, err := s.memberships.ResolveAssistantDeliveryMembership(
		ctx,
		subscription.Destination.DestinationID,
		subscription.CreatedByPersonaID,
		"",
	)
	if err != nil {
		return subscriptionerrors.AppErrorFromSubscriptionDestinationValidationUnavailable(err.Error())
	}
	if !current {
		return subscriptionerrors.AppErrorFromSubscriptionDestinationForbidden(
			"subscription creator or assistant is not a current chat member",
		)
	}
	return nil
}

func createDigestPayload(subscription model.SkillSubscription) any {
	return struct {
		OwnerID            string                                 `json:"ownerId"`
		CreatedByPersonaID string                                 `json:"createdByPersonaId"`
		SkillID            string                                 `json:"skillId"`
		DomainID           string                                 `json:"domainId"`
		TagRefs            []string                               `json:"tagRefs"`
		SearchQueryPlan    model.SkillSubscriptionSearchQueryPlan `json:"searchQueryPlan"`
		Trigger            model.SkillSubscriptionTrigger         `json:"trigger"`
		Destination        model.SkillSubscriptionDestination     `json:"destination"`
	}{
		OwnerID:            subscription.Owner.OwnerID,
		CreatedByPersonaID: subscription.CreatedByPersonaID,
		SkillID:            subscription.SkillID,
		DomainID:           subscription.DomainID,
		TagRefs:            subscription.TagRefs,
		SearchQueryPlan:    subscription.SearchQueryPlan,
		Trigger:            subscription.Trigger,
		Destination:        subscription.Destination,
	}
}

func commandDigest(commandKind string, payload any) (string, error) {
	encoded, err := json.Marshal(struct {
		CommandKind string `json:"commandKind"`
		Payload     any    `json:"payload"`
	}{CommandKind: strings.TrimSpace(commandKind), Payload: payload})
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("sha256:%x", sha256.Sum256(encoded)), nil
}

func mapStoreError(err error) error {
	switch {
	case errors.Is(err, model.ErrIdempotencyConflict):
		return subscriptionerrors.AppErrorFromSubscriptionIdempotencyConflict(err.Error())
	case errors.Is(err, model.ErrVersionConflict),
		errors.Is(err, model.ErrInvalidTransition):
		return subscriptionerrors.AppErrorFromSubscriptionInvalidTransition(err.Error())
	case errors.Is(err, model.ErrNotFound):
		return subscriptionerrors.AppErrorFromSubscriptionNotFound(err.Error())
	default:
		return err
	}
}

func storageUnavailable(operation string, err error) error {
	return rterr.NewUnavailable(
		rterr.ModuleAssistant,
		"订阅存储暂不可用",
		strings.TrimSpace(operation)+": "+err.Error(),
	)
}

func CompactStrings(items []string) []string {
	out := make([]string, 0, len(items))
	seen := map[string]bool{}
	for _, item := range items {
		item = strings.TrimSpace(item)
		if item == "" || seen[item] {
			continue
		}
		seen[item] = true
		out = append(out, item)
	}
	return out
}

func CronSupported(raw string) bool {
	parts := strings.Fields(raw)
	return len(parts) == 5 &&
		cronFieldSupported(parts[0], 0, 59) &&
		cronFieldSupported(parts[1], 0, 23) &&
		parts[2] == "*" && parts[3] == "*" && parts[4] == "*"
}

func TimezoneSupported(raw string) bool {
	raw = strings.TrimSpace(raw)
	if raw == "UTC" {
		return true
	}
	if !strings.Contains(raw, "/") {
		return false
	}
	_, err := time.LoadLocation(raw)
	return err == nil
}

func CronMatchesMinute(raw, timezone string, now time.Time) bool {
	location, err := time.LoadLocation(strings.TrimSpace(timezone))
	if err != nil || !TimezoneSupported(timezone) {
		return false
	}
	return cronMatchesMinuteAtLocation(raw, now.In(location))
}

func cronMatchesMinuteAtLocation(raw string, local time.Time) bool {
	parts := strings.Fields(raw)
	return len(parts) == 5 &&
		cronPartMatches(parts[0], local.Minute(), 0, 59) &&
		cronPartMatches(parts[1], local.Hour(), 0, 23) &&
		parts[2] == "*" && parts[3] == "*" && parts[4] == "*"
}

func NextCronTrigger(raw, timezone string, after time.Time) (time.Time, bool) {
	if !CronSupported(raw) || !TimezoneSupported(timezone) {
		return time.Time{}, false
	}
	location, err := time.LoadLocation(strings.TrimSpace(timezone))
	if err != nil {
		return time.Time{}, false
	}
	candidate := after.UTC().Truncate(time.Minute).Add(time.Minute)
	for minute := 0; minute <= 24*60; minute++ {
		if cronMatchesMinuteAtLocation(raw, candidate.In(location)) {
			return candidate, true
		}
		candidate = candidate.Add(time.Minute)
	}
	return time.Time{}, false
}

func cronFieldSupported(raw string, min, max int) bool {
	if raw == "*" {
		return true
	}
	value, err := strconv.Atoi(raw)
	return err == nil && value >= min && value <= max
}

func cronPartMatches(raw string, value, min, max int) bool {
	if raw == "*" {
		return true
	}
	parsed, err := strconv.Atoi(raw)
	return err == nil && parsed >= min && parsed <= max && parsed == value
}
