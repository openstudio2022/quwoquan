package http

import (
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	httpcodec "quwoquan_service/runtime/httpcodec"
	settingsgenerated "quwoquan_service/services/user-service/generated/account/user_settings"
	usersettingsapp "quwoquan_service/services/user-service/internal/account/user_settings/application"
	settingsmodel "quwoquan_service/services/user-service/internal/account/user_settings/domain/model"
)

type Handler struct {
	commands *usersettingsapp.UserSettingsCommandFacade
	queries  *usersettingsapp.UserSettingsQueryFacade
}

func NewHandler(
	commands *usersettingsapp.UserSettingsCommandFacade,
	queries *usersettingsapp.UserSettingsQueryFacade,
) *Handler {
	if commands == nil || queries == nil {
		panic("UserSettings HTTP handler requires command and query facades")
	}
	return &Handler{commands: commands, queries: queries}
}

func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /user/settings/notifications", h.handleGetNotificationSettings)
	mux.HandleFunc("PATCH /user/settings/notifications", h.handleUpdateNotificationSettings)
	mux.HandleFunc("GET /user/settings/privacy", h.handleGetPrivacySettings)
	mux.HandleFunc("PATCH /user/settings/privacy", h.handleUpdatePrivacySettings)
	mux.HandleFunc("GET /internal/user/accounts/{userId}/assistant-delivery-policy", h.handleResolveAssistantDeliveryPolicy)
	mux.HandleFunc("GET /user/settings/calls", h.handleGetCallSettings)
	mux.HandleFunc("PATCH /user/settings/calls", h.handleUpdateCallSettings)
	mux.HandleFunc("GET /user/settings/appearance", h.handleGetAppearanceSettings)
	mux.HandleFunc("PATCH /user/settings/appearance", h.handleUpdateAppearanceSettings)
}

// UserSettings 端点全部走对象专属 facade：
// 身份由 facade 从 operation.Context 取（guard 验签后注入），
// 命令响应统一 UserSettingsCommandResult，读响应为 typed slice。

type notificationSettingsWire struct {
	EnablePush      *bool   `json:"enablePush"`
	EnableMarketing *bool   `json:"enableMarketing"`
	QuietHoursStart *string `json:"quietHoursStart"`
	QuietHoursEnd   *string `json:"quietHoursEnd"`
}

type privacySettingsWire struct {
	AllowStrangerMsg  *bool    `json:"allowStrangerMsg"`
	ProfileVisibility *string  `json:"profileVisibility"`
	BlockedKeywords   []string `json:"blockedKeywords"`
	AssistantEnabled  *bool    `json:"assistantEnabled"`
}

type callSettingsWire struct {
	DefaultIncomingCallRingtoneID *string `json:"defaultIncomingCallRingtoneId"`
	AllowCallerRingtoneOverride   *bool   `json:"allowCallerRingtoneOverride"`
	EnableCallVibration           *bool   `json:"enableCallVibration"`
	EnableGroupCallRing           *bool   `json:"enableGroupCallRing"`
}

type appearanceSettingsWire struct {
	ThemeMode      string `json:"themeMode"`
	FontSizePreset string `json:"fontSizePreset"`
	ApplyScope     string `json:"applyScope"`
}

func (h *Handler) handleGetNotificationSettings(
	w http.ResponseWriter,
	r *http.Request,
) {
	slice, err := h.queries.GetNotificationSettings(r.Context())
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, slice)
}

func (h *Handler) handleGetPrivacySettings(
	w http.ResponseWriter,
	r *http.Request,
) {
	slice, err := h.queries.GetPrivacySettings(r.Context())
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, slice)
}

func (h *Handler) handleResolveAssistantDeliveryPolicy(
	w http.ResponseWriter,
	r *http.Request,
) {
	slice, err := h.queries.ResolveAssistantDeliveryPolicy(
		r.Context(),
		r.PathValue("userId"),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, slice)
}

func (h *Handler) handleGetCallSettings(
	w http.ResponseWriter,
	r *http.Request,
) {
	slice, err := h.queries.GetCallSettings(r.Context())
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, slice)
}

func (h *Handler) handleGetAppearanceSettings(
	w http.ResponseWriter,
	r *http.Request,
) {
	slice, err := h.queries.GetAppearanceSettings(r.Context())
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, slice)
}

func (h *Handler) handleUpdateNotificationSettings(
	w http.ResponseWriter,
	r *http.Request,
) {
	var wire notificationSettingsWire
	if err := decodeStrictJSON(r, &wire); err != nil {
		writeInvalidArg(w, r, "invalid notification settings: "+err.Error())
		return
	}
	command := usersettingsapp.UpdateNotificationSettingsCommand{}
	if wire.EnablePush != nil {
		command.EnablePush = usersettingsapp.Set(*wire.EnablePush)
	}
	if wire.EnableMarketing != nil {
		command.EnableMarketing = usersettingsapp.Set(*wire.EnableMarketing)
	}
	quietStart, err := timeOfDayPatch(wire.QuietHoursStart)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	command.QuietHoursStart = quietStart
	quietEnd, err := timeOfDayPatch(wire.QuietHoursEnd)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	command.QuietHoursEnd = quietEnd
	result, err := h.commands.UpdateNotificationSettings(
		r.Context(),
		command,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) handleUpdatePrivacySettings(
	w http.ResponseWriter,
	r *http.Request,
) {
	var wire privacySettingsWire
	if err := decodeStrictJSON(r, &wire); err != nil {
		writeInvalidArg(w, r, "invalid privacy settings: "+err.Error())
		return
	}
	command := usersettingsapp.UpdatePrivacySettingsCommand{}
	if wire.AllowStrangerMsg != nil {
		command.AllowStrangerMsg = usersettingsapp.Set(*wire.AllowStrangerMsg)
	}
	if wire.ProfileVisibility != nil {
		command.ProfileVisibility = usersettingsapp.Set(
			settingsmodel.ProfileVisibility(
				strings.TrimSpace(*wire.ProfileVisibility),
			),
		)
	}
	if wire.BlockedKeywords != nil {
		command.BlockedKeywords = usersettingsapp.Set(wire.BlockedKeywords)
	}
	if wire.AssistantEnabled != nil {
		command.AssistantEnabled = usersettingsapp.Set(*wire.AssistantEnabled)
	}
	result, err := h.commands.UpdatePrivacySettings(
		r.Context(),
		command,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) handleUpdateCallSettings(
	w http.ResponseWriter,
	r *http.Request,
) {
	var wire callSettingsWire
	if err := decodeStrictJSON(r, &wire); err != nil {
		writeInvalidArg(w, r, "invalid call settings: "+err.Error())
		return
	}
	command := usersettingsapp.UpdateCallSettingsCommand{}
	if wire.DefaultIncomingCallRingtoneID != nil {
		raw := strings.TrimSpace(*wire.DefaultIncomingCallRingtoneID)
		if raw == "" {
			command.DefaultIncomingCallRingtoneID = usersettingsapp.Set(
				(*settingsmodel.OfficialRingtoneID)(nil),
			)
		} else {
			parsed, err := settingsmodel.ParseOfficialRingtoneID(raw)
			if err != nil {
				writeHTTPError(w, r, settingsgenerated.AppErrorFromInvalidCallRingtone(
					"defaultIncomingCallRingtoneId must use the official namespace",
				))
				return
			}
			command.DefaultIncomingCallRingtoneID = usersettingsapp.Set(&parsed)
		}
	}
	if wire.AllowCallerRingtoneOverride != nil {
		command.AllowCallerRingtoneOverride = usersettingsapp.Set(
			*wire.AllowCallerRingtoneOverride,
		)
	}
	if wire.EnableCallVibration != nil {
		command.EnableCallVibration = usersettingsapp.Set(
			*wire.EnableCallVibration,
		)
	}
	if wire.EnableGroupCallRing != nil {
		command.EnableGroupCallRing = usersettingsapp.Set(
			*wire.EnableGroupCallRing,
		)
	}
	result, err := h.commands.UpdateCallSettings(r.Context(), command)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) handleUpdateAppearanceSettings(
	w http.ResponseWriter,
	r *http.Request,
) {
	var wire appearanceSettingsWire
	if err := decodeStrictJSON(r, &wire); err != nil {
		writeInvalidArg(w, r, "invalid appearance settings: "+err.Error())
		return
	}
	scope := settingsmodel.AppearanceApplyScope(
		strings.TrimSpace(wire.ApplyScope),
	)
	if scope == "" {
		scope = settingsmodel.AppearanceApplyScopeAllAccounts
	}
	if scope != settingsmodel.AppearanceApplyScopeAllAccounts {
		// UserSettings 只持有 owner 默认；persona override 走 Persona 命令。
		writeHTTPError(w, r, settingsgenerated.AppErrorFromInvalidAppearanceScope(
			"UserSettings owns only all_accounts defaults; persona overrides use Persona commands",
		))
		return
	}
	if _, err := h.commands.UpdateAppearanceSettings(
		r.Context(),
		usersettingsapp.UpdateAppearanceSettingsCommand{
			ThemeMode:      settingsmodel.ThemeMode(strings.TrimSpace(wire.ThemeMode)),
			FontSizePreset: settingsmodel.FontSizePreset(strings.TrimSpace(wire.FontSizePreset)),
			ApplyScope:     scope,
		},
	); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	slice, err := h.queries.GetAppearanceSettings(r.Context())
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, slice)
}

// timeOfDayPatch 把 wire 值转为 Patch：nil=未提供；""=清除；"HH:mm"=设置。
func timeOfDayPatch(
	raw *string,
) (usersettingsapp.Patch[*settingsmodel.TimeOfDay], error) {
	if raw == nil {
		return usersettingsapp.Patch[*settingsmodel.TimeOfDay]{}, nil
	}
	trimmed := strings.TrimSpace(*raw)
	if trimmed == "" {
		return usersettingsapp.Set((*settingsmodel.TimeOfDay)(nil)), nil
	}
	parsed, err := settingsmodel.ParseTimeOfDay(trimmed)
	if err != nil {
		return usersettingsapp.Patch[*settingsmodel.TimeOfDay]{},
			invalidArgument(
				"quiet hours must use HH:mm",
			)
	}
	return usersettingsapp.Set(&parsed), nil
}

func invalidArgument(debug string) error {
	return rterr.NewInvalidArgument(rterr.ModuleUser, "参数无效", debug)
}

func decodeStrictJSON(r *http.Request, target any) error {
	return httpcodec.DecodeStrictJSON(r, target)
}

func writeInvalidArg(w http.ResponseWriter, r *http.Request, debug string) {
	writeHTTPError(w, r, invalidArgument(debug))
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	httpcodec.WriteJSON(w, status, payload, "user_settings")
}
