#!/usr/bin/env bash
# T3 鉴权会话级 · 任务1回归：dislike 单条内容负反馈在 feed「仓库兜底分页」路径生效。
# 真实 HTTP / curl 级集成验证（gamma-local，content-service 已重建为含 SessionCache
# NegativeFeedbackReader 转发的新镜像）。不构建/修改 Flutter app 代码；不放宽门禁。
#
# 修复前（见 README §4.1）：被 dislike 的 post 仍出现在 feed（fallback 路径未过滤）。
# 修复后：被 dislike 的 post 连续多次 feed（含 limit=50 触达兜底分页）不再出现，且
# rec:negative:{user} 含该 post。
set -uo pipefail
GW="http://127.0.0.1:19000"; US="http://127.0.0.1:19210"; CS="http://127.0.0.1:19220"
RC="quwoquan_service-redis-1"
OUT="artifacts/home-rec-phase9/t3-session"; mkdir -p "$OUT"
ts(){ date -u +%Y-%m-%dT%H:%M:%SZ; }
say(){ echo; echo "==================== $* ===================="; }
RUN="t3neg_$(date -u +%Y%m%d%H%M%S)"
INSTALL="t3-session-install-01"; FPHASH="t3sessionfphash01"

say "STEP 1: 建立鉴权会话（anonymous device login 恢复路径）"
curl -sS -X POST "$US/v1/auth/login/anonymous" -H "Content-Type: application/json" \
  -d "{\"installId\":\"$INSTALL\",\"deviceFingerprintHash\":\"$FPHASH\",\"platform\":\"ios\",\"appVersion\":\"1.0.0\"}" > "$OUT/08_login_raw.json"
TOKEN=$(python3 -c "import json;print(json.load(open('$OUT/08_login_raw.json')).get('accessToken',''))")
SUB=$(python3 -c "import json;print(json.load(open('$OUT/08_login_raw.json')).get('activeSub',{}).get('subAccountId',''))")
if [ -z "$TOKEN" ] || [ -z "$SUB" ]; then echo "FATAL: login failed"; cat "$OUT/08_login_raw.json"; exit 1; fi
SESSION="${RUN}_sess"
AUTH=(-H "Authorization: Bearer $TOKEN" -H "X-Client-User-Id: $SUB" -H "X-Client-Session-Id: $SESSION")
echo "subAccountId=$SUB sessionId=$SESSION tokenLen=${#TOKEN}"

say "STEP 2: 取会话 feed，选定一个 dislike 目标 post"
curl -sS "${AUTH[@]}" "$GW/v1/content/feed?sort=recommend&limit=20" > "$OUT/08_feed_before.json"
FRQ=$(python3 -c "import json;print(json.load(open('$OUT/08_feed_before.json')).get('feedRequestId',''))")
read DIS_POST DIS_AUTHOR DIS_CT DIS_POS < <(python3 - "$OUT/08_feed_before.json" <<'PY'
import sys,json
d=json.load(open(sys.argv[1])); items=d.get('items',[])
def ct(it): return it.get('contentType') or it.get('type') or ''
# 选一个稳定可定位的单条 post（取第一个有 id 的）。
for i,it in enumerate(items):
    if it.get('id'):
        print(it['id'], it.get('authorId') or '', ct(it), i); break
else:
    print('','','',0)
PY
)
if [ -z "$DIS_POST" ]; then echo "FATAL: no feed item to dislike"; cat "$OUT/08_feed_before.json"; exit 1; fi
echo "dislike target: post=$DIS_POST author=$DIS_AUTHOR type=$DIS_CT pos=$DIS_POS feedRequestId=$FRQ"

say "STEP 3: 服务端 patch 指标（before）"
curl -sS "$CS/metrics" | grep -E "^recommendation_feed_patch_emitted_total" > "$OUT/08_metrics_before.txt" || true
cat "$OUT/08_metrics_before.txt"

say "STEP 4: 上报 dislike 单条内容负反馈"
BEH_BODY=$(cat <<JSON
{"userId":"$SUB","events":[
 {"clientEventId":"${RUN}_dislike","type":"dislike","postId":"$DIS_POST","authorId":"$DIS_AUTHOR","contentType":"$DIS_CT","state":"negative","feedRequestId":"$FRQ","position":$DIS_POS,"channelId":"recommend","rankingVersion":"rec-v1","referralSource":"organic_feed"}
]}
JSON
)
echo "$BEH_BODY" > "$OUT/08_behaviors_request.json"
BEH_CODE=$(curl -sS -o "$OUT/08_behaviors_response.json" -w "%{http_code}" -X POST "${AUTH[@]}" -H "Content-Type: application/json" -d "$BEH_BODY" "$GW/v1/content/behaviors")
echo "POST /v1/content/behaviors -> HTTP $BEH_CODE"; cat "$OUT/08_behaviors_response.json"; echo

say "STEP 4c: Redis 侧证据（rec:negative:{user} 含被 dislike 的 post）"
docker exec "$RC" sh -lc 'for k in $(redis-cli --scan --pattern "rec:negative:*"); do echo "$k => $(redis-cli SMEMBERS "$k" | tr "\n" " ")"; done' > "$OUT/08_redis_negative.txt" 2>&1 || true
cat "$OUT/08_redis_negative.txt"
NEG_HAS=$(grep -c "$DIS_POST" "$OUT/08_redis_negative.txt" || true)

sleep 2
say "STEP 5: 连续多次取 feed（含 limit=50 触达仓库兜底分页），断言被 dislike 的 post 不再出现"
PASS_DISLIKE=1
for n in 1 2 3; do
  curl -sS "${AUTH[@]}" "$GW/v1/content/feed?sort=recommend&limit=50" > "$OUT/08_feed_after_${n}.json"
  PRESENT=$(python3 - "$OUT/08_feed_after_${n}.json" "$DIS_POST" <<'PY'
import sys,json
d=json.load(open(sys.argv[1])); dp=sys.argv[2]; items=d.get('items',[])
print(1 if any(it.get('id')==dp for it in items) else 0, len(items))
PY
)
  P=$(echo "$PRESENT"|cut -d' ' -f1); CNT=$(echo "$PRESENT"|cut -d' ' -f2)
  echo "re-fetch #$n (limit=50): items=$CNT  disliked_post_present=$P"
  [ "$P" != "0" ] && PASS_DISLIKE=0
done

say "STEP 6: 服务端 patch 指标（after）"
curl -sS "$CS/metrics" | grep -E "^recommendation_feed_patch_emitted_total" > "$OUT/08_metrics_after.txt" || true
cat "$OUT/08_metrics_after.txt"

say "STEP 7: 汇总判定"
python3 - "$DIS_POST" "$PASS_DISLIKE" "$NEG_HAS" "$BEH_CODE" <<'PY'
import sys,json,os,re
B="artifacts/home-rec-phase9/t3-session/"
dp,pd,neg,beh=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]
def sump(path):
    if not os.path.exists(path): return 0.0
    s=0.0
    for line in open(path):
        m=re.match(r'^recommendation_feed_patch_emitted_total\{[^}]*patch_type="negative_feedback_removal"[^}]*\}\s+([0-9.eE+-]+)$',line.strip())
        if m: s+=float(m.group(1))
    return s
delta=sump(B+"08_metrics_after.txt")-sump(B+"08_metrics_before.txt")
res={
 "image":"localhost/quwoquan_service_content-service:latest (sha256:af8610ba3c0d…)",
 "disliked_post":dp,
 "behaviors_http":int(beh),
 "rec_negative_contains_disliked_post": int(neg)>0,
 "dislike_single_post_removal_fallback_path":"PASS" if pd=="1" else "FAIL",
 "negative_feedback_removal_patch_metric_delta":delta,
 "capturedAt":__import__('datetime').datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
}
json.dump(res,open(B+"08_dislike_fallback_matrix.json","w"),ensure_ascii=False,indent=2)
print(json.dumps(res,ensure_ascii=False,indent=2))
PY
echo; echo "证据目录: $OUT (08_*)"
