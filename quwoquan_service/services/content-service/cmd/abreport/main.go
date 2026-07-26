// abreport（N1-3）：在线 AB 实验报告 CLI。
//
// 从 rec_learning_events 聚合窗口观测，产出 BuildABExperimentReport 的固定
// 模板（产品/算法/数据/运营晋升评审用），并同步执行准入记账（与常驻
// ABAdmissionRunner 同一代码路径，保证周报与在线 SLI 同源）。
//
// 用法：
//
//	go run ./services/content-service/cmd/abreport \
//	  --mongo-uri mongodb://127.0.0.1:27017 --db quwoquan_content \
//	  [--experiment rec_model_vs_rule] [--policy services/content-service/resources/policies/content/post/recommendation_policy.yaml]
//
// 输出：每个实验一份 JSON 报告（stdout），CI 周报把输出归档为 artifact。
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"strings"
	"time"

	rtmongo "quwoquan_service/internal/platform/mongodb"
	rtrec "quwoquan_service/runtime/recommendation"
	rtrecpolicy "quwoquan_service/runtime/recpolicy"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

func main() {
	mongoURI := flag.String("mongo-uri", envOr("MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true"), "MongoDB URI")
	dbName := flag.String("db", envOr("DB", "quwoquan_content"), "MongoDB database")
	experimentID := flag.String("experiment", "", "只报告指定实验（默认全部 enabled 实验）")
	policyPath := flag.String("policy", os.Getenv("QWQ_REC_POLICY_PATH"), "policy yaml 路径（默认 codegen baseline）")
	flag.Parse()

	logger := slog.New(slog.NewTextHandler(os.Stderr, nil))
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	policyStore := rtrecpolicy.NewStoreFromBaseline()
	if strings.TrimSpace(*policyPath) != "" {
		if _, err := policyStore.ApplyFile(*policyPath); err != nil {
			logger.Error("apply policy file failed", slog.String("path", *policyPath), slog.String("err", err.Error()))
			os.Exit(1)
		}
	}

	client := rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: *mongoURI}, "abreport")
	defer func() { _ = client.Disconnect(context.Background()) }()

	runner := recinfra.NewABAdmissionRunner(client.Database(*dbName), policyStore, logger)
	policy := policyStore.Current()

	reported := 0
	for _, exp := range policy.Experiments {
		if !exp.Enabled || len(exp.Buckets) == 0 {
			continue
		}
		if *experimentID != "" && exp.ID != *experimentID {
			continue
		}
		obs, err := runner.ObserveExperiment(ctx, policy, exp)
		if err != nil {
			logger.Error("observe experiment failed", slog.String("experiment", exp.ID), slog.String("err", err.Error()))
			os.Exit(1)
		}
		report := rtrec.BuildABExperimentReport(obs, policy.ABAdmission, rtrec.ABGuardrailThresholds{})
		payload, err := json.MarshalIndent(report, "", "  ")
		if err != nil {
			logger.Error("marshal report failed", slog.String("experiment", exp.ID), slog.String("err", err.Error()))
			os.Exit(1)
		}
		fmt.Println(string(payload))
		reported++
	}
	if reported == 0 {
		logger.Warn("no enabled experiment matched", slog.String("experiment", *experimentID))
	}
}

func envOr(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}
