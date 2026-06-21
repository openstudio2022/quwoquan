#!/usr/bin/env bash
# T3 鉴权会话级 · 任务2回归：按 env-seed-first 注入社交图/交集种子后，鉴权会话 feed
# envelope 的 intersectionReasons 可非空且语义正确。
#
# 正规 seed 通道（单一真相源 fixture + 幂等 applier）：
#   fixture : quwoquan_service/contracts/metadata/_shared/test_fixtures/content_recommendation_social_graph.gamma_seed.json
#   applier : quwoquan_service/scripts/seed/apply_content_social_graph_seed.py
# 应用器向 content-service 自身库 quwoquan_content 幂等 upsert follow_edges + rm_recommend_feature
# 并失效 viewer 的 rm_viewer_object_intersection 预物化快照（真实部署里这两个读模型由 user-service
# 关注事件投影产出，gamma-local 未接线该跨服务投影；fixture 为其最小正规替身）。
# 真实 HTTP / curl 级集成验证 —— 不构建/修改 Flutter app 代码；不放宽门禁。
set -uo pipefail
GW="http://127.0.0.1:19000"; US="http://127.0.0.1:19210"
RC="quwoquan_service-redis-1"; MC="quwoquan_service-mongodb-1"
OUT="artifacts/home-rec-phase9/t3-session"; mkdir -p "$OUT"
say(){ echo; echo "==================== $* ===================="; }
SUB="us_01_3278_01kvevr8s7s3b0arr7x3p27efe"
INSTALL="t3-session-install-01"; FPHASH="t3sessionfphash01"

say "STEP 0: （幂等）应用社交图交集种子 fixture"
python3 quwoquan_service/scripts/seed/apply_content_social_graph_seed.py \
  --report "$OUT/09_seed_apply_report.json" 2>&1 | tail -2
echo "--- seeded follow_edges / friend features ---"
docker exec "$MC" mongosh --quiet quwoquan_content --eval '
print("follow_edges(viewer)="+db.follow_edges.countDocuments({followerId:"'"$SUB"'"}));
db.rm_recommend_feature.find({userId:{$in:["fixture_user_travel","fixture_user_outdoor_01"]}},{_id:0,userId:1,"userFeatures.tagInteraction":1}).forEach(function(d){print(JSON.stringify(d));});
' > "$OUT/09_seed_state.txt" 2>&1
cat "$OUT/09_seed_state.txt"

say "STEP 1: 建立鉴权会话（anonymous device login 恢复路径）"
TOKEN=$(curl -sS -X POST "$US/v1/auth/login/anonymous" -H 'Content-Type: application/json' \
  -d "{\"installId\":\"$INSTALL\",\"deviceFingerprintHash\":\"$FPHASH\",\"platform\":\"ios\",\"appVersion\":\"1.0.0\"}" \
  | python3 -c "import json,sys;print(json.load(sys.stdin).get('accessToken',''))")
if [ -z "$TOKEN" ]; then echo "FATAL: login failed"; exit 1; fi
SESSION="ix_seed_$(date -u +%Y%m%d%H%M%S)"
AUTH=(-H "Authorization: Bearer $TOKEN" -H "X-Client-User-Id: $SUB" -H "X-Client-Session-Id: $SESSION")
echo "subAccountId=$SUB sessionId=$SESSION tokenLen=${#TOKEN}"

say "STEP 2: 鉴权会话 feed envelope intersectionReasons 非空断言"
curl -sS "${AUTH[@]}" "$GW/v1/content/feed?sort=recommend&limit=50" > "$OUT/09_feed_session.json"
python3 - > "$OUT/09_intersection_matrix.json" <<'PY'
import json
B="artifacts/home-rec-phase9/t3-session/"
d=json.load(open(B+"09_feed_session.json"))
items=d.get('items',[])
withix=[it for it in items if it.get('intersectionReasons')]
samples=[]
ok_semantics=False
for it in withix[:5]:
    for r in it.get('intersectionReasons',[]):
        pt=r.get('primaryText','')
        samples.append({"postId":it.get('id'),"primaryText":pt,"weightTier":r.get('weightTier'),
                        "dimension":r.get('dimension'),"source":r.get('source'),
                        "intersectionClass":r.get('intersectionClass')})
        if pt and ("关注的人" in pt or "共同" in pt or "都" in pt):
            ok_semantics=True
res={
 "envelope_feedRequestId":d.get('feedRequestId'),
 "rankingVersion":d.get('rankingVersion'),
 "reasonVersion":d.get('reasonVersion'),
 "item_count":len(items),
 "items_with_intersectionReasons":len(withix),
 "intersectionReasons_present": len(withix)>0,
 "intersectionReasons_semantics_ok": ok_semantics,
 "samples":samples,
 "checkA_envelope_intersectionReasons":"PASS" if (len(withix)>0 and ok_semantics) else "FAIL",
}
json.dump(res,open(B+"09_intersection_matrix.json","w"),ensure_ascii=False,indent=2)
print(json.dumps(res,ensure_ascii=False,indent=2))
PY

say "STEP 3: 交集 inbox summary（同源 FactReasons 读模型，旁证非空）"
curl -sS "${AUTH[@]}" "$GW/v1/content/intersections/summary" > "$OUT/09_intersections_summary.json" 2>&1 || true
cat "$OUT/09_intersections_summary.json"; echo

say "STEP 4: 回算后的 viewer 交集快照（rm_viewer_object_intersection 已物化非空）"
docker exec "$MC" mongosh --quiet quwoquan_content --eval '
var doc=db.rm_viewer_object_intersection.findOne({_id:"'"$SUB"'"});
if(doc){ var r=JSON.parse(doc.reasonsJson||"[]"); print("viewer snapshot reasons="+r.length); r.slice(0,3).forEach(function(x){print("  primaryText="+(x.primaryText||"")+" dim="+x.dimension+" src="+x.source);}); }
else { print("viewer snapshot: <none>"); }
' > "$OUT/09_viewer_snapshot.txt" 2>&1
cat "$OUT/09_viewer_snapshot.txt"
echo; echo "证据目录: $OUT (09_*)"
