package runtimemedia

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strconv"
	"strings"
	"time"
)

// PrivateDeliveryPathPrefixes 是私有媒体交付路径闭集的唯一真相源
// （DEC-031 网络层边缘守卫）。gamma Caddy 与 local_media_origin 等
// 边缘 adapter 只消费该闭集，不得各自维护前缀字面量。
var PrivateDeliveryPathPrefixes = []string{
	"/media/objects/",
	"/media/processed/",
}

// IsPrivateDeliveryPath 判断（已归一化的）请求路径是否落在私有交付
// 前缀闭集内。归一化（dot-segment、双斜杠）由边缘 adapter 在调用前完成。
func IsPrivateDeliveryPath(escapedPath string) bool {
	for _, prefix := range PrivateDeliveryPathPrefixes {
		if strings.HasPrefix(escapedPath, prefix) {
			return true
		}
	}
	return false
}

// VerifyPrivateDeliverySignature 在字节交付边缘复算私有媒体 URL 的
// HMAC-SHA256 签名并判定绝对到期（DEC-031）：输入为 escaped path、
// sign/t query 原文与签发方同源的 signKey。签名缺失、格式错误、摘要
// 不匹配、t 非法或已到期均返回 false；signKey 缺失时整体 fail closed。
// 复算是纯 CPU 运算、无外部 IO；比较使用常数时间 hmac.Equal。
func VerifyPrivateDeliverySignature(
	escapedPath string,
	signHex string,
	expiresRaw string,
	signKey string,
	now time.Time,
) bool {
	if strings.TrimSpace(signKey) == "" || escapedPath == "" {
		return false
	}
	expires, err := strconv.ParseInt(strings.TrimSpace(expiresRaw), 10, 64)
	if err != nil || expires <= 0 {
		return false
	}
	if now.UTC().Unix() > expires {
		return false
	}
	provided, err := hex.DecodeString(strings.TrimSpace(signHex))
	if err != nil || len(provided) != sha256.Size {
		return false
	}
	mac := hmac.New(sha256.New, []byte(signKey))
	_, _ = fmt.Fprintf(mac, "%s-%d", escapedPath, expires)
	return hmac.Equal(provided, mac.Sum(nil))
}
