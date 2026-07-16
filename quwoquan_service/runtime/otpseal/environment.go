package otpseal

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

const (
	ActiveKeyVersionEnv = "OTP_CODE_REF_ACTIVE_KEY_VERSION"
	KeysJSONEnv         = "OTP_CODE_REF_KEYS_JSON"
)

// LoadFromEnvironment 从部署密钥注入中装配 OTP codeRef 密封器。
// keys JSON 的形状为 {"k1":"<base64-encoded-32-byte-key>"}；任何缺失或
// 非法配置都会 fail-closed，且错误不包含密钥值。
func LoadFromEnvironment() (*Sealer, error) {
	activeVersion := strings.TrimSpace(os.Getenv(ActiveKeyVersionEnv))
	rawKeys := strings.TrimSpace(os.Getenv(KeysJSONEnv))
	if activeVersion == "" || rawKeys == "" {
		return nil, fmt.Errorf("%s and %s are required", ActiveKeyVersionEnv, KeysJSONEnv)
	}
	encodedKeys := map[string]string{}
	if err := json.Unmarshal([]byte(rawKeys), &encodedKeys); err != nil {
		return nil, fmt.Errorf("%s must be a JSON object of base64 keys", KeysJSONEnv)
	}
	return NewFromBase64(activeVersion, encodedKeys)
}
