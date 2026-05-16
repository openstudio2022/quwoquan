"""一次性迁移脚本：将住宿实体的旧六轴 tagRefs 迁移到新结构。"""
import json
from pathlib import Path

ENTITIES_ROOT = Path(__file__).resolve().parents[1] / "publish" / "v1" / "entities"

TAG_MIGRATION = {
    # 住宿业态 → Entity/地点/住宿 扁平
    "Entity/地点/住宿/住宿业态/度假村": "Entity/地点/住宿/度假村",
    "Entity/地点/住宿/住宿业态/五星级酒店": "Entity/地点/住宿/酒店",
    "Entity/地点/住宿/住宿业态/四星级酒店": "Entity/地点/住宿/酒店",
    "Entity/地点/住宿/住宿业态/精品民宿": "Entity/地点/住宿/民宿",
    "Entity/地点/住宿/住宿业态/特色民宿": "Entity/地点/住宿/民宿",
    "Entity/地点/住宿/住宿业态/客栈": "Entity/地点/住宿/客栈",
    "Entity/地点/住宿/住宿业态/青年旅舍": "Entity/地点/住宿/青旅",
    "Entity/地点/住宿/住宿业态/农家乐": "Entity/地点/住宿/农家乐",
    "Entity/地点/住宿/住宿业态/胶囊旅馆": "Entity/地点/住宿/胶囊酒店",
    "Entity/地点/住宿/住宿业态/酒店式公寓": "Entity/地点/住宿/酒店式公寓",
    "Entity/地点/住宿/住宿业态/帐篷酒店": "Entity/地点/住宿/营地",
    "Entity/地点/住宿/住宿业态/酒店": "Entity/地点/住宿/酒店",
    "Entity/地点/住宿/住宿业态/民宿": "Entity/地点/住宿/民宿",

    # 档次等级 → Topic/住宿/价位档次
    "Entity/地点/住宿/档次等级/豪华型": "Topic/住宿/价位档次/奢华型",
    "Entity/地点/住宿/档次等级/高端型": "Topic/住宿/价位档次/高端型",
    "Entity/地点/住宿/档次等级/中高端": "Topic/住宿/价位档次/高端型",
    "Entity/地点/住宿/档次等级/中端型": "Topic/住宿/价位档次/中端型",
    "Entity/地点/住宿/档次等级/经济型": "Topic/住宿/价位档次/经济型",
    "Entity/地点/住宿/档次等级/白金五星级": "Topic/住宿/价位档次/超奢华型",
    "Entity/地点/住宿/档次等级/五星级": "Topic/住宿/业态/星级酒店/五星酒店",
    "Entity/地点/住宿/档次等级/舒适型": "Topic/住宿/价位档次/中端型",

    # 功能定位 → Topic/住宿/主题
    "Entity/地点/住宿/功能定位/度假住宿": "Topic/住宿/主题/康养主题",
    "Entity/地点/住宿/功能定位/温泉住宿": "Topic/住宿/主题/温泉主题",
    "Entity/地点/住宿/功能定位/亲子友好住宿": "Topic/住宿/主题/亲子主题",
    "Entity/地点/住宿/功能定位/商务差旅住宿": "Topic/住宿/主题/商务主题",
    "Entity/地点/住宿/功能定位/文化体验": "Topic/住宿/主题/文化体验",
    "Entity/地点/住宿/功能定位/康养禅修": "Topic/住宿/主题/康养主题",
    "Entity/地点/住宿/功能定位/高原友好住宿": "Topic/住宿/主题/自驾友好",
    "Entity/地点/住宿/功能定位/城市商旅": "Topic/住宿/主题/商务主题",
    "Entity/地点/住宿/功能定位/经济实惠": "Topic/住宿/价位档次/经济型",
    "Entity/地点/住宿/功能定位/背包客社交": "Topic/住宿/主题/单人友好",
    "Entity/地点/住宿/功能定位/休闲田园": "Topic/住宿/主题/生态田园",
    "Entity/地点/住宿/功能定位/设计精品住宿": "Topic/住宿/主题/文化体验",
    "Entity/地点/住宿/功能定位/机场高铁住宿": "Topic/住宿/区位/机场近",
    "Entity/地点/住宿/功能定位/商务住宿": "Topic/住宿/主题/商务主题",
    "Entity/地点/住宿/功能定位/会议会展住宿": "Topic/住宿/设施服务/会议室",

    # 设施服务 → Topic/住宿/设施服务
    "Entity/地点/住宿/设施服务/SPA水疗": "Topic/住宿/设施服务/SPA",
    "Entity/地点/住宿/设施服务/游泳池": "Topic/住宿/设施服务/泳池",
    "Entity/地点/住宿/设施服务/免费停车": "Topic/住宿/设施服务/停车场",
    "Entity/地点/住宿/设施服务/餐厅": "Topic/住宿/设施服务/酒店餐厅",
    "Entity/地点/住宿/设施服务/健身中心": "Topic/住宿/设施服务/健身房",
    "Entity/地点/住宿/设施服务/免费WiFi": "Topic/住宿/设施服务/免费WiFi",
    "Entity/地点/住宿/设施服务/洗衣服务": "Topic/住宿/设施服务/洗衣服务",
    "Entity/地点/住宿/设施服务/24小时前台": "Topic/住宿/设施服务/24h前台",
    "Entity/地点/住宿/设施服务/机场接送": "Topic/住宿/设施服务/机场接送",
    "Entity/地点/住宿/设施服务/行政酒廊": "Topic/住宿/设施服务/行政酒廊",
    "Entity/地点/住宿/设施服务/会议室": "Topic/住宿/设施服务/会议室",
    "Entity/地点/住宿/设施服务/含早餐": "Topic/住宿/设施服务/含早餐",
    "Entity/地点/住宿/设施服务/无障碍设施": "Topic/住宿/设施服务/无障碍",
    "Entity/地点/住宿/设施服务/儿童游乐设施": "Topic/住宿/设施服务/儿童设施",
    "Entity/地点/住宿/设施服务/酒吧": "Topic/住宿/设施服务/酒店酒吧",
    "Entity/地点/住宿/设施服务/温泉": "Topic/住宿/主题/温泉主题",
    "Entity/地点/住宿/设施服务/健身房": "Topic/住宿/设施服务/健身房",
    "Entity/地点/住宿/设施服务/厨房厨具": "Topic/住宿/设施服务/免费WiFi",
    "Entity/地点/住宿/设施服务/接送服务": "Topic/住宿/设施服务/机场接送",
    "Entity/地点/住宿/设施服务/温泉汤池": "Topic/住宿/主题/温泉主题",
    "Entity/地点/住宿/设施服务/儿童乐园": "Topic/住宿/设施服务/儿童设施",

    # 房型空间 → Topic/住宿/房型
    "Entity/地点/住宿/房型空间/大床房": "Topic/住宿/房型/大床房",
    "Entity/地点/住宿/房型空间/双床房": "Topic/住宿/房型/双床房",
    "Entity/地点/住宿/房型空间/套房": "Topic/住宿/房型/套房",
    "Entity/地点/住宿/房型空间/别墅": "Topic/住宿/房型/复式套房",
    "Entity/地点/住宿/房型空间/家庭房": "Topic/住宿/房型/家庭房",
    "Entity/地点/住宿/房型空间/亲子房": "Topic/住宿/房型/亲子房",
    "Entity/地点/住宿/房型空间/Loft": "Topic/住宿/房型/Loft",
    "Entity/地点/住宿/房型空间/单人间": "Topic/住宿/房型/单人间",

    # 房源形态 → Topic/住宿/业态/度假短租 或 Entity
    "Entity/地点/住宿/房源形态/独栋别墅": "Topic/住宿/业态/度假短租/整租别墅",
    "Entity/地点/住宿/房源形态/整套公寓": "Topic/住宿/业态/度假短租/整租公寓",
    "Entity/地点/住宿/房源形态/独立客房": "Topic/住宿/房型/单人间",
    "Entity/地点/住宿/房源形态/床位": "Topic/住宿/房型/单人间",
    "Entity/地点/住宿/房源形态/庭院": "Topic/住宿/业态/特色住宿",
    "Entity/地点/住宿/房源形态/帐篷": "Topic/住宿/业态/特色住宿/帐篷酒店",
    "Entity/地点/住宿/房源形态/木屋": "Topic/住宿/业态/特色住宿",
    "Entity/地点/住宿/房源形态/窑洞": "Topic/住宿/业态/特色住宿/洞穴酒店",
    "Entity/地点/住宿/房源形态/庭院客栈": "Entity/地点/住宿/客栈",
    "Entity/地点/住宿/房源形态/藏式民居": "Entity/地点/住宿/民宿",
    "Entity/地点/住宿/房源形态/树屋": "Topic/住宿/业态/特色住宿/树屋酒店",
    "Entity/地点/住宿/房源形态/合住房间": "Topic/住宿/房型/单人间",
}


def migrate():
    fixed = 0
    for ej in ENTITIES_ROOT.rglob("_entity.json"):
        data = json.loads(ej.read_text(encoding="utf-8"))
        old_refs = data.get("tagRefs", [])
        new_refs = []
        changed = False
        for ref in old_refs:
            if ref in TAG_MIGRATION:
                new_refs.append(TAG_MIGRATION[ref])
                changed = True
            elif ref.startswith("Entity/地点/住宿/住宿业态/") or \
                 ref.startswith("Entity/地点/住宿/档次等级/") or \
                 ref.startswith("Entity/地点/住宿/功能定位/") or \
                 ref.startswith("Entity/地点/住宿/设施服务/") or \
                 ref.startswith("Entity/地点/住宿/房型空间/") or \
                 ref.startswith("Entity/地点/住宿/房源形态/"):
                print(f"  WARN: 未映射的旧路径 '{ref}' in {ej.parent.name}，跳过")
                changed = True
            else:
                new_refs.append(ref)

        new_refs = list(dict.fromkeys(new_refs))
        if changed:
            data["tagRefs"] = new_refs
            ej.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
            fixed += 1
            print(f"  FIXED: {ej.parent.name} ({len(old_refs)}→{len(new_refs)} refs)")

    print(f"\n迁移完成：修复 {fixed} 个实体")


if __name__ == "__main__":
    migrate()
