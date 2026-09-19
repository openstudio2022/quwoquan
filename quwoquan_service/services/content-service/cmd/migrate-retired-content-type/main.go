// Command migrate-retired-content-type 记录显式退役 micro 的迁移阻断回执。
// canonical release/lifecycle 投影恢复协议确定前，不连接数据库、不改写 Post，
// 不恢复已退役的发现流写轨；未来未知 ContentType 也不属于分类输入。
package main

import (
	"context"
	"log"
	"os"

	releaseimport "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func main() {
	if err := releaseimport.RunRetiredContentTypeMigration(context.Background(), os.Args[1:]); err != nil {
		log.Fatal(err)
	}
}
