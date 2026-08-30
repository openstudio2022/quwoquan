package servicekit

import (
	rthttp "quwoquan_service/runtime/http"
)

// BrowserCORSFromEnv 返回按进程环境派生的浏览器跨域策略，供确实接受浏览器
// 跨域直连的服务显式声明到 BootstrapSpec.CORS。
//
// 它是显式声明位而不是骨架默认：rthttp.WithCORS 对 OPTIONS 无条件短路返回
// 204，那个面不过观测、不过 operation guard、也不过共享准入。把它设成默认
// 会让每个服务凭空多一个未认证可探测面，而绝大多数服务的入站面根本不接受
// 浏览器跨域直连。
func BrowserCORSFromEnv() *rthttp.CORSOptions {
	options := rthttp.CORSOptionsFromEnv()
	return &options
}
