// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/spec.md#sit-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-002
package local_contract

import (
	"encoding/json"
	"fmt"
	"reflect"
	"sort"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/simulator"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/skill"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/assets"
)

const replayCasesPerSkill = 10

func TestAgentReplayEvaluationGate(t *testing.T) {
	catalog, err := orchestration.LoadAssistantDomainSkillCatalog()
	if err != nil {
		t.Fatalf("LoadAssistantDomainSkillCatalog(): %v", err)
	}
	assertReplayCorpusCoversCatalog(t, catalog)
	promptAssets, err := assets.NewDefaultPromptAssetLoader()
	if err != nil {
		t.Fatalf("NewDefaultPromptAssetLoader(): %v", err)
	}
	runner := simulator.Runner{
		Now: func() time.Time {
			return time.Date(2026, 7, 28, 10, 0, 0, 0, time.UTC)
		},
		PromptAssets: promptAssets,
	}
	seenCaseIDs := map[string]bool{}
	for _, manifest := range catalog {
		cases := replayCasesForManifest(t, manifest)
		if len(cases) < replayCasesPerSkill {
			t.Fatalf(
				"skill %q replay cases=%d, want at least %d",
				manifest.SkillID,
				len(cases),
				replayCasesPerSkill,
			)
		}
		for _, replay := range cases {
			replay := replay
			if seenCaseIDs[replay.ReplayCaseID] {
				t.Fatalf("duplicate replayCaseId %q", replay.ReplayCaseID)
			}
			seenCaseIDs[replay.ReplayCaseID] = true
			t.Run(replay.ReplayCaseID, func(t *testing.T) {
				wireCase := roundTripReplayCase(t, replay)
				transcript, err := runner.Run(t.Context(), wireCase)
				if err != nil {
					t.Fatalf("Run(): %v", err)
				}
				assertReplayTrajectory(t, manifest, wireCase, transcript)
			})
		}
	}
}

func assertReplayCorpusCoversCatalog(
	t *testing.T,
	catalog []skillpkg.Manifest,
) {
	t.Helper()
	catalogIDs := map[string]bool{}
	for _, manifest := range catalog {
		catalogIDs[manifest.SkillID] = true
		rawPrompts, ok := replayPromptsBySkill[manifest.SkillID]
		if !ok {
			t.Fatalf("skill %q has no replay corpus", manifest.SkillID)
		}
		prompts := splitReplayPrompts(rawPrompts)
		if len(prompts) != replayCasesPerSkill {
			t.Fatalf(
				"skill %q replay inputs=%d, want %d",
				manifest.SkillID,
				len(prompts),
				replayCasesPerSkill,
			)
		}
		seenInputs := map[string]bool{}
		for _, prompt := range prompts {
			if seenInputs[prompt] {
				t.Fatalf("skill %q has duplicate replay input %q", manifest.SkillID, prompt)
			}
			seenInputs[prompt] = true
		}
	}
	for skillID := range replayPromptsBySkill {
		if !catalogIDs[skillID] {
			t.Fatalf("replay corpus references unknown skill %q", skillID)
		}
	}
}

func replayCasesForManifest(
	t *testing.T,
	manifest skillpkg.Manifest,
) []assistant.ReplayCase {
	t.Helper()
	prompts := splitReplayPrompts(replayPromptsBySkill[manifest.SkillID])
	cases := make([]assistant.ReplayCase, 0, len(prompts))
	for index, prompt := range prompts {
		caseID := fmt.Sprintf("agent_eval_%s_%02d", manifest.SkillID, index+1)
		clarificationSlotIDs := []string{}
		expectedToolNames := []string{}
		expectedReferenceURLs := []string{}
		finalAnswerMode := "full"
		modelScript := []assistant.ReplayModelStep{}
		toolScript := []assistant.ReplayToolStep{}
		if index == len(prompts)-1 && len(manifest.SlotSchema.RequiredSlots) > 0 {
			clarificationSlotIDs = []string{manifest.SlotSchema.RequiredSlots[0]}
			finalAnswerMode = "clarify"
		} else if index == len(prompts)-1 {
			modelScript = directAnswerScript(manifest, prompt)
		} else {
			toolName := manifest.ToolPolicy.PreferredTools[0]
			referenceURL := "https://example.com/assistant-eval/" + caseID
			expectedToolNames = []string{toolName}
			expectedReferenceURLs = []string{referenceURL}
			modelScript = groundedAnswerScript(manifest, prompt, referenceURL)
			toolScript = []assistant.ReplayToolStep{{
				ToolName: toolName,
				Input:    map[string]any{"query": prompt},
				Result: map[string]any{
					"kind":     "tool_result",
					"summary":  manifest.DisplayName + " 已取得可核验结果。",
					"reliable": true,
					"references": []map[string]any{{
						"title":      manifest.DisplayName + " 权威资料",
						"objectType": "web.document",
						"url":        referenceURL,
						"source":     "assistant_eval_source",
						"snippet":    "该引用直接支持本 Case 的回答。",
					}},
				},
			}}
		}
		cases = append(cases, assistant.ReplayCase{
			ReplayCaseID: caseID,
			Title:        manifest.DisplayName + "轨迹回放",
			Request: assistant.ReplayRequest{
				ConversationID: "acv_" + caseID,
				TurnID:         "atn_" + caseID,
				UserID:         "persona_agent_eval",
				InputText:      prompt,
				ClientContext:  map[string]any{"surfaceId": "assistant.personal"},
			},
			FakeModelScript: modelScript,
			FakeToolScript:  toolScript,
			Expectations: assistant.ReplayExpectations{
				SelectedSkillID:              manifest.SkillID,
				SelectedDomainID:             manifest.DomainID,
				ExpectedToolNames:            expectedToolNames,
				ExpectedClarificationSlotIDs: clarificationSlotIDs,
				ExpectedReferenceURLs:        expectedReferenceURLs,
				FinalAnswerMode:              finalAnswerMode,
			},
		})
	}
	return cases
}

func groundedAnswerScript(
	manifest skillpkg.Manifest,
	prompt string,
	referenceURL string,
) []assistant.ReplayModelStep {
	accepted := map[string]any{
		"title":   manifest.DisplayName + " 权威资料",
		"source":  "assistant_eval_source",
		"snippet": "该引用直接支持本 Case 的回答。",
		"destination": map[string]any{
			"kind": "external",
			"url":  referenceURL,
		},
	}
	forged := map[string]any{
		"title":  "未由工具返回的伪造资料",
		"source": "forged",
		"destination": map[string]any{
			"kind": "external",
			"url":  "https://forged.invalid/not-from-tool",
		},
	}
	return []assistant.ReplayModelStep{
		{
			Stage: "reasoning",
			Text:  "需要调用允许的工具取得资料。",
			StructuredDelta: map[string]any{
				"nextAction": "tool_call",
				"toolName":   manifest.ToolPolicy.PreferredTools[0],
				"toolInput":  map[string]any{"query": prompt},
			},
			FinishReason: "tool_use",
		},
		{
			Stage: "evidence_processing",
			Text:  "已核对资料覆盖范围。",
			StructuredDelta: map[string]any{
				"retrievalProcessing": map[string]any{
					"processingSummary": "已核对资料覆盖范围。",
					"selectedKeyPoints": []string{"关键结论已获得资料支持"},
					"acceptedReferences": []map[string]any{
						forged,
						accepted,
					},
				},
				"evidenceSufficient": true,
			},
			FinishReason: "stop",
		},
		{
			Stage:        "final",
			Text:         manifest.DisplayName + "已基于可核验资料完成回答。",
			FinishReason: "stop",
		},
	}
}

func directAnswerScript(
	manifest skillpkg.Manifest,
	_ string,
) []assistant.ReplayModelStep {
	return []assistant.ReplayModelStep{
		{
			Stage: "reasoning",
			Text:  "该问题可直接回答。",
			StructuredDelta: map[string]any{
				"nextAction": "answer",
			},
			FinishReason: "stop",
		},
		{
			Stage:        "final",
			Text:         manifest.DisplayName + "已直接完成回答。",
			FinishReason: "stop",
		},
	}
}

func roundTripReplayCase(
	t *testing.T,
	replay assistant.ReplayCase,
) assistant.ReplayCase {
	t.Helper()
	raw, err := json.Marshal(replay)
	if err != nil {
		t.Fatalf("marshal assistant_replay_case: %v", err)
	}
	var decoded assistant.ReplayCase
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatalf("unmarshal assistant_replay_case: %v", err)
	}
	if strings.TrimSpace(decoded.Expectations.SelectedSkillID) == "" ||
		strings.TrimSpace(decoded.Expectations.SelectedDomainID) == "" ||
		strings.TrimSpace(decoded.Expectations.FinalAnswerMode) == "" {
		t.Fatalf("assistant_replay_case lost required expectations: %#v", decoded.Expectations)
	}
	return decoded
}

func assertReplayTrajectory(
	t *testing.T,
	manifest skillpkg.Manifest,
	replay assistant.ReplayCase,
	transcript simulator.Transcript,
) {
	t.Helper()
	expectations := replay.Expectations
	if transcript.Failure != nil {
		t.Fatalf("runtimeFailure=%#v", transcript.Failure)
	}
	if transcript.SelectedSkillID != expectations.SelectedSkillID ||
		transcript.SelectedDomainID != expectations.SelectedDomainID {
		t.Fatalf(
			"selected skill/domain=%s/%s, want %s/%s",
			transcript.SelectedSkillID,
			transcript.SelectedDomainID,
			expectations.SelectedSkillID,
			expectations.SelectedDomainID,
		)
	}
	actualTools := make([]string, 0, len(transcript.ToolCalls))
	allowedTools := stringSetForReplay(manifest.ToolPolicy.AllowedTools)
	for _, call := range transcript.ToolCalls {
		actualTools = append(actualTools, call.ToolName)
		if !allowedTools[call.ToolName] {
			t.Fatalf(
				"tool %q is outside skill %q allowedTools=%v",
				call.ToolName,
				manifest.SkillID,
				manifest.ToolPolicy.AllowedTools,
			)
		}
	}
	if !reflect.DeepEqual(actualTools, expectations.ExpectedToolNames) {
		t.Fatalf("tool calls=%v, want %v", actualTools, expectations.ExpectedToolNames)
	}
	if !reflect.DeepEqual(
		transcript.ClarificationSlotIDs,
		expectations.ExpectedClarificationSlotIDs,
	) {
		t.Fatalf(
			"clarification slots=%v, want %v",
			transcript.ClarificationSlotIDs,
			expectations.ExpectedClarificationSlotIDs,
		)
	}
	actualReferences := sortedReplayStrings(transcript.ReferenceURLs)
	expectedReferences := sortedReplayStrings(expectations.ExpectedReferenceURLs)
	if !reflect.DeepEqual(actualReferences, expectedReferences) {
		t.Fatalf("reference URLs=%v, want %v", actualReferences, expectedReferences)
	}
	for _, referenceURL := range transcript.ReferenceURLs {
		if referenceURL == "https://forged.invalid/not-from-tool" {
			t.Fatal("user-visible references accepted a URL absent from tool results")
		}
	}
	if transcript.FinalAnswerMode != expectations.FinalAnswerMode {
		t.Fatalf(
			"finalAnswerMode=%q, want %q",
			transcript.FinalAnswerMode,
			expectations.FinalAnswerMode,
		)
	}
}

func splitReplayPrompts(raw string) []string {
	parts := strings.Split(raw, "|")
	prompts := make([]string, 0, len(parts))
	for _, part := range parts {
		if prompt := strings.TrimSpace(part); prompt != "" {
			prompts = append(prompts, prompt)
		}
	}
	return prompts
}

func sortedReplayStrings(values []string) []string {
	sorted := append([]string(nil), values...)
	sort.Strings(sorted)
	return sorted
}

func stringSetForReplay(values []string) map[string]bool {
	set := make(map[string]bool, len(values))
	for _, value := range values {
		set[value] = true
	}
	return set
}

var replayPromptsBySkill = map[string]string{
	"astrology_constellation":  `解释上升星座和太阳星座的区别|月亮星座通常代表什么|星盘里的宫位该怎么理解|水逆在占星语境里是什么意思|金星和火星相位如何解读|太阳月亮上升如何综合看|合相与对冲有什么差异|出生时间误差会怎样影响星盘|如何理性看待占星人格描述|给初学者一份星盘阅读顺序`,
	"calendar_task":            `安排明天上午十点的项目会并提前半小时提醒|把周五下午三点的复盘加入待办|提醒我今晚九点提交周报|下周一早上八点提醒我带证件|安排后天下午的牙医预约提醒|每周三晚上提醒我跑步|帮我整理今天尚未完成的待办|给月底报销设置两次提醒|安排周末给父母打电话的待办|列出创建会议前需要确认的信息`,
	"creation_assistant":       `帮我整理一篇西湖旅行草稿的摘要|给城市夜景照片推荐合适标签|这篇徒步记录适合关联哪个地点主页|把露营体验草稿整理成发布提纲|为海边日落照片补充内容结构|推荐这篇咖啡探店笔记可加入的圈子|帮我检查游记标题是否清楚|把器材测评草稿提炼成三个要点|给古建筑摄影作品设计讨论问题|整理一份发布前的关联对象清单`,
	"daily_assistant":          `每天早上提醒我查看工作和学习计划|工作日晚上提醒我复盘当天任务|每天午休前汇总尚未完成的待办|每周一早上整理本周重点|每天睡前提醒我准备第二天物品|工作日上午提醒我安排深度工作|每天傍晚汇总运动和饮水计划|每周五提醒我完成周报|考试前两周每天提醒复习进度|出差期间每天早上整理日程`,
	"divination_fortune":       `给我一份今天事业运的趣味建议|今天财运可以怎样轻松解读|看看今天的人际运势仅供娱乐|用积极方式解读今天的选择运|今天适合怎样安排重要任务|给今天的情绪状态一点趣味提示|解读本周桃花运但不要绝对化|给我一个现实可执行的开运小行动|今天做决定时该注意什么|解释为什么运势不能替代现实决策`,
	"education_learning":       `制定两周考研英语复习计划|帮我拆解高中数学函数学习路径|准备雅思口语每天该练什么|一周掌握摄影曝光基础怎么安排|给小学生设计阅读习惯计划|解释错题本应该怎样复盘|帮我规划三个月编程入门学习|考试前一天如何高效复习|比较自学和报班的适用情况|给我一份论文阅读训练方法`,
	"emotion_companion":        `最近工作压力很大想和你梳理一下|我有点焦虑不知道从哪里开始|今天很难过请先陪我聊聊|和朋友闹矛盾后一直内耗|面试失败让我很受打击|最近睡前总在担心工作|分手后情绪反复怎么办|我觉得自己什么都做不好|家里争吵让我很疲惫|遇到强烈情绪时可以先做什么`,
	"fallback_general_search":  `搜索最近值得关注的人工智能产品发布|查找今年热门的城市徒步路线|总结近期可持续包装的新趋势|搜索适合家庭使用的云存储方案|查找公开的摄影比赛征稿信息|总结最近的开源数据库动态|搜索城市公共自行车发展案例|查找远程办公工具的新功能|总结近期消费电子新品方向|搜索一个冷门主题并说明核验方法`,
	"family_parenting":         `青春期孩子叛逆时怎样沟通|孩子写作业总拖延怎么办|幼儿第一次上学如何缓解焦虑|兄弟姐妹争抢玩具怎么处理|孩子沉迷手机怎样共同定规则|亲子沟通中如何减少说教|孩子考试失利后怎么安慰|如何培养小学生的阅读习惯|父母意见不一致时怎样协作育儿|发现孩子被欺负时先做什么`,
	"finance_consumer":         `分析比亚迪今天的重大消息和风险|比较两只基金前要看哪些指标|家庭应急预算该怎样规划|选择保险时如何识别关键条款|贷款利率变化会怎样影响月供|比较信用卡权益和年费的方法|行业估值变化该如何理性理解|股票波动时怎样避免冲动决策|制定一年储蓄计划需要哪些信息|解释为什么投资结论必须标注时效`,
	"fortune_astrology":        `金牛座本周事业和感情运势如何|双子座今天适合怎样安排工作|用娱乐方式解读狮子座本月状态|水逆期间有哪些理性行动建议|天秤座本周人际关系趣味解读|射手座近期旅行运势怎么看|摩羯座事业节奏可以怎样理解|双鱼座感情运势请避免宿命判断|星座运势为什么只能作为娱乐|给白羊座一条现实可执行的建议`,
	"health_wellness":          `最近睡眠不好想改善作息|给久坐上班族一份低风险运动建议|减脂期间怎样安排均衡饮食|跑步后膝盖不适应该注意什么|如何逐步减少熬夜|高压工作时怎样保持规律饮水|新手力量训练每周如何安排|外出旅行怎样维持健康饮食|持续头痛时哪些情况应及时就医|解释健康建议与医疗诊断的边界`,
	"huawei_cloud_qa":          `华为云上做大模型推理如何选择昇腾|比较容器服务和云服务器的适用场景|对象存储适合保存哪些模型资产|高斯数据库选型要关注什么|鲲鹏服务器适合哪些工作负载|盘古大模型服务有哪些验证维度|华为云计费比较时要核对什么|云上部署推理服务如何考虑安全|对象存储和文件存储有什么区别|给我一份华为云方案验证清单`,
	"knowledge_general":        `解释大模型RAG的原理和局限|量子计算和经典计算有什么区别|什么是零知识证明|用例子解释机会成本|翻译并解释机器学习中的过拟合|为什么天空看起来是蓝色|区块链共识机制解决什么问题|解释数据库索引的工作原理|什么是碳足迹以及如何计算|比较相关性和因果性的区别`,
	"local_life":               `成都春熙路附近的餐厅今晚怎么选|上海徐家汇周末的餐厅和本地好去处|北京三里屯附近预算200元找餐厅|广州天河体育中心附近的粤菜餐厅|杭州西湖附近适合家庭的餐厅|深圳南山今晚有哪些餐厅和安静咖啡馆|南京夫子庙附近有哪些本地美食|武汉餐厅周末朋友聚会怎么选|西安钟楼附近的餐厅和夜游怎么安排|预算200元帮我推荐一个吃饭地方`,
	"news_briefing":            `每天早上给我人工智能新闻摘要|工作日汇总半导体产业新闻|每天晚上整理国内文旅新闻|每周汇总开源软件重要动态|每天推送摄影器材新品消息|早上汇总新能源汽车重大新闻|每周整理教育政策公开消息|每天关注气候科技新闻|下班前汇总云计算行业新闻|每周生成城市更新新闻简报`,
	"policy_public_service":    `广州办理居住证需要哪些材料|深圳公积金提取流程怎么查|北京社保转移要满足什么条件|上海人才落户政策如何核验|成都护照换发需要准备什么|杭州个体工商户登记流程是什么|南京生育津贴怎样申请|武汉异地就医备案怎么办|西安公共租赁住房申请条件有哪些|解释政务信息为什么必须核对地区和时效`,
	"relationship_matchmaking": `和伴侣沟通总吵架怎么表达更温和|想表白但担心给对方压力|分手后是否挽回该考虑什么|异地关系如何建立稳定沟通|伴侣总是回避冲突怎么办|怎样提出自己的关系边界|第一次见对方父母如何准备|关系中缺乏信任怎么逐步修复|朋友介绍相亲时如何自然聊天|给我一个非暴力沟通表达示例`,
	"shopping_decision":        `两千元内降噪耳机怎么选|对比两款手机时要看哪些参数|家用扫地机器人怎样比较性价比|第一次买相机该如何确定预算|通勤背包要关注哪些使用体验|空气净化器选购如何看指标|儿童安全座椅怎样核对标准|机械键盘不同轴体怎么取舍|旅行充电器如何兼顾功率和重量|促销期间怎样判断是否值得购买`,
	"social_companion_chat":    `有点无聊陪我轻松聊聊天|今天发生了一件小趣事|在吗想随便聊几句|给我一个轻松的话题|哈哈我刚刚坐过站了|周末宅在家有点闷|陪我聊聊最近看的电影|想分享今天的一点小进步|来玩一个不需要道具的小游戏|睡前聊一个温柔的小问题`,
	"stock_sentinel":           `每天开盘前提醒我关注股票重大消息|收盘后汇总关注标的异常波动|公告发布时提醒我核对原文|每天提醒我查看持仓风险事件|开盘前整理行业政策变化|盘中出现重大消息时给出摘要|每周汇总关注公司的公告|财报季提醒我查看披露时间|提醒我区分市场传闻和正式公告|每天收盘后生成非投资建议摘要`,
	"travel_journey_manager":   `出发前提醒我行程天气和路况|每天早上检查景点拥堵风险|航班前提醒我核对天气变化|自驾出发前汇总道路信息|旅行中每天提醒下一站安排|景区关闭时提醒我准备备选|高铁出发前提醒换乘缓冲|返程当天汇总交通和天气|亲子旅行每日提醒休息节奏|行程变化时提醒我重新核对关键事项`,
	"travel_planning":          `周末去杭州旅行帮我规划两日行程|下周去成都旅行安排景点和酒店区域|明天去苏州一日游怎样规划|本周末去南京带父母旅行怎么安排|下周去厦门三日旅行预算5000元|后天去北京两人旅行如何避开拥堵|周末去长沙安排美食和景点|本周去青岛亲子旅行住哪里方便|下周去西安旅行如何安排历史景点|明天帮我规划旅行`,
	"travel_transport":         `明天从深圳出发去广州规划高铁路线|后天从北京出发到天津比较交通方式|周末从上海出发去苏州安排换乘|下周从成都出发到重庆规划高铁|明天从杭州出发去宁波比较自驾和火车|本周末从南京出发到扬州规划路线|后天从武汉出发去长沙预留换乘缓冲|下周从西安出发到洛阳安排交通|明天从广州出发去珠海比较耗时|明天帮我规划高铁路线`,
	"weather":                  `上海天气明天下午降雨如何|北京今天气温和穿衣建议|广州后天天气和空气质量怎么样|杭州周末天气适合骑行吗|深圳明天天气的紫外线强不强|成都本周末天气会下雨吗|南京今天天气的风力和体感如何|武汉下周天气趋势怎么样|厦门明天天气适合海边拍照吗|明天天气怎么样`,
	"work_productivity":        `把下周产品评审拆成任务和里程碑|制定一个月项目推进计划|帮我整理本周工作复盘|面试准备应该怎样分阶段|优化一份产品经理简历的结构|为跨部门项目列出风险清单|把复杂需求拆成可执行任务|制定季度职业成长目标|设计一次高效周会流程|项目延期时如何重新排优先级`,
}
