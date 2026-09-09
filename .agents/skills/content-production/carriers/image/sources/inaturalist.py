"""自然观察按 observation 分组，保留所有照片及逐图许可。"""
import json
from urllib.parse import urlencode


def fetch(request, client):
    query = {"place_id": request["placeId"], "photos": "true", "per_page": 100, "page": int(request.get("page", 1))}
    if request.get("taxonId"):
        query["taxon_id"] = request["taxonId"]
    return client.get("https://api.inaturalist.org/v1/observations?" + urlencode(query))


def parse(body, request):
    rows = []
    for observation in json.loads(body).get("results", []):
        assets = []
        for photo in observation.get("photos", []):
            url = photo.get("url") or ""
            if not url.startswith("https://"):
                continue
            asset = {"id": f"inaturalist:photo:{photo['id']}", "directUrl": url.replace("/square.", "/original."), "previewUrl": url}
            if photo.get("license_code"):
                asset["license"] = photo["license_code"]
            if photo.get("attribution"):
                asset["description"] = photo["attribution"]
            assets.append(asset)
        if not assets:
            continue
        row = {"id": f"inaturalist:{observation['id']}", "kind": "image", "source": "inaturalist",
               "sourceUrl": observation.get("uri") or f"https://www.inaturalist.org/observations/{observation['id']}",
               "title": observation.get("species_guess") or observation.get("place_guess") or "", "assets": assets}
        # 观察者不一定是照片作者；保留逐图 attribution，由宿主核实署名。
        rows.append(row)
    return rows, {}
