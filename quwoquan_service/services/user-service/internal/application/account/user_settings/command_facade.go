package user_settings

import (
	"context"
	"errors"
	"strings"
	"time"

	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/operation"
	settingsmodel "quwoquan_service/services/user-service/internal/domain/account/user_settings/model"
	settingsports "quwoquan_service/services/user-service/internal/domain/account/user_settings/ports"
	"quwoquan_service/services/user-service/internal/generated"
)

const userSettingsCommitAttempts = 3

// UserSettingsCommandFacade 暴露 metadata 声明的四个强类型 command。
type UserSettingsCommandFacade struct {
	store settingsports.AggregateStore
	now   func() time.Time
}

func NewUserSettingsCommandFacade(
	store settingsports.AggregateStore,
) *UserSettingsCommandFacade {
	if store == nil {
		panic("UserSettingsCommandFacade requires an object-specific AggregateStore")
	}
	return &UserSettingsCommandFacade{store: store, now: time.Now}
}

func (facade *UserSettingsCommandFacade) UpdateNotificationSettings(
	ctx context.Context,
	command UpdateNotificationSettingsCommand,
) (CommandResult, error) {
	return facade.commit(ctx, "user.UpdateNotificationSettings", func(
		current settingsmodel.UserSettings,
		now time.Time,
	) (settingsmodel.ChangeSet, error) {
		next := current.Notification
		if command.EnablePush.Present {
			next.EnablePush = command.EnablePush.Value
		}
		if command.EnableMarketing.Present {
			next.EnableMarketing = command.EnableMarketing.Value
		}
		if command.QuietHoursStart.Present {
			next.QuietHoursStart = clonePointer(command.QuietHoursStart.Value)
		}
		if command.QuietHoursEnd.Present {
			next.QuietHoursEnd = clonePointer(command.QuietHoursEnd.Value)
		}
		return current.UpdateNotification(next, now)
	})
}

func (facade *UserSettingsCommandFacade) UpdatePrivacySettings(
	ctx context.Context,
	command UpdatePrivacySettingsCommand,
) (CommandResult, error) {
	return facade.commit(ctx, "user.UpdatePrivacySettings", func(
		current settingsmodel.UserSettings,
		now time.Time,
	) (settingsmodel.ChangeSet, error) {
		next := current.Privacy
		if command.AllowStrangerMsg.Present {
			next.AllowStrangerMsg = command.AllowStrangerMsg.Value
		}
		if command.ProfileVisibility.Present {
			next.ProfileVisibility = command.ProfileVisibility.Value
		}
		if command.BlockedKeywords.Present {
			next.BlockedKeywords = append(
				[]string(nil),
				command.BlockedKeywords.Value...,
			)
		}
		if command.AssistantEnabled.Present {
			next.AssistantEnabled = command.AssistantEnabled.Value
		}
		return current.UpdatePrivacy(next, now)
	})
}

func (facade *UserSettingsCommandFacade) UpdateCallSettings(
	ctx context.Context,
	command UpdateCallSettingsCommand,
) (CommandResult, error) {
	return facade.commit(ctx, "user.UpdateCallSettings", func(
		current settingsmodel.UserSettings,
		now time.Time,
	) (settingsmodel.ChangeSet, error) {
		next := current.Call
		if command.DefaultIncomingCallRingtoneID.Present {
			next.DefaultIncomingCallRingtoneID = clonePointer(
				command.DefaultIncomingCallRingtoneID.Value,
			)
		}
		if command.AllowCallerRingtoneOverride.Present {
			next.AllowCallerRingtoneOverride =
				command.AllowCallerRingtoneOverride.Value
		}
		if command.EnableCallVibration.Present {
			next.EnableCallVibration = command.EnableCallVibration.Value
		}
		if command.EnableGroupCallRing.Present {
			next.EnableGroupCallRing = command.EnableGroupCallRing.Value
		}
		return current.UpdateCall(next, now)
	})
}

func (facade *UserSettingsCommandFacade) UpdateAppearanceSettings(
	ctx context.Context,
	command UpdateAppearanceSettingsCommand,
) (CommandResult, error) {
	if !command.ApplyScope.Valid() {
		return CommandResult{}, generated.AppErrorFromInvalidAppearanceScope(
			"UpdateAppearanceSettings received an unknown applyScope",
		)
	}
	if !command.ThemeMode.Valid() || !command.FontSizePreset.Valid() {
		return CommandResult{}, generated.AppErrorFromInvalidArgument(
			"UpdateAppearanceSettings received an unknown themeMode or fontSizePreset",
		)
	}
	return facade.commit(ctx, "user.UpdateAppearanceSettings", func(
		current settingsmodel.UserSettings,
		now time.Time,
	) (settingsmodel.ChangeSet, error) {
		if command.ApplyScope != settingsmodel.AppearanceApplyScopeAllAccounts {
			// current_sub_account / inherit_owner_default 属于 Persona 聚合。
			// 父级 operation coordinator 负责 Persona 命令；本聚合保持 no-op。
			return current.UpdateAppearance(
				current.Appearance.DefaultThemeMode,
				current.Appearance.DefaultFontSizePreset,
				now,
			)
		}
		return current.UpdateAppearance(
			command.ThemeMode,
			command.FontSizePreset,
			now,
		)
	})
}

func (facade *UserSettingsCommandFacade) commit(
	ctx context.Context,
	operationName string,
	mutate func(
		settingsmodel.UserSettings,
		time.Time,
	) (settingsmodel.ChangeSet, error),
) (result CommandResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, operationName)
	defer func() { rtobs.EndSpan(span, err) }()

	userID, err := trustedAccountID(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	for attempt := 0; attempt < userSettingsCommitAttempts; attempt++ {
		mutationTime := facade.now().UTC()
		current, found, loadErr := facade.store.Load(ctx, userID)
		if loadErr != nil {
			return CommandResult{}, generated.AppErrorFromInternalError(loadErr.Error())
		}
		if !found {
			current, loadErr = settingsmodel.NewDefault(userID, mutationTime)
			if loadErr != nil {
				return CommandResult{}, mapMutationError(loadErr)
			}
		} else if mutationTime.Before(current.UpdatedAt) {
			// 数据库默认时间或跨节点时钟可能略快于当前进程。聚合更新时间
			// 只需单调不回退，CAS/version 才是并发顺序的权威来源。
			mutationTime = current.UpdatedAt
		}
		change, mutationErr := mutate(current, mutationTime)
		if mutationErr != nil {
			return CommandResult{}, mapMutationError(mutationErr)
		}
		if !change.Changed {
			return CommandResult{
				UserID:           current.UserID,
				Version:          current.Version,
				IdempotentReplay: true,
			}, nil
		}
		commitErr := facade.store.Commit(ctx, current.Version, change)
		if commitErr == nil {
			return CommandResult{
				UserID:  change.Aggregate.UserID,
				Version: change.Aggregate.Version,
			}, nil
		}
		if !errors.Is(commitErr, settingsmodel.ErrVersionConflict) ||
			attempt+1 == userSettingsCommitAttempts {
			return CommandResult{}, mapCommitError(commitErr)
		}
	}
	panic("unreachable UserSettings CAS retry")
}

func trustedAccountID(ctx context.Context) (string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Actor.Validate(operation.ActorAccount) != nil {
		return "", generated.AppErrorFromUnauthorized(
			"UserSettings requires a trusted account actor",
		)
	}
	return strings.TrimSpace(current.Actor.AccountID), nil
}

func mapMutationError(err error) error {
	switch {
	case errors.Is(err, settingsmodel.ErrInvalidCallRingtone):
		return generated.AppErrorFromInvalidCallRingtone(err.Error())
	case errors.Is(err, settingsmodel.ErrInvalidAppearanceScope):
		return generated.AppErrorFromInvalidAppearanceScope(err.Error())
	case errors.Is(err, settingsmodel.ErrInvalidArgument):
		return generated.AppErrorFromInvalidArgument(err.Error())
	default:
		return generated.AppErrorFromInternalError(err.Error())
	}
}

func mapCommitError(err error) error {
	switch {
	case errors.Is(err, settingsmodel.ErrVersionConflict):
		return generated.AppErrorFromSettingsVersionConflict(err.Error())
	default:
		return generated.AppErrorFromInternalError(err.Error())
	}
}

func clonePointer[T any](value *T) *T {
	if value == nil {
		return nil
	}
	clone := *value
	return &clone
}
