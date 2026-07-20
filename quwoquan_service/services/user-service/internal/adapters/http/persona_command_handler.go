package http

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"

	"quwoquan_service/runtime/operation"
	application "quwoquan_service/services/user-service/internal/application"
	"quwoquan_service/services/user-service/internal/generated"
)

// personaCommandMeta 从请求中提取 Persona 聚合命令的业务重放身份。
// Idempotency-Key 是唯一真相源（operation guard 注入的 invocation 与
// 原始 header 同源）；digest 绑定方法、路径与负载。
func personaCommandMeta(r *http.Request, payload []byte) (application.PersonaCommandMeta, error) {
	key := ""
	if invocation, ok := operation.FromContext(r.Context()); ok {
		key = strings.TrimSpace(invocation.IdempotencyKey)
	}
	if key == "" {
		key = strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	}
	if key == "" {
		return application.PersonaCommandMeta{},
			errors.New("Idempotency-Key is required")
	}
	digest := sha256.Sum256(append(
		[]byte(r.Method+" "+r.URL.Path+"\x00"),
		payload...,
	))
	// personas_command_receipts.idempotency_key 全局唯一，且与
	// ProfileUpdateProposal 的 apply 链共用一张表；直接命令加命名空间前缀。
	return application.PersonaCommandMeta{
		IdempotencyKey: "persona-cmd:" + key,
		CommandDigest:  hex.EncodeToString(digest[:]),
	}, nil
}

// decodePersonaCommandBody 读取原始负载并严格解码（拒绝未知字段），
// 返回原始字节供命令摘要使用。空 body 对 path-only 命令合法。
func decodePersonaCommandBody(r *http.Request, target any) ([]byte, error) {
	payload, err := io.ReadAll(io.LimitReader(r.Body, 64*1024))
	if err != nil {
		return nil, err
	}
	if target == nil || len(strings.TrimSpace(string(payload))) == 0 {
		return payload, nil
	}
	decoder := json.NewDecoder(strings.NewReader(string(payload)))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return nil, err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		if err == nil {
			return nil, errors.New("request body contains multiple JSON values")
		}
		return nil, err
	}
	return payload, nil
}

// createPersonaWire 对齐 CreatePersona request_fields；userHandle 由系统分配，
// 显式携带返回 handle_readonly。
type createPersonaWire struct {
	DisplayName    string  `json:"displayName"`
	AvatarURL      string  `json:"avatarUrl"`
	IsolationLevel string  `json:"isolationLevel"`
	PurposeHint    string  `json:"purposeHint"`
	UserHandle     *string `json:"userHandle"`
}

// updatePersonaWire 对齐 UpdatePersona request_fields（PATCH 语义）。
type updatePersonaWire struct {
	DisplayName    *string  `json:"displayName"`
	Phone          *string  `json:"phone"`
	Email          *string  `json:"email"`
	AvatarURL      *string  `json:"avatarUrl"`
	BackgroundURL  *string  `json:"backgroundUrl"`
	IsolationLevel *string  `json:"isolationLevel"`
	PurposeHint    *string  `json:"purposeHint"`
	ApplyScope     string   `json:"applyScope"`
	SyncTargetIDs  []string `json:"syncTargetIds"`
	FieldsMask     []string `json:"fieldsMask"`
	UserHandle     *string  `json:"userHandle"`
}

// profileSyncWire 对齐 ApplyPersonaProfileSync request_fields。
type profileSyncWire struct {
	ApplyScope    string   `json:"applyScope"`
	SyncTargetIDs []string `json:"syncTargetIds"`
	FieldsMask    []string `json:"fieldsMask"`
}

// updateProfileWire 对齐 UpdateUserProfile request_fields（PATCH /user/profile）。
type updateProfileWire struct {
	Nickname          *string  `json:"nickname"`
	DisplayName       *string  `json:"displayName"`
	AvatarAssetID     *string  `json:"avatarAssetId"`
	AvatarURL         *string  `json:"avatarUrl"`
	BackgroundAssetID *string  `json:"backgroundAssetId"`
	BackgroundURL     *string  `json:"backgroundUrl"`
	Bio               *string  `json:"bio"`
	Gender            *string  `json:"gender"`
	BirthDate         *string  `json:"birthDate"`
	RegionTagRef      *string  `json:"regionTagRef"`
	Region            *string  `json:"region"`
	OccupationTagRef  *string  `json:"occupationTagRef"`
	InterestTagRefs   []string `json:"interestTagRefs"`
	IdentityTags      []string `json:"identityTags"`
	ProfileVisibility *string  `json:"profileVisibility"`
	ApplyScope        string   `json:"applyScope"`
	SyncTargetIDs     []string `json:"syncTargetIds"`
	FieldsMask        []string `json:"fieldsMask"`
	UserHandle        *string  `json:"userHandle"`
}

func (w updateProfileWire) command() application.ProfileUpdateCommand {
	return application.ProfileUpdateCommand{
		Nickname:          w.Nickname,
		DisplayName:       w.DisplayName,
		AvatarAssetID:     w.AvatarAssetID,
		AvatarURL:         w.AvatarURL,
		BackgroundAssetID: w.BackgroundAssetID,
		BackgroundURL:     w.BackgroundURL,
		Bio:               w.Bio,
		Gender:            w.Gender,
		BirthDate:         w.BirthDate,
		RegionTagRef:      w.RegionTagRef,
		Region:            w.Region,
		OccupationTagRef:  w.OccupationTagRef,
		InterestTagRefs:   w.InterestTagRefs,
		IdentityTags:      w.IdentityTags,
		ProfileVisibility: w.ProfileVisibility,
		Sync: application.PersonaProfileSyncOptions{
			ApplyScope:    w.ApplyScope,
			SyncTargetIDs: w.SyncTargetIDs,
			FieldsMask:    w.FieldsMask,
		},
	}
}

func writeHandleReadonlyIfRequested(w http.ResponseWriter, r *http.Request, userHandle *string) bool {
	if userHandle == nil {
		return false
	}
	writeHTTPError(w, r, generated.AppErrorFromSubAccountHandleReadonly(
		"userHandle is system assigned",
	))
	return true
}
