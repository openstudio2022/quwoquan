package credential_binding

import bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"

// BindCredentialCommand 只接受验证完成后得到的不可逆 CredentialKey。
// Provider token、OTP 与其他明文认证材料不得进入本对象。
type BindCredentialCommand struct {
	CredentialType bindingmodel.CredentialType
	CredentialKey  string
	DisplayLabel   string
}

type UnbindCredentialCommand struct {
	CredentialType bindingmodel.CredentialType
}

// CommandResult 与 metadata CredentialBindingCommandResult 完全对齐。
type CommandResult struct {
	OwnerID          string                      `json:"-"`
	CredentialType   bindingmodel.CredentialType `json:"credentialType"`
	IsActive         bool                        `json:"isActive"`
	Version          int64                       `json:"version"`
	IdempotentReplay bool                        `json:"idempotentReplay"`
	DisplayLabel     string                      `json:"displayLabel,omitempty"`
}
