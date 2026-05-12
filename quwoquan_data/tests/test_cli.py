from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import yaml
import zlib

from quwoquan_data.tools.native_fetch import fetch_html_page, safe_filename_from_url


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DATA_ROOT = REPO_ROOT / 'quwoquan_data'
CLI_PATH = SOURCE_DATA_ROOT / 'tools' / 'cli.py'
BUILD_SICHUAN_CATALOG_PATH = SOURCE_DATA_ROOT / 'tools' / 'geo' / 'build_sichuan_attractions_catalog.py'
BUILD_GEO_CATALOG_PATH = SOURCE_DATA_ROOT / 'tools' / 'geo' / 'build_geo_poi_catalog.py'
VERIFY_PACKAGES_PATH = REPO_ROOT / 'scripts' / 'verify_quwoquan_data_post_packages.py'
VERIFY_AUTHENTICITY_PATH = REPO_ROOT / 'scripts' / 'verify_quwoquan_data_source_authenticity.py'
VERIFY_GEO_CATALOG_QUALITY_PATH = REPO_ROOT / 'scripts' / 'verify_geo_catalog_quality.py'
VERIFY_CATALOG_ENTITY_CONSISTENCY_PATH = REPO_ROOT / 'scripts' / 'verify_catalog_entity_consistency.py'
SPEC_RELATIVE_PATH = 'runtime/specs/west_lake_discovery_001.yaml'
RUNTIME_SPEC_ID = 'west_lake_discovery_001'
GEO_CONFIG_PATH = REPO_ROOT / 'specs' / 'feature-tree' / 'runtime' / 'runtime-data-engineering' / 'geo-content-trinity' / 'config' / 'geo_catalog_config.sichuan.yaml'
GEO_BAND_RULES_SICHUAN_PATH = GEO_CONFIG_PATH.parent / 'geo_band_rules.sichuan.yaml'


class QwqDataCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tempdir.name) / 'quwoquan_data'
        shutil.copytree(SOURCE_DATA_ROOT, self.data_root)
        self.runtime_root = self.data_root / 'runtime'
        shutil.rmtree(self.runtime_root, ignore_errors=True)
        fixture_root = self.data_root / 'tests' / 'fixtures' / 'runtime_seed'
        for child in ('specs', 'trees'):
            shutil.copytree(
                fixture_root / child,
                self.runtime_root / child,
                dirs_exist_ok=True,
            )
        for child in ('runs', 'publish', 'out', 'downloads'):
            (self.runtime_root / child).mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def env(self) -> dict[str, str]:
        env = os.environ.copy()
        env['QWQ_DATA_ROOT'] = str(self.data_root)
        env['QWQ_RUNTIME_ROOT'] = str(self.runtime_root)
        env['QWQ_REPO_ROOT'] = str(REPO_ROOT)
        return env

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI_PATH), *args],
            cwd=REPO_ROOT,
            env=self.env(),
            text=True,
            capture_output=True,
            check=False,
        )

    def run_package_gate(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VERIFY_PACKAGES_PATH)],
            cwd=REPO_ROOT,
            env=self.env(),
            text=True,
            capture_output=True,
            check=False,
        )

    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=REPO_ROOT,
            env=self.env(),
            text=True,
            capture_output=True,
            check=False,
        )

    def run_auth_gate(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VERIFY_AUTHENTICITY_PATH)],
            cwd=REPO_ROOT,
            env=self.env(),
            text=True,
            capture_output=True,
            check=False,
        )

    def assert_ok(self, result: subprocess.CompletedProcess[str]) -> None:
        if result.returncode != 0:
            self.fail(f'命令失败: stdout={result.stdout}\\nstderr={result.stderr}')

    def read_json(self, path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding='utf-8'))

    def read_yaml(self, path: Path) -> dict[str, object]:
        return yaml.safe_load(path.read_text(encoding='utf-8'))

    def read_ndjson(self, path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        rows: list[dict[str, object]] = []
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def write_ndjson(self, path: Path, rows: list[dict[str, object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows),
            encoding='utf-8',
        )

    def write_yaml(self, path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding='utf-8',
        )

    def spec_path(self) -> Path:
        return self.data_root / SPEC_RELATIVE_PATH

    def runtime_spec_dir(self) -> Path:
        return self.runtime_root / 'runs' / RUNTIME_SPEC_ID

    def topic_dir(self, topic_id: str) -> Path:
        return self.runtime_spec_dir() / 'topics' / topic_id

    def normalization_fixture_path(self, name: str) -> Path:
        return self.data_root / 'tests' / 'fixtures' / 'runtime_seed' / 'normalization' / name

    def write_entity_catalog_seed(self, spec_id: str = 'dual_source_001') -> Path:
        path = self.runtime_root / 'seed' / 'entity_seed.ndjson'
        self.write_ndjson(
            path,
            [
                {
                    'entityId': 'entity_place_west_lake',
                    'canonicalName': '西湖',
                    'entityType': 'scenic_spot',
                    'aliases': ['杭州西湖'],
                    'entityRef': 'trees/entities/地点/西湖.yaml',
                    'tagRefs': ['trees/tags/主题/城市漫游.yaml'],
                    'topicId': 'west_lake_article_001',
                    'extensions': {
                        'coreTokens': ['西湖', '白堤', '断桥'],
                        'wikiTitle': '西湖',
                        'baikeItem': '西湖',
                    },
                }
            ],
        )
        return path

    def build_catalog_row(
        self,
        *,
        topic_id: str,
        name: str,
        entity_type: str = 'scenic_spot',
        entity_type_label_zh: str = '名胜风景区',
        prefecture: str = '成都市',
        district: str = '',
        province: str = '四川省',
        normalized_name: str | None = None,
    ) -> dict[str, object]:
        normalized = normalized_name or name
        return {
            'topic_id': topic_id,
            'name': normalized,
            'raw_name': name,
            'normalized_name': normalized,
            'label_zh': normalized,
            'label_en': '',
            'display_locale': 'zh',
            'entity_type': entity_type,
            'entity_type_label_zh': entity_type_label_zh,
            'wiki_title': normalized,
            'baike_item': normalized,
            'aliases': [],
            'core_tokens': [prefecture.replace('市', ''), district.replace('区', '').replace('县', '')],
            'region': prefecture,
            'province': province,
            'prefecture': prefecture,
            'district': district,
            'expected_region_keywords': [province, prefecture] + ([district] if district else []),
            'tagRefs': ['trees/tags/主题/旅行攻略.yaml'],
            'authority_status': 'pending_check',
            'source_type': 'way',
            'source_id': topic_id,
            'center_lat': 30.0,
            'center_lon': 103.0,
            'ordinal': '',
            'parent_name_hint': '',
            'cluster_hints': [],
        }

    def write_catalog_seed(self, filename: str, rows: list[dict[str, object]]) -> Path:
        path = self.runtime_root / 'seed' / filename
        self.write_ndjson(path, rows)
        return path

    def write_manual_content_seed(self, entity_id: str, topic_id: str) -> Path:
        html_path = self.data_root / 'tests' / 'fixtures' / 'dual_source_page.html'
        html_path.write_text(
            '<html><head><title>西湖白堤亲子慢走攻略</title></head><body><article>'
            '<p>西湖白堤适合亲子慢走，断桥到平湖秋月这段路更容易控制体力，也方便在湖边停下来拍照和休息。</p>'
            '<p>如果把路线放在清晨或傍晚，湖面光线会更柔和，带孩子出门也不容易太晒。走到苏堤口后再决定要不要继续向曲院风荷延伸，会比一开始拉满路线更舒服。</p>'
            '<p>从白堤往里走，断桥、平湖秋月和湖滨一带都能作为补给点。想拍照的人可以把停留点放在断桥附近，想吃饭的人则可以回到湖滨餐厅区域。</p>'
            '<p>这条线最大的好处是节奏稳定，老人和孩子都不容易掉队。带相机的人还可以在断桥、白堤和湖面之间切换取景，形成文章和图片都能用的素材。</p>'
            '<p>如果只是半天时间，建议把重点放在白堤、断桥、平湖秋月这一小圈，留出喝茶和休息的时间，不必把每个景点都挤进一趟行程里。</p>'
            '<p>西湖作为杭州城市漫游里最稳定的实体锚点，适合串联白堤、湖滨、游船和晚饭安排，也适合把沿线风景和亲子体验写成一篇更完整的攻略。</p>'
            '</article></body></html>',
            encoding='utf-8',
        )
        path = self.runtime_root / 'seed' / 'manual_content_seed.ndjson'
        self.write_ndjson(
            path,
            [
                {
                    'postId': 'west_lake_manual_article_001',
                    'entityId': entity_id,
                    'topicId': topic_id,
                    'sourceUrl': html_path.as_uri(),
                    'sourceType': 'manual_seed',
                    'mediaType': 'article',
                    'title': '西湖白堤亲子慢走攻略',
                    'snippet': '围绕西湖白堤、断桥和平湖秋月展开的亲子慢走路线。',
                    'fetchPolicy': 'open_html',
                    'likes': 120,
                    'shares': 18,
                    'comments': 9,
                    'rightsStatus': 'clear',
                    'watermarkStatus': 'clean',
                }
            ],
        )
        return path

    def _png_bytes(self) -> bytes:
        def chunk(tag: bytes, data: bytes) -> bytes:
            return (
                struct.pack('!I', len(data))
                + tag
                + data
                + struct.pack('!I', zlib.crc32(tag + data) & 0xFFFFFFFF)
            )

        width = 256
        height = 256
        scanline = b'\x00' + (b'\x7F\xBF\xFF' * width)
        raw = scanline * height
        return (
            b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('!IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw))
            + chunk(b'IEND', b'')
        )

    def seed_local_image(self, name: str = 'cover.png') -> str:
        png = self._png_bytes()
        image_path = self.data_root / 'tests' / 'fixtures' / name
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(png)
        return image_path.as_uri()

    def seed_local_html_page(self, *, name: str, title: str, paragraphs: list[str], image_urls: list[str] | None = None) -> str:
        image_tags = ''.join(f'<img src="{url}" alt="image-{idx}"/>' for idx, url in enumerate(image_urls or [], start=1))
        html_path = self.data_root / 'tests' / 'fixtures' / name
        html_path.parent.mkdir(parents=True, exist_ok=True)
        body = ''.join(f'<p>{paragraph}</p>' for paragraph in paragraphs)
        html_path.write_text(
            f'<html><head><title>{title}</title></head><body><article>{body}{image_tags}</article></body></html>',
            encoding='utf-8',
        )
        return html_path.as_uri()

    def write_runtime_image(self, relative_path: str) -> None:
        image_path = self.runtime_root / relative_path
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(self._png_bytes())

    def seed_authentic_article_topic(self, topic_id: str = 'west_lake_article_001') -> None:
        topic_dir = self.topic_dir(topic_id)
        shutil.rmtree(topic_dir, ignore_errors=True)
        (topic_dir / 'pages').mkdir(parents=True, exist_ok=True)
        authentic_paragraphs = [
            '杭州春日亲子遛娃的舒适感，往往从白堤这段路开始。断桥往里走，桃柳贴着湖岸铺开，孩子一路都有景可看，大人也不会有赶路的压力。',
            '从白堤到平湖秋月这一段大约四公里，慢走两小时左右更合适。路面平缓，推车和带低龄孩子都比较省力，体力一般的家庭也能把节奏掌握住。',
            '清晨七点前或傍晚前后最适合带孩子走这条线。早一点人少，拍照干净；傍晚则有湖面反光和金色侧光，走累了还能在湖边茶馆休息。',
            '如果住宿安排在西湖湖滨或武林一带，第二天回撤会更从容。先把白堤和临湖步道走完，再决定要不要去龙井村或曲院风荷，不必一开始就把行程拉满。',
            '携程这篇亲子游记里把酒店体验写得很细，从亲子房、前台小点心到文房四宝都提到了。对带孩子出门的人来说，住得舒服往往比景点多打一个卡更重要。',
            '傍晚找饭馆时，楼外楼、知味观这类临湖餐厅的优势很明显，吃饭时就能看到湖景。对亲子出游来说，这种“边歇脚边看景”的体验很容易把一天收住。',
        ]
        base_urls = [
            'https://hk.trip.com/moments/detail/hangzhou-14-143546908/',
            'https://tw.trip.com/moments/detail/hangzhou-14-144391556/',
            'https://my.trip.com/moments/detail/hangzhou-14-143654750/',
            'https://tw.trip.com/moments/detail/hangzhou-14-144806635/',
            'https://gs.ctrip.com/html5/you/travels/14/3948872.html',
        ]
        base_titles = [
            '春日白堤慢走与亲子停留点',
            '沿湖轻松遛娃的半日节奏',
            '住在西湖边后如何安排回撤',
            '亲子拍照机位与傍晚光线',
            '酒店与吃饭如何和步行线衔接',
        ]
        rows: list[dict[str, object]] = []
        for index in range(20):
            source_id = f'{topic_id}_source_{index + 1:03d}'
            url = base_urls[index % len(base_urls)]
            title = base_titles[index % len(base_titles)]
            snippet = authentic_paragraphs[index % len(authentic_paragraphs)]
            row = {
                'candidateId': source_id,
                'sourceId': source_id,
                'topicTitle': '西湖白堤亲子半日慢走实录',
                'query': '杭州西湖 白堤 亲子 半日路线',
                'title': title,
                'sourceUrl': url,
                'domain': url.split('/')[2],
                'platform': url.split('/')[2],
                'snippet': snippet,
                'sourceRole': 'publish_candidate',
                'rightsStatus': 'clear',
                'watermarkStatus': 'clean',
                'duplicateStatus': 'unique',
                'adSignal': False,
                'likes': 620 - index * 11,
                'shares': 112 - index * 3,
                'comments': 68 - index * 2,
                'qualityBreakdown': {
                    'contentCompleteness': 24 if index < 7 else 21,
                    'actionability': 19 if index < 7 else 17,
                    'sourceCredibility': 14 if index < 7 else 12,
                    'freshness': 10 if index < 10 else 8,
                    'richness': 9 if index < 10 else 7,
                    'engagementSignal': 9 if index < 7 else 7,
                    'cleanliness': 9 if index < 10 else 8,
                },
                'taskType': 'article',
            }
            rows.append(row)
            page_dir = topic_dir / 'pages' / source_id
            page_dir.mkdir(parents=True, exist_ok=True)
            page_html = (
                '<html><body><article>'
                f'<h1>{title}</h1>'
                + ''.join(f'<p>{paragraph}</p>' for paragraph in authentic_paragraphs)
                + '</article></body></html>'
            )
            source_md = '\n'.join(
                [
                    '---',
                    f'title: {title}',
                    f'source_url: {url}',
                    'fetched_at: 2026-05-08T18:00:00Z',
                    '---',
                    '',
                    *[paragraph + '\n' for paragraph in authentic_paragraphs],
                ]
            )
            assets: list[dict[str, object]] = []
            if index == 0:
                cover_path = f'downloads/images/{RUNTIME_SPEC_ID}/{topic_id}/{source_id}/cover.png'
                self.write_runtime_image(cover_path)
                assets.append(
                    {
                        'assetId': f'{topic_id}_cover',
                        'kind': 'image',
                        'objectKey': cover_path,
                        'localPath': cover_path,
                        'downloadStatus': 'downloaded',
                        'sourceUrl': url,
                        'caption': '白堤春日封面',
                        'sha256': f'sha256:{topic_id}_cover',
                        'mimeType': 'image/png',
                        'width': 1440,
                        'height': 1080,
                        'license': {'name': 'editorial_clear', 'usage': 'publishable_reference'},
                        'rightsStatus': 'clear',
                        'watermarkStatus': 'clean',
                        'publishEligibility': 'approved',
                        'platform': url.split('/')[2],
                        'sourceCandidateId': source_id,
                        'sourceId': source_id,
                    }
                )
            elif index == 1:
                walk_path = f'downloads/images/{RUNTIME_SPEC_ID}/{topic_id}/{source_id}/walk.png'
                self.write_runtime_image(walk_path)
                assets.append(
                    {
                        'assetId': f'{topic_id}_walk',
                        'kind': 'image',
                        'objectKey': walk_path,
                        'localPath': walk_path,
                        'downloadStatus': 'downloaded',
                        'sourceUrl': url,
                        'caption': '白堤沿湖步道',
                        'sha256': f'sha256:{topic_id}_walk',
                        'mimeType': 'image/png',
                        'width': 1440,
                        'height': 1080,
                        'license': {'name': 'editorial_clear', 'usage': 'publishable_reference'},
                        'rightsStatus': 'clear',
                        'watermarkStatus': 'clean',
                        'publishEligibility': 'approved',
                        'platform': url.split('/')[2],
                        'sourceCandidateId': source_id,
                        'sourceId': source_id,
                    }
                )
            elif index == 2:
                hotel_path = f'downloads/images/{RUNTIME_SPEC_ID}/{topic_id}/{source_id}/hotel.png'
                self.write_runtime_image(hotel_path)
                assets.append(
                    {
                        'assetId': f'{topic_id}_hotel',
                        'kind': 'image',
                        'objectKey': hotel_path,
                        'localPath': hotel_path,
                        'downloadStatus': 'downloaded',
                        'sourceUrl': url,
                        'caption': '湖边住宿回撤点',
                        'sha256': f'sha256:{topic_id}_hotel',
                        'mimeType': 'image/png',
                        'width': 1440,
                        'height': 1080,
                        'license': {'name': 'editorial_clear', 'usage': 'publishable_reference'},
                        'rightsStatus': 'clear',
                        'watermarkStatus': 'clean',
                        'publishEligibility': 'approved',
                        'platform': url.split('/')[2],
                        'sourceCandidateId': source_id,
                        'sourceId': source_id,
                    }
                )
            (page_dir / 'page.html').write_text(page_html, encoding='utf-8')
            (page_dir / 'source.md').write_text(source_md, encoding='utf-8')
            (page_dir / 'asset_manifest.json').write_text(
                json.dumps(
                    {
                        'schemaVersion': 'quwoquan_data.topic_asset_manifest',
                        'specId': RUNTIME_SPEC_ID,
                        'topicId': topic_id,
                        'sourceId': source_id,
                        'taskType': 'article',
                        'assets': assets,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + '\n',
                encoding='utf-8',
            )
        self.write_ndjson(topic_dir / 'source_pool.ndjson', rows)
        self.write_ndjson(
            topic_dir / 'enrichment.ndjson',
            [
                {
                    'schemaVersion': 'quwoquan_data.topic_enrichment',
                    'specId': RUNTIME_SPEC_ID,
                    'topicId': topic_id,
                    'taskType': 'article',
                    'publishReady': True,
                    'title': '西湖白堤亲子半日慢走实录',
                    'summary': '从断桥进白堤、在湖边歇脚、再回到住宿点，这条线更适合带着孩子慢慢走。',
                    'entity_refs': [
                        'trees/entities/地点/西湖.yaml',
                        'trees/entities/住宿/西湖亲子友好酒店.yaml',
                        'trees/entities/本地生活/龙井路咖啡.yaml',
                    ],
                    'tag_refs': [
                        'trees/tags/主题/城市漫游.yaml',
                        'trees/tags/场景/周末一日.yaml',
                        'trees/tags/人群/亲子.yaml',
                        'trees/tags/质量/高置信.yaml',
                    ],
                    'sourceUrls': [str(row['sourceUrl']) for row in rows[:5]],
                    'selectedCandidateIds': [str(row['candidateId']) for row in rows[:7]],
                    'cover_asset_id': f'{topic_id}_cover',
                    'figure_asset_ids': [f'{topic_id}_cover', f'{topic_id}_walk', f'{topic_id}_hotel'],
                    'article_template': 'journal',
                    'article_font_preset': 'clean',
                }
            ],
        )

    def seed_publishable_placeholder_topic(self, topic_id: str = 'west_lake_article_001') -> None:
        topic_dir = self.topic_dir(topic_id)
        page_dir = topic_dir / 'pages' / f'{topic_id}_source_001'
        page_dir.mkdir(parents=True, exist_ok=True)
        self.write_ndjson(
            topic_dir / 'source_pool.ndjson',
            [
                {
                    'candidateId': f'{topic_id}_source_001',
                    'sourceId': f'{topic_id}_source_001',
                    'taskType': 'article',
                    'topicTitle': '占位主题',
                    'query': '杭州西湖 亲子 半日路线',
                    'title': '公开样本 01',
                    'sourceUrl': 'https://mafengwo.cn/i/west-lake-placeholder',
                    'domain': 'mafengwo.cn',
                    'platform': 'mafengwo.cn',
                    'snippet': '占位摘要',
                    'sourceRole': 'publish_candidate',
                    'rightsStatus': 'clear',
                    'watermarkStatus': 'clean',
                    'duplicateStatus': 'unique',
                    'adSignal': False,
                    'likes': 99,
                    'shares': 12,
                    'comments': 4,
                    'qualityBreakdown': {
                        'contentCompleteness': 23,
                        'actionability': 18,
                        'sourceCredibility': 12,
                        'freshness': 9,
                        'richness': 8,
                        'engagementSignal': 8,
                        'cleanliness': 8,
                    },
                }
            ],
        )
        self.write_ndjson(
            topic_dir / 'enrichment.ndjson',
            [
                {
                    'schemaVersion': 'quwoquan_data.topic_enrichment',
                    'specId': RUNTIME_SPEC_ID,
                    'topicId': topic_id,
                    'taskType': 'article',
                    'publishReady': True,
                    'title': '占位主题',
                    'summary': '占位摘要',
                    'selectedCandidateIds': [f'{topic_id}_source_001'],
                }
            ],
        )
        (page_dir / 'page.html').write_text('<html><body>短</body></html>', encoding='utf-8')
        (page_dir / 'source.md').write_text('# 公开样本\n\n太短了。\n', encoding='utf-8')
        (page_dir / 'asset_manifest.json').write_text(
            json.dumps(
                {
                    'schemaVersion': 'quwoquan_data.topic_asset_manifest',
                    'specId': RUNTIME_SPEC_ID,
                    'topicId': topic_id,
                    'sourceId': f'{topic_id}_source_001',
                    'taskType': 'article',
                    'assets': [],
                },
                ensure_ascii=False,
                indent=2,
            )
            + '\n',
            encoding='utf-8',
        )
        self.write_ndjson(
            self.runtime_spec_dir() / 'topic_tasks.ndjson',
            [
                {
                    'schemaVersion': 'quwoquan_data.topic_task',
                    'specId': RUNTIME_SPEC_ID,
                    'topicId': topic_id,
                    'taskType': 'article',
                    'status': 'ready_for_publish',
                    'publishReady': True,
                    'postCount': 0,
                }
            ],
        )

    def test_tree_validate_all_green(self) -> None:
        self.assert_ok(self.run_cli('tree', 'validate', '--tree', 'all'))

    def test_spec_discovery_initializes_runtime_topic_shells(self) -> None:
        self.assert_ok(self.run_cli('crawl', 'spec-discovery', '--spec', str(self.spec_path())))
        discovery = self.read_json(self.runtime_spec_dir() / 'discovery.json')
        topic_tasks = self.read_ndjson(self.runtime_spec_dir() / 'topic_tasks.ndjson')
        self.assertEqual(discovery['articleTopicCount'], 20)
        self.assertEqual(discovery['imageTopicCount'], 1)
        self.assertFalse(discovery['articlePublishFloorMet'])
        self.assertEqual(topic_tasks[0]['candidateCount'], 0)
        self.assertEqual(topic_tasks[0]['status'], 'needs_source_discovery')
        self.assertTrue((self.topic_dir('west_lake_article_001') / 'source_pool.ndjson').exists())
        self.assertTrue((self.topic_dir('west_lake_article_001') / 'enrichment.ndjson').exists())

    def test_fetch_source_hydrates_runtime_topic_from_local_html(self) -> None:
        image_url = self.seed_local_image()
        html_path = self.data_root / 'tests' / 'fixtures' / 'source_page.html'
        html_path.write_text(
            f'<html><head><title>本地西湖图集</title><meta property="og:image" content="{image_url}"></head>'
            '<body><article><p>这是一段足够长的本地测试正文，用来验证 fetch-source 会把 HTML 和正文抽到 runtime 页面目录里。</p>'
            '<p>第二段继续补足长度，并保留图片引用，便于 image 任务写入 asset_manifest。</p></article></body></html>',
            encoding='utf-8',
        )
        result = self.run_cli(
            'crawl',
            'fetch-source',
            '--spec',
            str(self.spec_path()),
            '--topic',
            'west_lake_image_001',
            '--task-type',
            'image',
            '--source-id',
            'west_lake_image_001_source_local',
            '--url',
            html_path.as_uri(),
            '--title',
            '本地西湖图集',
        )
        self.assert_ok(result)
        page_dir = self.topic_dir('west_lake_image_001') / 'pages' / 'west_lake_image_001_source_local'
        self.assertTrue((page_dir / 'page.html').exists())
        self.assertTrue((page_dir / 'source.md').exists())
        manifest = self.read_json(page_dir / 'asset_manifest.json')
        self.assertTrue(manifest['assets'])
        self.assertTrue((self.runtime_root / manifest['assets'][0]['localPath']).exists())
        source_pool = self.read_ndjson(self.topic_dir('west_lake_image_001') / 'source_pool.ndjson')
        self.assertGreater(int(source_pool[0].get('imageQualityScore') or 0), 0)
        self.assertGreater(
            int((source_pool[0].get('imageQualityBreakdown') or {}).get('resolution') or 0),
            0,
        )

    def test_fetch_source_force_refreshes_broken_source_markdown(self) -> None:
        image_url = self.seed_local_image('refresh-cover.png')
        html_path = self.data_root / 'tests' / 'fixtures' / 'refresh_source_page.html'
        html_path.write_text(
            f'<html><head><title>刷新后的西湖图集</title><meta property="og:image" content="{image_url}"></head>'
            '<body><article><p>这是一段足够长的真实正文，用来验证 fetch-source 会覆盖旧的错误 source.md，并保留真实图片下载结果。</p>'
            '<p>第二段补充说明湖面与步行线索，确保抓取后的 source.md 仍然是一份可读正文，而不是损坏的 front matter。</p></article></body></html>',
            encoding='utf-8',
        )
        args = (
            'crawl',
            'fetch-source',
            '--spec',
            str(self.spec_path()),
            '--topic',
            'west_lake_image_001',
            '--task-type',
            'image',
            '--source-id',
            'west_lake_image_001_source_refresh',
            '--url',
            html_path.as_uri(),
            '--title',
            '刷新后的西湖图集',
        )
        self.assert_ok(self.run_cli(*args))
        page_dir = self.topic_dir('west_lake_image_001') / 'pages' / 'west_lake_image_001_source_refresh'
        (page_dir / 'source.md').write_text('---\n\n## title: 已损坏\n', encoding='utf-8')
        self.assert_ok(self.run_cli(*args))
        source_text = (page_dir / 'source.md').read_text(encoding='utf-8')
        self.assertTrue(source_text.startswith('---\ntitle: 刷新后的西湖图集\n'))
        self.assertIn('\n---\n\n', source_text)
        self.assertNotIn('## title:', source_text)
        source_pool = self.read_ndjson(self.topic_dir('west_lake_image_001') / 'source_pool.ndjson')
        matching = [row for row in source_pool if row.get('sourceId') == 'west_lake_image_001_source_refresh']
        self.assertEqual(len(matching), 1)
        self.assertGreater(int(matching[0].get('imageQualityScore') or 0), 0)

    def test_run_topic_fails_without_verified_candidates(self) -> None:
        self.assert_ok(self.run_cli('crawl', 'spec-discovery', '--spec', str(self.spec_path())))
        result = self.run_cli(
            'crawl',
            'run-topic',
            '--spec',
            str(self.spec_path()),
            '--topic',
            'west_lake_article_001',
            '--targets',
            'alpha,gamma',
            '--dry-run',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('source_pool 候选不足', result.stderr)

    def test_authentic_article_topic_can_build_package(self) -> None:
        self.seed_authentic_article_topic()
        self.assert_ok(self.run_cli('crawl', 'spec-discovery', '--spec', str(self.spec_path())))
        self.assert_ok(
            self.run_cli(
                'crawl',
                'run-topic',
                '--spec',
                str(self.spec_path()),
                '--topic',
                'west_lake_article_001',
                '--targets',
                'alpha,gamma',
                '--dry-run',
            )
        )
        post_dir = (
            self.runtime_root
            / 'publish'
            / 'west_lake_article_001'
            / 'posts'
            / 'west_lake_article_001_article_001'
        )
        manifest = self.read_json(post_dir / 'manifest.json')
        review = self.read_json(post_dir / 'review.json')
        article_text = (post_dir / 'article.md').read_text(encoding='utf-8')
        self.assertEqual(manifest['compliance']['overallStatus'], 'approved')
        self.assertEqual(manifest['qualityAudit']['overallStatus'], 'approved')
        self.assertEqual(review['overallStatus'], 'approved')
        self.assertTrue(review['checks']['readerFacingTone']['pass'])
        self.assertIn('白堤和断桥一侧', article_text)
        self.assertNotIn(
            '杭州春日亲子遛娃的舒适感，往往从白堤这段路开始。断桥往里走，桃柳贴着湖岸铺开，孩子一路都有景可看，大人也不会有赶路的压力。',
            article_text,
        )
        self.assertNotIn('为什么这个选题值得写', article_text)
        self.assertTrue(manifest['selectedSourceIds'])
        package_path = manifest['assets'][0]['packagePath']
        self.assertTrue((post_dir / package_path).exists())
        source_pool = self.read_ndjson(self.topic_dir('west_lake_article_001') / 'source_pool.ndjson')
        retained_row = next(
            row for row in source_pool if row.get('selectionDecision') == 'retained'
        )
        self.assertGreater(int(retained_row.get('publishabilityScore') or 0), 0)
        self.assertIn('readerValue', retained_row.get('publishabilityBreakdown') or {})
        self.assertIn('routeSpecificity', retained_row.get('publishabilityBreakdown') or {})
        self.assertIn('factDensity', retained_row.get('publishabilityBreakdown') or {})
        self.assertIn('practicality', retained_row.get('publishabilityBreakdown') or {})
        self.assertIn('narrativePotential', retained_row.get('publishabilityBreakdown') or {})
        self.assertIn('encyclopedicPenalty', retained_row.get('publishabilityBreakdown') or {})
        self.assertEqual(self.run_package_gate().returncode, 0)

    def test_compose_and_audit_topic_emit_role_artifacts(self) -> None:
        self.seed_authentic_article_topic()
        self.assert_ok(self.run_cli('crawl', 'spec-discovery', '--spec', str(self.spec_path())))
        self.assert_ok(
            self.run_cli(
                'crawl',
                'compose-topic',
                '--spec',
                str(self.spec_path()),
                '--topic',
                'west_lake_article_001',
                '--targets',
                'alpha,gamma',
                '--dry-run',
            )
        )
        compose_summary = self.read_json(
            self.topic_dir('west_lake_article_001') / 'compose_summary.json'
        )
        self.assertEqual(compose_summary['role'], 'compose')
        self.assertEqual(compose_summary['overallStatus'], 'composed')
        self.assertTrue(compose_summary['postIds'])
        self.assert_ok(
            self.run_cli(
                'crawl',
                'audit-topic',
                '--spec',
                str(self.spec_path()),
                '--topic',
                'west_lake_article_001',
            )
        )
        audit_summary = self.read_json(
            self.topic_dir('west_lake_article_001') / 'audit_summary.json'
        )
        review = self.read_json(
            self.runtime_root
            / 'publish'
            / 'west_lake_article_001'
            / 'posts'
            / 'west_lake_article_001_article_001'
            / 'review.json'
        )
        self.assertEqual(audit_summary['role'], 'audit')
        self.assertEqual(audit_summary['overallStatus'], 'approved')
        self.assertEqual(review['overallStatus'], 'approved')
        self.assertTrue(review['checks']['factualCoverage']['pass'])
        self.assertTrue(review['checks']['sourceGrounding']['pass'])

    def test_run_topic_auto_prepares_enrichment_for_single_real_source(self) -> None:
        self.seed_authentic_article_topic()
        spec = self.read_yaml(self.spec_path())
        spec['discovery_policy']['min_candidate_sources_per_task'] = 1
        self.write_yaml(self.spec_path(), spec)

        topic_id = 'west_lake_article_001'
        topic_dir = self.topic_dir(topic_id)
        source_pool = self.read_ndjson(topic_dir / 'source_pool.ndjson')
        first_row = source_pool[0]
        self.write_ndjson(topic_dir / 'source_pool.ndjson', [first_row])
        self.write_ndjson(
            topic_dir / 'enrichment.ndjson',
            [
                {
                    'schemaVersion': 'quwoquan_data.topic_enrichment',
                    'specId': RUNTIME_SPEC_ID,
                    'topicId': topic_id,
                    'taskType': 'article',
                    'publishReady': False,
                    'title': 'west lake article 001 文章任务',
                    'summary': '',
                    'entityRefs': [
                        'trees/entities/地点/西湖.yaml',
                        'trees/entities/住宿/西湖亲子友好酒店.yaml',
                        'trees/entities/本地生活/龙井路咖啡.yaml',
                    ],
                    'tagRefs': [
                        'trees/tags/主题/城市漫游.yaml',
                        'trees/tags/场景/周末一日.yaml',
                        'trees/tags/人群/亲子.yaml',
                        'trees/tags/质量/高置信.yaml',
                    ],
                    'selectedCandidateIds': [],
                    'sourceUrls': [],
                }
            ],
        )

        self.assert_ok(
            self.run_cli(
                'crawl',
                'run-topic',
                '--spec',
                str(self.spec_path()),
                '--topic',
                topic_id,
                '--targets',
                'alpha,gamma',
                '--dry-run',
            )
        )
        enrichment = self.read_ndjson(topic_dir / 'enrichment.ndjson')[0]
        self.assertTrue(enrichment['publishReady'])
        self.assertTrue(enrichment['selectedCandidateIds'])
        self.assertTrue(enrichment['sourceUrls'])
        self.assertTrue(enrichment['coverAssetId'])
        self.assertEqual(self.run_package_gate().returncode, 0)

    def test_package_gate_accepts_single_source_real_article(self) -> None:
        self.seed_authentic_article_topic()
        spec = self.read_yaml(self.spec_path())
        spec['discovery_policy']['min_article_topics'] = 1
        spec['discovery_policy']['min_image_topics'] = 1
        spec['discovery_policy']['min_candidate_sources_per_task'] = 1
        spec['discovery_policy']['min_article_publish_topics'] = 1
        spec['discovery_policy']['min_image_publish_topics'] = 0
        self.write_yaml(self.spec_path(), spec)

        topic_dir = self.topic_dir('west_lake_article_001')
        source_pool = self.read_ndjson(topic_dir / 'source_pool.ndjson')
        first_row = source_pool[0]
        self.write_ndjson(topic_dir / 'source_pool.ndjson', [first_row])
        enrichment = self.read_ndjson(topic_dir / 'enrichment.ndjson')[0]
        enrichment['sourceUrls'] = [str(first_row['sourceUrl'])]
        enrichment['selectedCandidateIds'] = [str(first_row['candidateId'])]
        enrichment['figure_asset_ids'] = [str(enrichment['cover_asset_id'])]
        self.write_ndjson(topic_dir / 'enrichment.ndjson', [enrichment])

        self.assert_ok(
            self.run_cli(
                'crawl',
                'run-topic',
                '--spec',
                str(self.spec_path()),
                '--topic',
                'west_lake_article_001',
                '--targets',
                'alpha,gamma',
                '--dry-run',
            )
        )
        gate = self.run_package_gate()
        self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)

    def test_package_gate_rejects_template_article_copy(self) -> None:
        self.seed_authentic_article_topic()
        self.assert_ok(
            self.run_cli(
                'crawl',
                'run-topic',
                '--spec',
                str(self.spec_path()),
                '--topic',
                'west_lake_article_001',
                '--targets',
                'alpha,gamma',
                '--dry-run',
            )
        )
        article_path = (
            self.runtime_root
            / 'publish'
            / 'west_lake_article_001'
            / 'posts'
            / 'west_lake_article_001_article_001'
            / 'article.md'
        )
        article_text = article_path.read_text(encoding='utf-8')
        article_path.write_text(article_text + '\n## 为什么这个选题值得写\n模板文案\n', encoding='utf-8')
        gate = self.run_package_gate()
        self.assertNotEqual(gate.returncode, 0)
        self.assertIn('模板化固定文案', gate.stdout + gate.stderr)

    def test_authenticity_gate_rejects_publishable_placeholder_topic(self) -> None:
        self.seed_publishable_placeholder_topic()
        gate = self.run_auth_gate()
        self.assertNotEqual(gate.returncode, 0)
        self.assertIn('占位 URL', gate.stdout + gate.stderr)

    def test_crawl_spec_discovery_skip_hydrate(self) -> None:
        self.assert_ok(
            self.run_cli(
                'crawl',
                'spec-discovery',
                '--spec',
                str(self.spec_path()),
                '--skip-hydrate',
            )
        )

    def test_crawl_export_poi_topics_writes_ndjson(self) -> None:
        overpass = self.runtime_root / 'seed' / 'overpass_test.json'
        overpass.parent.mkdir(parents=True, exist_ok=True)
        overpass.write_text(
            json.dumps(
                {
                    'elements': [
                        {
                            'type': 'node',
                            'id': 4242,
                            'tags': {'name': '西门测试景点', 'tourism': 'attraction'},
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        out = self.runtime_root / 'seed' / 'poi_topics_out.ndjson'
        self.assert_ok(
            self.run_cli(
                'crawl',
                'export-poi-topics',
                '--input',
                str(overpass),
                '--output',
                str(out),
                '--topic-id-prefix',
                'tpfx',
            )
        )
        rows = self.read_ndjson(out)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['topic_id'], 'tpfx_node_4242')

    def test_build_sichuan_catalog_filters_invalid_names_and_emits_candidate_fields(self) -> None:
        overpass = self.runtime_root / 'seed' / 'sichuan_catalog_input.json'
        overpass.parent.mkdir(parents=True, exist_ok=True)
        overpass.write_text(
            json.dumps(
                {
                    'elements': [
                        {
                            'type': 'way',
                            'id': 299409723,
                            'tags': {
                                'name': '杜甫草堂',
                                'tourism': 'attraction',
                                'addr:city': '成都市',
                                'addr:district': '青羊区',
                            },
                        },
                        {
                            'type': 'node',
                            'id': 9081656149,
                            'tags': {'name': 'I LOVE XHU', 'tourism': 'attraction'},
                        },
                        {
                            'type': 'node',
                            'id': 10090429018,
                            'tags': {'name': '卐', 'tourism': 'attraction'},
                        },
                        {
                            'type': 'node',
                            'id': 8721292664,
                            'tags': {'name': '歼-5', 'historic': 'monument'},
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        out = self.runtime_root / 'seed' / 'sichuan_catalog_out.ndjson'
        result = self.run_script(
            BUILD_SICHUAN_CATALOG_PATH,
            '--inputs',
            str(overpass),
            '--output',
            str(out),
        )
        self.assert_ok(result)
        rows = self.read_ndjson(out)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], '杜甫草堂')
        self.assertEqual(rows[0]['label_zh'], '杜甫草堂')
        self.assertEqual(rows[0]['entity_type_label_zh'], '人文史迹')
        self.assertEqual(rows[0]['tagRefs'], ['trees/tags/主题/旅行攻略.yaml'])

    def test_build_geo_catalog_from_config_emits_slice_report(self) -> None:
        overpass = self.runtime_root / 'seed' / 'generic_catalog_input.json'
        overpass.parent.mkdir(parents=True, exist_ok=True)
        overpass.write_text(
            json.dumps(
                {
                    'elements': [
                        {
                            'type': 'way',
                            'id': 299409723,
                            'tags': {
                                'name': '杜甫草堂',
                                'tourism': 'attraction',
                                'addr:city': '成都市',
                                'addr:district': '青羊区',
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        out = self.runtime_root / 'seed' / 'generic_catalog_out.ndjson'
        report = self.runtime_root / 'out' / 'generic_catalog_slice_report.json'
        result = self.run_script(
            BUILD_GEO_CATALOG_PATH,
            '--config',
            str(GEO_CONFIG_PATH),
            '--inputs',
            str(overpass),
            '--output',
            str(out),
            '--report-out',
            str(report),
        )
        self.assert_ok(result)
        rows = self.read_ndjson(out)
        payload = self.read_json(report)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], '杜甫草堂')
        self.assertEqual(payload['schemaVersion'], 'quwoquan_data.geo_catalog_slice_report')
        self.assertEqual(payload['keptCount'], 1)

    def test_data_build_entities_tags_can_generate_catalog_from_config(self) -> None:
        overpass = self.runtime_root / 'seed' / 'stage_catalog_input.json'
        overpass.parent.mkdir(parents=True, exist_ok=True)
        overpass.write_text(
            json.dumps(
                {
                    'elements': [
                        {
                            'type': 'way',
                            'id': 299409723,
                            'tags': {
                                'name': '杜甫草堂',
                                'tourism': 'attraction',
                                'addr:city': '成都市',
                                'addr:district': '青羊区',
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        out = self.runtime_root / 'seed' / 'sichuan_catalog_stage.ndjson'
        report = self.runtime_root / 'out' / 'sichuan_catalog_stage_report.json'
        result = self.run_cli(
            'data',
            'build-entities-tags',
            '--catalog-config',
            str(GEO_CONFIG_PATH),
            '--catalog-output',
            str(out),
            '--report-out',
            str(report),
            '--catalog-inputs',
            str(overpass),
        )
        self.assert_ok(result)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['stage'], 'data-build-entities-tags')
        built_catalog = self.read_ndjson(out)
        self.assertEqual(built_catalog[0]['name'], '杜甫草堂')
        self.assertEqual(built_catalog[0]['source_type'], 'way')
        self.assertEqual(built_catalog[0]['source_id'], '299409723')
        entity_catalog = self.read_ndjson(self.runtime_root / 'seed' / 'entity_catalog' / 'entities.ndjson')
        self.assertTrue(any(row['canonicalName'] == '杜甫草堂' for row in entity_catalog))

    def test_data_build_entities_tags_semantic_members_materialize_under_root(self) -> None:
        catalog = self.write_catalog_seed(
            'semantic_members_catalog.ndjson',
            [
                self.build_catalog_row(
                    topic_id='poi_panda_base',
                    name='成都大熊猫繁育研究基地',
                    entity_type='leisure_attraction',
                    entity_type_label_zh='休闲景点',
                    district='成华区',
                ),
                self.build_catalog_row(
                    topic_id='poi_panda_villa_2',
                    name='大熊猫2号别墅',
                    entity_type='leisure_attraction',
                    entity_type_label_zh='休闲景点',
                    district='成华区',
                ),
                self.build_catalog_row(
                    topic_id='poi_panda_villa_3',
                    name='大熊猫3号别墅',
                    entity_type='leisure_attraction',
                    entity_type_label_zh='休闲景点',
                    district='成华区',
                ),
                self.build_catalog_row(topic_id='poi_liu_estate', name='刘氏庄园'),
                self.build_catalog_row(
                    topic_id='poi_liu_gc_1',
                    name='刘文彩公馆',
                    entity_type='heritage_site',
                    entity_type_label_zh='人文史迹',
                ),
                self.build_catalog_row(
                    topic_id='poi_liu_gc_2',
                    name='刘文成公馆',
                    entity_type='heritage_site',
                    entity_type_label_zh='人文史迹',
                ),
                self.build_catalog_row(
                    topic_id='poi_jianmen_root',
                    name='剑门关关风景区',
                    normalized_name='剑门关风景区',
                    entity_type='heritage_site',
                    entity_type_label_zh='人文史迹',
                    prefecture='广元市',
                ),
                self.build_catalog_row(
                    topic_id='poi_jianmen_gate',
                    name='剑门关关楼',
                    entity_type='heritage_site',
                    entity_type_label_zh='人文史迹',
                    prefecture='广元市',
                ),
            ],
        )

        self.assert_ok(self.run_cli('data', 'build-entities-tags', '--catalog', str(catalog)))

        entity_catalog = self.read_ndjson(self.runtime_root / 'seed' / 'entity_catalog' / 'entities.ndjson')
        names = {str(row['canonicalName']) for row in entity_catalog}
        self.assertIn('成都大熊猫繁育研究基地', names)
        self.assertIn('刘氏庄园', names)
        self.assertIn('剑门关风景区', names)
        self.assertNotIn('大熊猫2号别墅', names)
        self.assertNotIn('大熊猫3号别墅', names)
        self.assertNotIn('刘文彩公馆', names)
        self.assertNotIn('刘文成公馆', names)
        self.assertNotIn('剑门关关楼', names)

        panda = next(row for row in entity_catalog if row['canonicalName'] == '成都大熊猫繁育研究基地')
        panda_members = {member['nameCanonicalZhHans'] for member in panda['extensions']['members']}
        self.assertEqual(panda_members, {'大熊猫2号别墅', '大熊猫3号别墅'})
        self.assertEqual(panda['extensions']['admissionTrack'], 'authority')

        estate = next(row for row in entity_catalog if row['canonicalName'] == '刘氏庄园')
        estate_members = {member['nameCanonicalZhHans'] for member in estate['extensions']['members']}
        self.assertEqual(estate_members, {'刘文彩公馆', '刘文成公馆'})

        jianmen = next(row for row in entity_catalog if row['canonicalName'] == '剑门关风景区')
        jianmen_members = {member['nameCanonicalZhHans'] for member in jianmen['extensions']['members']}
        self.assertEqual(jianmen_members, {'剑门关关楼'})

        semantic_candidates = self.read_ndjson(
            self.runtime_root / 'seed' / 'entity_catalog' / 'semantic_cluster_candidates.ndjson'
        )
        member_by_topic = {row['topicId']: row for row in semantic_candidates}
        self.assertEqual(member_by_topic['poi_panda_villa_2']['decision'], 'member')
        self.assertEqual(member_by_topic['poi_panda_villa_2']['rootCanonicalName'], '成都大熊猫繁育研究基地')
        self.assertEqual(member_by_topic['poi_jianmen_gate']['rootCanonicalName'], '剑门关风景区')

        self.assert_ok(self.run_script(VERIFY_CATALOG_ENTITY_CONSISTENCY_PATH, '--catalog', str(catalog)))

    def test_data_build_entities_tags_semantic_pending_review_when_parent_missing(self) -> None:
        catalog = self.write_catalog_seed(
            'semantic_pending_catalog.ndjson',
            [
                self.build_catalog_row(
                    topic_id='poi_xjb_1',
                    name='向家坝1号观景台',
                    entity_type='viewpoint',
                    entity_type_label_zh='观景台',
                    prefecture='宜宾市',
                ),
                self.build_catalog_row(
                    topic_id='poi_xjb_2',
                    name='向家坝2号观景台',
                    entity_type='viewpoint',
                    entity_type_label_zh='观景台',
                    prefecture='宜宾市',
                ),
                self.build_catalog_row(
                    topic_id='poi_tj_1',
                    name='同济大学工学院旧址',
                    entity_type='heritage_site',
                    entity_type_label_zh='人文史迹',
                    prefecture='宜宾市',
                ),
                self.build_catalog_row(
                    topic_id='poi_tj_2',
                    name='同济大学理学院(旧址)',
                    entity_type='heritage_site',
                    entity_type_label_zh='人文史迹',
                    prefecture='宜宾市',
                ),
                self.build_catalog_row(
                    topic_id='poi_tj_3',
                    name='国立同济大学医学院旧址',
                    entity_type='heritage_site',
                    entity_type_label_zh='人文史迹',
                    prefecture='宜宾市',
                ),
            ],
        )

        self.assert_ok(self.run_cli('data', 'build-entities-tags', '--catalog', str(catalog)))
        entity_catalog = self.read_ndjson(self.runtime_root / 'seed' / 'entity_catalog' / 'entities.ndjson')
        names = {str(row['canonicalName']) for row in entity_catalog}
        self.assertFalse({'向家坝1号观景台', '向家坝2号观景台'} & names)
        self.assertFalse({'同济大学工学院旧址', '同济大学理学院(旧址)', '国立同济大学医学院旧址'} & names)

        pending_rows = self.read_ndjson(self.runtime_root / 'seed' / 'entity_catalog' / 'semantic_cluster_pending.ndjson')
        pending_ids = {row['topicId'] for row in pending_rows}
        self.assertEqual(
            pending_ids,
            {'poi_xjb_1', 'poi_xjb_2', 'poi_tj_1', 'poi_tj_2', 'poi_tj_3'},
        )
        self.assertTrue(all(row['decision'] == 'pending_review' for row in pending_rows))

        self.assert_ok(self.run_script(VERIFY_CATALOG_ENTITY_CONSISTENCY_PATH, '--catalog', str(catalog)))

    def test_data_build_entities_tags_keeps_single_old_site_as_standalone_without_parent(self) -> None:
        catalog = self.write_catalog_seed(
            'semantic_single_old_site_catalog.ndjson',
            [
                self.build_catalog_row(
                    topic_id='poi_red_army_old_site',
                    name='红三军团驻地旧址',
                    entity_type='heritage_site',
                    entity_type_label_zh='人文史迹',
                    prefecture='泸州市',
                ),
            ],
        )

        self.assert_ok(self.run_cli('data', 'build-entities-tags', '--catalog', str(catalog)))
        entity_catalog = self.read_ndjson(self.runtime_root / 'seed' / 'entity_catalog' / 'entities.ndjson')
        self.assertTrue(any(row['canonicalName'] == '红三军团驻地旧址' for row in entity_catalog))

        semantic_candidates = self.read_ndjson(
            self.runtime_root / 'seed' / 'entity_catalog' / 'semantic_cluster_candidates.ndjson'
        )
        self.assertEqual(semantic_candidates[0]['decision'], 'standalone')
        self.assert_ok(self.run_script(VERIFY_CATALOG_ENTITY_CONSISTENCY_PATH, '--catalog', str(catalog)))

    def test_data_build_entities_tags_semantic_alias_attaches_to_root_entity(self) -> None:
        catalog = self.write_catalog_seed(
            'semantic_alias_catalog.ndjson',
            [
                self.build_catalog_row(
                    topic_id='poi_jianmen_root_primary',
                    name='剑门关风景区',
                    entity_type='heritage_site',
                    entity_type_label_zh='人文史迹',
                    prefecture='广元市',
                ),
                self.build_catalog_row(
                    topic_id='poi_jianmen_root_alias',
                    name='剑门关关风景区',
                    normalized_name='剑门关风景区',
                    entity_type='heritage_site',
                    entity_type_label_zh='人文史迹',
                    prefecture='广元市',
                ),
            ],
        )

        self.assert_ok(self.run_cli('data', 'build-entities-tags', '--catalog', str(catalog)))
        entity_catalog = self.read_ndjson(self.runtime_root / 'seed' / 'entity_catalog' / 'entities.ndjson')
        names = [str(row['canonicalName']) for row in entity_catalog]
        self.assertEqual(names.count('剑门关风景区'), 1)
        root = next(row for row in entity_catalog if row['canonicalName'] == '剑门关风景区')
        self.assertIn('剑门关关风景区', root['aliases'])

        semantic_candidates = self.read_ndjson(
            self.runtime_root / 'seed' / 'entity_catalog' / 'semantic_cluster_candidates.ndjson'
        )
        alias_row = next(row for row in semantic_candidates if row['topicId'] == 'poi_jianmen_root_alias')
        self.assertEqual(alias_row['decision'], 'alias')
        self.assertEqual(alias_row['rootCanonicalName'], '剑门关风景区')
        self.assert_ok(self.run_script(VERIFY_CATALOG_ENTITY_CONSISTENCY_PATH, '--catalog', str(catalog)))

    def test_data_build_entities_tags_parallel_entity_hint_keeps_top_level_entity(self) -> None:
        root = self.build_catalog_row(topic_id='poi_liu_estate_root', name='刘氏庄园')
        parallel = self.build_catalog_row(
            topic_id='poi_liu_parallel_museum',
            name='刘文彩公馆博物馆',
            entity_type='museum_gallery',
            entity_type_label_zh='博物馆美术馆',
        )
        parallel['semantic_decision_hint'] = 'parallel_entity'
        parallel['parallel_of_name'] = '刘氏庄园'
        catalog = self.write_catalog_seed('semantic_parallel_catalog.ndjson', [root, parallel])

        self.assert_ok(self.run_cli('data', 'build-entities-tags', '--catalog', str(catalog)))
        entity_catalog = self.read_ndjson(self.runtime_root / 'seed' / 'entity_catalog' / 'entities.ndjson')
        names = {str(row['canonicalName']) for row in entity_catalog}
        self.assertTrue({'刘氏庄园', '刘文彩公馆博物馆'} <= names)

        semantic_candidates = self.read_ndjson(
            self.runtime_root / 'seed' / 'entity_catalog' / 'semantic_cluster_candidates.ndjson'
        )
        parallel_row = next(row for row in semantic_candidates if row['topicId'] == 'poi_liu_parallel_museum')
        self.assertEqual(parallel_row['decision'], 'parallel_entity')
        self.assertEqual(parallel_row['rootCanonicalName'], '刘氏庄园')
        self.assert_ok(self.run_script(VERIFY_CATALOG_ENTITY_CONSISTENCY_PATH, '--catalog', str(catalog)))

    def test_data_build_entities_tags_preserves_post_evidence_fields(self) -> None:
        row = self.build_catalog_row(
            topic_id='poi_hidden_lake_001',
            name='冷嘎措秘境观景点',
            entity_type='viewpoint',
            entity_type_label_zh='观景台',
            prefecture='甘孜藏族自治州',
        )
        row['admission_track_hint'] = 'post_evidence'
        row['evidence_article_urls'] = [
            'https://example.com/posts/hidden-lake-001',
            'https://travel.example.net/articles/hidden-lake-002',
        ]
        row['evidence_independence_notes'] = ['不同顶级域名互证']
        row['conflict_check_status'] = 'pass'
        row['undeveloped_or_wild_access'] = True
        catalog = self.write_catalog_seed('semantic_post_evidence_catalog.ndjson', [row])

        self.assert_ok(self.run_cli('data', 'build-entities-tags', '--catalog', str(catalog)))
        entity_catalog = self.read_ndjson(self.runtime_root / 'seed' / 'entity_catalog' / 'entities.ndjson')
        entity = next(row for row in entity_catalog if row['canonicalName'] == '冷嘎措秘境观景点')
        self.assertEqual(entity['extensions']['admissionTrack'], 'post_evidence')
        self.assertEqual(
            entity['extensions']['evidenceArticleUrls'],
            [
                'https://example.com/posts/hidden-lake-001',
                'https://travel.example.net/articles/hidden-lake-002',
            ],
        )
        self.assertEqual(entity['extensions']['conflictCheckStatus'], 'pass')
        self.assertTrue(entity['extensions']['undevelopedOrWildAccess'])
        self.assert_ok(self.run_script(VERIFY_CATALOG_ENTITY_CONSISTENCY_PATH, '--catalog', str(catalog)))

    def test_verify_catalog_entity_consistency_rejects_insufficient_post_evidence(self) -> None:
        row = self.build_catalog_row(
            topic_id='poi_hidden_lake_002',
            name='冷嘎措北坡秘境点',
            entity_type='viewpoint',
            entity_type_label_zh='观景台',
            prefecture='甘孜藏族自治州',
        )
        row['admission_track_hint'] = 'post_evidence'
        row['evidence_article_urls'] = ['https://example.com/posts/hidden-lake-only']
        row['conflict_check_status'] = 'pending'
        catalog = self.write_catalog_seed('semantic_post_evidence_fail_catalog.ndjson', [row])

        self.assert_ok(self.run_cli('data', 'build-entities-tags', '--catalog', str(catalog)))
        result = self.run_script(VERIFY_CATALOG_ENTITY_CONSISTENCY_PATH, '--catalog', str(catalog))
        self.assertNotEqual(result.returncode, 0)

    def test_data_build_entities_tags_replaces_stale_rows_on_rebuild(self) -> None:
        stale_entity_path = self.runtime_root / 'seed' / 'entity_catalog' / 'entities.ndjson'
        self.write_ndjson(
            stale_entity_path,
            [
                {
                    'schemaVersion': 'quwoquan_data.entity_catalog',
                    'entityId': 'stale_poi_panda_villa_2',
                    'canonicalName': '大熊猫2号别墅',
                    'entityType': 'leisure_attraction',
                    'authorityProfileRef': '',
                    'aliases': [],
                    'entityRef': '',
                    'tagRefs': [],
                    'topicId': 'poi_panda_villa_2',
                    'source': 'catalog',
                    'extensions': {
                        'labelZh': '大熊猫2号别墅',
                        'rawName': '大熊猫2号别墅',
                        'normalizedName': '大熊猫2号别墅',
                    },
                }
            ],
        )
        catalog = self.write_catalog_seed(
            'semantic_rebuild_round_2.ndjson',
            [
                self.build_catalog_row(
                    topic_id='poi_panda_base',
                    name='成都大熊猫繁育研究基地',
                    entity_type='leisure_attraction',
                    entity_type_label_zh='休闲景点',
                    district='成华区',
                ),
                self.build_catalog_row(
                    topic_id='poi_panda_villa_2',
                    name='大熊猫2号别墅',
                    entity_type='leisure_attraction',
                    entity_type_label_zh='休闲景点',
                    district='成华区',
                ),
            ],
        )
        self.assert_ok(self.run_cli('data', 'build-entities-tags', '--catalog', str(catalog)))
        second_entities = self.read_ndjson(self.runtime_root / 'seed' / 'entity_catalog' / 'entities.ndjson')
        self.assertFalse(any(row['canonicalName'] == '大熊猫2号别墅' for row in second_entities))
        root = next(row for row in second_entities if row['canonicalName'] == '成都大熊猫繁育研究基地')
        members = {member['nameCanonicalZhHans'] for member in root['extensions']['members']}
        self.assertEqual(members, {'大熊猫2号别墅'})

    def test_data_build_entities_tags_preserves_spacing_in_canonical_name(self) -> None:
        catalog = self.write_catalog_seed(
            'semantic_spacing_catalog.ndjson',
            [
                self.build_catalog_row(
                    topic_id='poi_spacing_001',
                    name='8.8 石',
                    entity_type='viewpoint',
                    entity_type_label_zh='观景台',
                    prefecture='甘孜藏族自治州',
                ),
            ],
        )
        self.assert_ok(self.run_cli('data', 'build-entities-tags', '--catalog', str(catalog)))
        entities = self.read_ndjson(self.runtime_root / 'seed' / 'entity_catalog' / 'entities.ndjson')
        self.assertTrue(any(row['canonicalName'] == '8.8 石' for row in entities))
        self.assert_ok(self.run_script(VERIFY_CATALOG_ENTITY_CONSISTENCY_PATH, '--catalog', str(catalog)))

    def test_data_build_entities_tags_parent_hint_keeps_member_path_not_alias(self) -> None:
        root = self.build_catalog_row(
            topic_id='poi_jianmen_root',
            name='剑门关关风景区',
            normalized_name='剑门关风景区',
            entity_type='heritage_site',
            entity_type_label_zh='人文史迹',
            prefecture='广元市',
        )
        member = self.build_catalog_row(
            topic_id='poi_jianmen_gate',
            name='剑门关关楼',
            entity_type='heritage_site',
            entity_type_label_zh='人文史迹',
            prefecture='广元市',
        )
        member['parent_name_hint'] = '剑门关'
        catalog = self.write_catalog_seed('semantic_parent_hint_member.ndjson', [root, member])

        self.assert_ok(self.run_cli('data', 'build-entities-tags', '--catalog', str(catalog)))

        semantic_candidates = self.read_ndjson(
            self.runtime_root / 'seed' / 'entity_catalog' / 'semantic_cluster_candidates.ndjson'
        )
        decision_by_topic = {row['topicId']: row for row in semantic_candidates}
        self.assertEqual(decision_by_topic['poi_jianmen_gate']['decision'], 'member')
        self.assertEqual(decision_by_topic['poi_jianmen_gate']['rootCanonicalName'], '剑门关风景区')

    def test_data_baseline_accepts_aligned_geo_band_rules(self) -> None:
        result = self.run_cli(
            'data',
            'baseline',
            '--catalog-config',
            str(GEO_CONFIG_PATH),
            '--geo-band-rules',
            str(GEO_BAND_RULES_SICHUAN_PATH),
        )
        self.assert_ok(result)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['stage'], 'data-baseline')
        files = payload['files']
        self.assertIn('geoBandRules', files)

    def test_data_baseline_rejects_geo_band_rules_mismatch(self) -> None:
        wrong_band = GEO_CONFIG_PATH.parent / 'entity_naming_rules.yaml'
        result = self.run_cli(
            'data',
            'baseline',
            '--catalog-config',
            str(GEO_CONFIG_PATH),
            '--geo-band-rules',
            str(wrong_band),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('不一致', result.stderr)

    def test_geo_catalog_verify_scripts_pass_on_built_catalog(self) -> None:
        overpass = self.runtime_root / 'seed' / 'verify_catalog_input.json'
        overpass.parent.mkdir(parents=True, exist_ok=True)
        overpass.write_text(
            json.dumps(
                {
                    'elements': [
                        {
                            'type': 'way',
                            'id': 299409723,
                            'tags': {
                                'name': '杜甫草堂',
                                'tourism': 'attraction',
                                'addr:city': '成都市',
                                'addr:district': '青羊区',
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        out = self.runtime_root / 'seed' / 'verify_catalog_out.ndjson'
        report = self.runtime_root / 'out' / 'verify_catalog_report.json'
        self.assert_ok(
            self.run_cli(
                'data',
                'build-entities-tags',
                '--catalog-config',
                str(GEO_CONFIG_PATH),
                '--catalog-output',
                str(out),
                '--report-out',
                str(report),
                '--catalog-inputs',
                str(overpass),
            )
        )
        self.assert_ok(self.run_script(VERIFY_GEO_CATALOG_QUALITY_PATH, '--catalog', str(out), '--report', str(report)))
        self.assert_ok(self.run_script(VERIFY_CATALOG_ENTITY_CONSISTENCY_PATH, '--catalog', str(out)))

    def test_verify_geo_catalog_quality_min_kept_enforced(self) -> None:
        overpass = self.runtime_root / 'seed' / 'verify_min_kept_input.json'
        overpass.parent.mkdir(parents=True, exist_ok=True)
        overpass.write_text(
            json.dumps(
                {
                    'elements': [
                        {
                            'type': 'way',
                            'id': 299409723,
                            'tags': {
                                'name': '杜甫草堂',
                                'tourism': 'attraction',
                                'addr:city': '成都市',
                                'addr:district': '青羊区',
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        out = self.runtime_root / 'seed' / 'verify_min_kept_out.ndjson'
        report = self.runtime_root / 'out' / 'verify_min_kept_report.json'
        self.assert_ok(
            self.run_cli(
                'data',
                'build-entities-tags',
                '--catalog-config',
                str(GEO_CONFIG_PATH),
                '--catalog-output',
                str(out),
                '--report-out',
                str(report),
                '--catalog-inputs',
                str(overpass),
            )
        )
        self.assert_ok(
            self.run_script(
                VERIFY_GEO_CATALOG_QUALITY_PATH,
                '--catalog',
                str(out),
                '--report',
                str(report),
                '--min-kept',
                '1',
                '--min-rows',
                '1',
            )
        )
        too_high = self.run_script(
            VERIFY_GEO_CATALOG_QUALITY_PATH,
            '--catalog',
            str(out),
            '--report',
            str(report),
            '--min-kept',
            '99999',
        )
        self.assertNotEqual(too_high.returncode, 0)

    def test_build_entities_tags_persists_catalog_cluster_hints(self) -> None:
        overpass = self.runtime_root / 'seed' / 'verify_cluster_hints_input.json'
        overpass.parent.mkdir(parents=True, exist_ok=True)
        overpass.write_text(
            json.dumps(
                {
                    'elements': [
                        {
                            'type': 'node',
                            'id': 30001,
                            'lat': 30.123,
                            'lon': 103.456,
                            'tags': {
                                'name': '大熊猫2号别墅',
                                'tourism': 'attraction',
                                'addr:city': '成都市',
                                'addr:district': '成华区',
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        out = self.runtime_root / 'seed' / 'verify_cluster_hints_out.ndjson'
        report = self.runtime_root / 'out' / 'verify_cluster_hints_report.json'
        self.assert_ok(
            self.run_cli(
                'data',
                'build-entities-tags',
                '--catalog-config',
                str(GEO_CONFIG_PATH),
                '--catalog-output',
                str(out),
                '--report-out',
                str(report),
                '--catalog-inputs',
                str(overpass),
            )
        )
        rows = self.read_ndjson(out)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['source_type'], 'node')
        self.assertEqual(row['source_id'], '30001')
        self.assertEqual(row['center_lat'], 30.123)
        self.assertEqual(row['center_lon'], 103.456)
        self.assertEqual(row['ordinal'], '2')
        self.assertEqual(row['parent_name_hint'], '大熊猫')
        self.assertEqual(set(row['cluster_hints']), {'numbered_member', '别墅'})

    def test_build_entities_tags_normalizes_catalog_names_from_geo_builder(self) -> None:
        overpass = self.runtime_root / 'seed' / 'verify_name_normalization_input.json'
        overpass.parent.mkdir(parents=True, exist_ok=True)
        overpass.write_text(
            json.dumps(
                {
                    'elements': [
                        {
                            'type': 'way',
                            'id': 31001,
                            'center': {'lat': 32.1, 'lon': 105.5},
                            'tags': {
                                'name': '剑门关关风景区',
                                'tourism': 'attraction',
                                'addr:city': '广元市',
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        out = self.runtime_root / 'seed' / 'verify_name_normalization_out.ndjson'
        report = self.runtime_root / 'out' / 'verify_name_normalization_report.json'
        self.assert_ok(
            self.run_cli(
                'data',
                'build-entities-tags',
                '--catalog-config',
                str(GEO_CONFIG_PATH),
                '--catalog-output',
                str(out),
                '--report-out',
                str(report),
                '--catalog-inputs',
                str(overpass),
            )
        )
        rows = self.read_ndjson(out)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['raw_name'], '剑门关关风景区')
        self.assertEqual(row['name'], '剑门关风景区')
        self.assertEqual(row['normalized_name'], '剑门关风景区')
        self.assertEqual(row['label_zh'], '剑门关风景区')
        self.assertEqual(row['wiki_title'], '剑门关风景区')
        self.assertEqual(row['baike_item'], '剑门关风景区')

    def test_content_hydrate_respects_topics_filter(self) -> None:
        entity_seed = self.write_entity_catalog_seed()
        manual_seed = self.write_manual_content_seed('entity_place_west_lake', 'west_lake_article_001')
        self.assert_ok(self.run_cli('crawl', 'tag-catalog-build'))
        self.assert_ok(self.run_cli('crawl', 'entity-catalog-build', '--catalog', str(entity_seed)))
        self.assert_ok(
            self.run_cli(
                'crawl',
                'instruction-build',
                '--spec-id',
                'hydrate_topics_filter_001',
                '--instruction',
                '从城市漫游标签出发抓取西湖攻略与图片',
                '--tag-refs',
                'trees/tags/主题/城市漫游.yaml',
                '--verticals',
                'travel',
                '--content-modes',
                'article,image',
            )
        )
        self.assert_ok(
            self.run_cli(
                'crawl',
                'entities-by-tag',
                '--spec-id',
                'hydrate_topics_filter_001',
                '--tag-refs',
                'trees/tags/主题/城市漫游.yaml',
            )
        )
        self.assert_ok(self.run_cli('crawl', 'spec-build', '--spec-id', 'hydrate_topics_filter_001'))
        spec_path = self.runtime_root / 'specs' / 'hydrate_topics_filter_001.yaml'
        self.assert_ok(self.run_cli('crawl', 'authority-sync', '--spec', str(spec_path)))
        self.assert_ok(self.run_cli('crawl', 'content-discover', '--spec', str(spec_path), '--seed', str(manual_seed)))

        miss = self.run_cli('crawl', 'content-hydrate', '--spec', str(spec_path), '--topics', 'nonexistent_topic_xyz')
        self.assert_ok(miss)
        payload = json.loads(miss.stdout.strip())
        self.assertEqual(payload.get('hydrated'), 0)

        hit = self.run_cli('crawl', 'content-hydrate', '--spec', str(spec_path), '--topics', 'west_lake_article_001')
        self.assert_ok(hit)
        payload_hit = json.loads(hit.stdout.strip())
        self.assertGreater(int(payload_hit.get('hydrated') or 0), 0)

    def test_data_build_entities_tags_stage_runs(self) -> None:
        entity_seed = self.write_entity_catalog_seed()
        result = self.run_cli('data', 'build-entities-tags', '--catalog', str(entity_seed))
        self.assert_ok(result)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['stage'], 'data-build-entities-tags')
        tag_catalog = self.read_ndjson(self.runtime_root / 'seed' / 'tag_catalog' / 'tags.ndjson')
        entity_catalog = self.read_ndjson(self.runtime_root / 'seed' / 'entity_catalog' / 'entities.ndjson')
        self.assertTrue(any(row['label'] == '城市漫游' for row in tag_catalog))
        self.assertTrue(any(row['canonicalName'] == '西湖' for row in entity_catalog))

    def test_data_download_stage_runs_dual_source_seed_pipeline(self) -> None:
        entity_seed = self.write_entity_catalog_seed()
        manual_seed = self.write_manual_content_seed('entity_place_west_lake', 'west_lake_article_001')

        self.assert_ok(self.run_cli('data', 'build-entities-tags', '--catalog', str(entity_seed)))
        self.assert_ok(
            self.run_cli(
                'crawl',
                'instruction-build',
                '--spec-id',
                'dual_source_data_001',
                '--instruction',
                '从城市漫游标签出发抓取西湖攻略与图片',
                '--tag-refs',
                'trees/tags/主题/城市漫游.yaml',
                '--verticals',
                'travel',
                '--content-modes',
                'article,image',
            )
        )
        self.assert_ok(
            self.run_cli(
                'crawl',
                'entities-by-tag',
                '--spec-id',
                'dual_source_data_001',
                '--tag-refs',
                'trees/tags/主题/城市漫游.yaml',
            )
        )
        self.assert_ok(self.run_cli('crawl', 'spec-build', '--spec-id', 'dual_source_data_001'))
        spec_path = self.runtime_root / 'specs' / 'dual_source_data_001.yaml'

        self.assert_ok(
            self.run_cli(
                'data',
                'download',
                '--spec',
                str(spec_path),
                '--seed',
                str(manual_seed),
                '--skip-pool-bootstrap',
            )
        )
        content_pool = self.read_ndjson(
            self.runtime_root / 'runs' / 'dual_source_data_001' / 'entities' / 'entity_place_west_lake' / 'content_pool.ndjson'
        )
        self.assertTrue(content_pool)
        hydrated_row = next(
            row for row in content_pool if str(row.get('publishStatus', '')).strip() == 'hydrated'
        )
        page_dir = self.runtime_root / str((hydrated_row.get('extensions') or {}).get('pageDir') or '')
        self.assertTrue((page_dir / 'source.md').exists())

    def test_data_download_stage_supports_fetch_seed(self) -> None:
        self.seed_authentic_article_topic('west_lake_article_001')
        fetch_seed_path = self.runtime_root / 'seed' / 'fetch_seed.ndjson'
        html_path = self.data_root / 'tests' / 'fixtures' / 'dual_source_page.html'
        html_path.write_text(
            '<html><head><title>西湖慢走攻略</title></head><body><article>'
            '<p>西湖慢走适合把白堤、断桥和平湖秋月连成一条轻松路线。</p>'
            '<p>如果只安排半天，可以把节奏放在白堤与湖滨，不必把每个点都挤进去。</p>'
            '<p>这条线适合第一次来杭州，也适合把沿湖停留和吃饭安排写成一篇完整攻略。</p>'
            '</article></body></html>',
            encoding='utf-8',
        )
        self.write_ndjson(
            fetch_seed_path,
            [
                {
                    'topicId': 'west_lake_article_001',
                    'taskType': 'article',
                    'sourceId': 'west_lake_fetch_seed_001',
                    'sourceUrl': html_path.as_uri(),
                    'title': '西湖慢走攻略',
                    'query': '西湖 白堤 慢走',
                    'snippet': '从白堤到湖滨的轻松步行线。',
                }
            ],
        )
        self.assert_ok(
            self.run_cli(
                'data',
                'download',
                '--spec',
                str(self.spec_path()),
                '--fetch-seed',
                str(fetch_seed_path),
                '--skip-authority-sync',
                '--skip-pool-bootstrap',
                '--skip-content-discover',
                '--skip-hydrate',
            )
        )
        pool = self.read_ndjson(self.topic_dir('west_lake_article_001') / 'source_pool.ndjson')
        self.assertTrue(any(row['sourceId'] == 'west_lake_fetch_seed_001' for row in pool))
        self.assertTrue((self.topic_dir('west_lake_article_001') / 'pages' / 'west_lake_fetch_seed_001' / 'source.md').exists())

    def test_data_process_content_and_publish_stage_runs_on_publishable_topic(self) -> None:
        self.seed_authentic_article_topic('west_lake_article_001')
        self.assert_ok(
            self.run_cli(
                'data',
                'process-content',
                '--spec',
                str(self.spec_path()),
                '--topics',
                'west_lake_article_001',
                '--targets',
                'alpha,gamma',
            )
        )
        self.assert_ok(
            self.run_cli(
                'data',
                'publish',
                '--spec',
                str(self.spec_path()),
                '--topics',
                'west_lake_article_001',
            )
        )
        publish_status = self.read_json(
            self.runtime_root / 'runs' / RUNTIME_SPEC_ID / 'topics' / 'west_lake_article_001' / 'publish_status.json'
        )
        self.assertEqual(publish_status['status'], 'published')

    def test_data_build_content_compat_alias_still_works(self) -> None:
        self.seed_authentic_article_topic('west_lake_article_001')
        result = self.run_cli(
            'data',
            'build-content',
            '--spec',
            str(self.spec_path()),
            '--topics',
            'west_lake_article_001',
            '--targets',
            'alpha,gamma',
        )
        self.assert_ok(result)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['stage'], 'data-process-content')

    def test_dual_source_instruction_and_catalog_commands(self) -> None:
        entity_seed = self.write_entity_catalog_seed()
        self.assert_ok(self.run_cli('crawl', 'tag-catalog-build'))
        self.assert_ok(self.run_cli('crawl', 'entity-catalog-build', '--catalog', str(entity_seed)))
        self.assert_ok(
            self.run_cli(
                'crawl',
                'instruction-build',
                '--spec-id',
                'dual_source_001',
                '--instruction',
                '从旅行攻略标签出发发现西湖实体与图文内容',
                '--tag-refs',
                'trees/tags/主题/城市漫游.yaml',
                '--verticals',
                'travel',
                '--content-modes',
                'article,image',
            )
        )
        tag_catalog = self.read_ndjson(self.runtime_root / 'seed' / 'tag_catalog' / 'tags.ndjson')
        entity_catalog = self.read_ndjson(self.runtime_root / 'seed' / 'entity_catalog' / 'entities.ndjson')
        instruction_profile = self.read_json(self.runtime_root / 'runs' / 'dual_source_001' / 'instruction_profile.json')
        self.assertTrue(any(row['label'] == '城市漫游' for row in tag_catalog))
        self.assertTrue(any(row['canonicalName'] == '西湖' for row in entity_catalog))
        self.assertEqual(instruction_profile['specId'], 'dual_source_001')

    def test_entities_by_tag_and_spec_build(self) -> None:
        entity_seed = self.write_entity_catalog_seed()
        self.assert_ok(self.run_cli('crawl', 'tag-catalog-build'))
        self.assert_ok(self.run_cli('crawl', 'entity-catalog-build', '--catalog', str(entity_seed)))
        self.assert_ok(
            self.run_cli(
                'crawl',
                'instruction-build',
                '--spec-id',
                'dual_source_002',
                '--instruction',
                '从城市漫游标签发现旅行实体',
                '--tag-refs',
                'trees/tags/主题/城市漫游.yaml',
            )
        )
        self.assert_ok(
            self.run_cli(
                'crawl',
                'entities-by-tag',
                '--spec-id',
                'dual_source_002',
                '--tag-refs',
                'trees/tags/主题/城市漫游.yaml',
            )
        )
        self.assert_ok(self.run_cli('crawl', 'spec-build', '--spec-id', 'dual_source_002'))
        selected = self.read_ndjson(self.runtime_root / 'runs' / 'dual_source_002' / 'selected_entities.ndjson')
        built_spec = self.read_yaml(self.runtime_root / 'specs' / 'dual_source_002.yaml')
        self.assertTrue(selected)
        self.assertEqual(built_spec['article_topic_catalog_ref'], 'seed/entity_catalog/dual_source_002_topics.ndjson')

    def test_authority_sync_and_content_review_materialize_topic_pool(self) -> None:
        entity_seed = self.write_entity_catalog_seed()
        manual_seed = self.write_manual_content_seed('entity_place_west_lake', 'west_lake_article_001')
        self.assert_ok(self.run_cli('crawl', 'tag-catalog-build'))
        self.assert_ok(self.run_cli('crawl', 'entity-catalog-build', '--catalog', str(entity_seed)))
        self.assert_ok(
            self.run_cli(
                'crawl',
                'instruction-build',
                '--spec-id',
                'dual_source_003',
                '--instruction',
                '从城市漫游标签出发抓取西湖攻略与图片',
                '--tag-refs',
                'trees/tags/主题/城市漫游.yaml',
                '--verticals',
                'travel',
                '--content-modes',
                'article,image',
            )
        )
        self.assert_ok(
            self.run_cli(
                'crawl',
                'entities-by-tag',
                '--spec-id',
                'dual_source_003',
                '--tag-refs',
                'trees/tags/主题/城市漫游.yaml',
            )
        )
        self.assert_ok(self.run_cli('crawl', 'spec-build', '--spec-id', 'dual_source_003'))
        spec_path = self.runtime_root / 'specs' / 'dual_source_003.yaml'
        self.assert_ok(self.run_cli('crawl', 'authority-sync', '--spec', str(spec_path)))
        self.assert_ok(self.run_cli('crawl', 'content-discover', '--spec', str(spec_path), '--seed', str(manual_seed)))
        self.assert_ok(self.run_cli('crawl', 'content-hydrate', '--spec', str(spec_path)))
        self.assert_ok(self.run_cli('crawl', 'content-review', '--spec', str(spec_path)))
        authority_pool = self.read_ndjson(
            self.runtime_root / 'runs' / 'dual_source_003' / 'entities' / 'entity_place_west_lake' / 'authority_pool.ndjson'
        )
        content_pool = self.read_ndjson(
            self.runtime_root / 'runs' / 'dual_source_003' / 'entities' / 'entity_place_west_lake' / 'content_pool.ndjson'
        )
        topic_source_pool = self.read_ndjson(
            self.runtime_root / 'runs' / 'dual_source_003' / 'topics' / 'west_lake_article_001' / 'source_pool.ndjson'
        )
        self.assertTrue(any(row['sourceId'] == 'wikipedia_zh' for row in authority_pool))
        approved_rows = [row for row in content_pool if row.get('reviewStatus') == 'approved']
        self.assertTrue(approved_rows)
        self.assertIn(approved_rows[0]['rewritePolicy'], {'light_edit', 'structured_enrich', 'multi_source_rewrite'})
        self.assertTrue(topic_source_pool)

    def test_content_discover_skips_discovery_only_for_authority_missing_entities(self) -> None:
        catalog_path = self.runtime_root / 'seed' / 'authority_missing_catalog.ndjson'
        self.write_ndjson(
            catalog_path,
            [
                {
                    'entityId': 'entity_place_missing_authority',
                    'name': '西湖',
                    'entityType': 'scenic_spot',
                    'topic_id': 'west_lake_article_001',
                    'tagRefs': ['trees/tags/主题/城市漫游.yaml'],
                    'core_tokens': ['西湖', '白堤'],
                    'wiki_title': '西湖',
                    'baike_item': '西湖',
                    'label_zh': '西湖',
                    'authority_status': 'missing',
                }
            ],
        )
        self.assert_ok(self.run_cli('crawl', 'tag-catalog-build'))
        self.assert_ok(self.run_cli('crawl', 'entity-catalog-build', '--catalog', str(catalog_path)))
        self.assert_ok(
            self.run_cli(
                'crawl',
                'instruction-build',
                '--spec-id',
                'authority_missing_001',
                '--instruction',
                '从城市漫游标签发现西湖攻略',
                '--tag-refs',
                'trees/tags/主题/城市漫游.yaml',
                '--verticals',
                'travel',
                '--content-modes',
                'article,image',
            )
        )
        self.assert_ok(
            self.run_cli(
                'crawl',
                'entities-by-tag',
                '--spec-id',
                'authority_missing_001',
                '--tag-refs',
                'trees/tags/主题/城市漫游.yaml',
            )
        )
        self.assert_ok(self.run_cli('crawl', 'spec-build', '--spec-id', 'authority_missing_001'))
        spec_path = self.runtime_root / 'specs' / 'authority_missing_001.yaml'
        self.assert_ok(self.run_cli('crawl', 'content-discover', '--spec', str(spec_path)))
        pool = self.read_ndjson(
            self.runtime_root / 'runs' / 'authority_missing_001' / 'entities' / 'entity_place_missing_authority' / 'content_pool.ndjson'
        )
        self.assertEqual(pool, [])

    def test_data_source_fetch_writes_normalization_bundle(self) -> None:
        image_url = self.seed_local_image('normalize-cover.png')
        page_url = self.seed_local_html_page(
            name='normalize-source.html',
            title='海螺沟景区游记',
            paragraphs=[
                '海螺沟景区是川西旅行里很稳定的主实体，二号观景台和冰川步道都属于景区内部的游览节点。',
                '正文里用了多张现场照片，适合保留清晰、无水印、能表现冰川和栈道关系的内容图。',
            ],
            image_urls=[image_url],
        )
        result = self.run_cli(
            'data',
            'source-fetch',
            '--batch-label',
            'normalize_batch_001',
            '--source-url',
            page_url,
            '--page-title',
            '海螺沟景区游记',
            '--catalog-topic',
            'poi_test_001',
            '--catalog-name',
            '海螺沟景区',
        )
        self.assert_ok(result)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['stage'], 'data-source-fetch')
        source_ref = payload['outputs']['sourceRef']
        bundle_dir = self.runtime_root / 'runs' / 'normalize_batch_001' / 'normalization' / 'source' / 'bundles' / source_ref
        self.assertTrue((bundle_dir / 'page.html').exists())
        self.assertTrue((bundle_dir / 'page.json').exists())
        self.assertTrue((bundle_dir / 'page.text.txt').exists())
        self.assertTrue((bundle_dir / 'source.md').exists())
        self.assertTrue((bundle_dir / 'source_blocks.ndjson').exists())
        manifest = self.read_json(bundle_dir / 'asset_manifest.json')
        self.assertEqual(len(manifest['assets']), 1)
        self.assertEqual(manifest['assets'][0]['watermarkStatus'], 'unknown')
        self.assertEqual(manifest['assets'][0]['imageTypeCandidate'], 'unknown')
        fetch_input = self.runtime_root / 'runs' / 'normalize_batch_001' / 'normalization' / 'inputs' / 'fetch' / f'{source_ref}.json'
        fetch_result = self.runtime_root / 'runs' / 'normalize_batch_001' / 'normalization' / 'results' / 'fetch' / f'{source_ref}.json'
        self.assertTrue(fetch_input.exists())
        self.assertTrue(fetch_result.exists())

    def test_safe_filename_from_url_truncates_overlong_names(self) -> None:
        url = 'https://example.com/' + ('a' * 260) + '.jpg'
        filename = safe_filename_from_url(url)
        self.assertLessEqual(len(filename), 120)
        self.assertTrue(filename.endswith('.jpg'))

    def test_fetch_html_page_falls_back_to_curl_on_remote_disconnect(self) -> None:
        with mock.patch(
            'quwoquan_data.tools.native_fetch.urllib.request.urlopen',
            side_effect=http.client.RemoteDisconnected('Remote end closed connection without response'),
        ), mock.patch(
            'quwoquan_data.tools.native_fetch._curl_fetch',
            return_value=(
                '<html><head><title>示例标题</title></head><body><p>正文段落</p></body></html>'.encode('utf-8'),
                'https://example.com/final',
                'text/html; charset=utf-8',
            ),
        ) as curl_fetch:
            page = fetch_html_page('https://example.com/original')
        curl_fetch.assert_called_once_with('https://example.com/original')
        self.assertEqual(page.final_url, 'https://example.com/final')
        self.assertEqual(page.title, '示例标题')
        self.assertIn('正文段落', page.text)

    def test_normalize_validate_output_rejects_invalid_extract_result(self) -> None:
        invalid = self.runtime_root / 'runs' / 'normalize_batch_002' / 'normalization' / 'results' / 'extract' / 'bad.json'
        invalid.parent.mkdir(parents=True, exist_ok=True)
        invalid.write_text(
            json.dumps(
                {
                    'schemaVersion': 'quwoquan_data.normalization.source_extraction_result',
                    'sourceRef': 'bad_source',
                    'batchLabel': 'normalize_batch_002',
                    'sourceUrl': 'https://example.com/a',
                    'sourceTitle': '坏结果',
                    'sourceMarkdownPath': '/tmp/source.md',
                    'mainEntityCandidates': [],
                    'memberCandidates': [],
                    'aliasCandidates': [],
                    'imageDecisions': [],
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        result = self.run_cli(
            'data',
            'normalize-validate-output',
            '--stage',
            'extract',
            '--result',
            str(invalid),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('缺少必填字段 extractionStatus', result.stderr)

    def test_normalize_compile_and_materialize_entities(self) -> None:
        image_url = self.seed_local_image('normalize-materialize-cover.png')
        page_url = self.seed_local_html_page(
            name='normalize-materialize-source.html',
            title='海螺沟景区与二号观景台',
            paragraphs=[
                '海螺沟景区是这篇文章的主实体，二号观景台明确属于景区内部观景节点。',
                '文章中的第一张图片是现场冰川和栈道的内容图，可以进入最终长文；带水印或图标图不能引用。',
            ],
            image_urls=[image_url],
        )
        fetch_result = self.run_cli(
            'data',
            'source-fetch',
            '--batch-label',
            'normalize_batch_003',
            '--source-url',
            page_url,
            '--page-title',
            '海螺沟景区与二号观景台',
            '--catalog-topic',
            'poi_test_003',
            '--catalog-name',
            '海螺沟景区',
        )
        self.assert_ok(fetch_result)
        fetch_payload = json.loads(fetch_result.stdout)
        source_ref = fetch_payload['outputs']['sourceRef']
        bundle_dir = self.runtime_root / 'runs' / 'normalize_batch_003' / 'normalization' / 'source' / 'bundles' / source_ref
        asset_manifest = self.read_json(bundle_dir / 'asset_manifest.json')
        asset_row = asset_manifest['assets'][0]

        extract_result = self.runtime_root / 'runs' / 'normalize_batch_003' / 'normalization' / 'results' / 'extract' / f'{source_ref}.json'
        extract_result.parent.mkdir(parents=True, exist_ok=True)
        extract_result.write_text(
            json.dumps(
                {
                    'schemaVersion': 'quwoquan_data.normalization.source_extraction_result',
                    'sourceRef': source_ref,
                    'batchLabel': 'normalize_batch_003',
                    'catalogTopicId': 'poi_test_003',
                    'sourceUrl': page_url,
                    'sourceTitle': '海螺沟景区与二号观景台',
                    'sourceMarkdownPath': str(bundle_dir / 'source.md'),
                    'language': 'zh',
                    'mainEntityCandidates': [
                        {
                            'nameOriginal': '海螺沟景区',
                            'nameCanonicalZhHansCandidate': '海螺沟景区',
                            'entityTypeCandidate': 'natural_scenery',
                            'confidence': 0.96,
                            'evidenceSpans': ['block_0001'],
                            'reasoningSummary': '全文明确以海螺沟景区为主实体。',
                        }
                    ],
                    'memberCandidates': [
                        {
                            'nameOriginal': '二号观景台',
                            'nameCanonicalZhHansCandidate': '二号观景台',
                            'belongsToMainCandidate': '海螺沟景区',
                            'memberRole': '观景台',
                            'ordinal': '2',
                            'evidenceSpans': ['block_0001'],
                            'confidence': 0.91,
                        }
                    ],
                    'aliasCandidates': [
                        {
                            'alias': '螺沟景区',
                            'targetMainCandidate': '海螺沟景区',
                            'aliasType': '曾用别称',
                            'confidence': 0.6,
                            'evidenceSpans': ['block_0001'],
                        }
                    ],
                    'imageDecisions': [
                        {
                            'assetId': asset_row['assetId'],
                            'assetSourceUrl': asset_row['assetSourceUrl'],
                            'assetLocalPath': asset_row['assetLocalPath'],
                            'pageTitle': '海螺沟景区与二号观景台',
                            'imageType': 'content_photo',
                            'usableAsEntityEvidence': True,
                            'depictsEntityCandidates': ['海螺沟景区'],
                            'watermarkStatusCandidate': 'clean',
                            'rightsStatusCandidate': 'clear',
                            'selectionReason': '清晰内容图，可进入长文。',
                            'reasoningSummary': '图中是冰川与栈道场景，不是图标。',
                        }
                    ],
                    'uncertainItems': [],
                    'extractionStatus': 'ready_for_review',
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        self.assert_ok(
            self.run_cli('data', 'normalize-validate-output', '--stage', 'extract', '--result', str(extract_result))
        )

        review_result = self.runtime_root / 'runs' / 'normalize_batch_003' / 'normalization' / 'results' / 'review' / f'{source_ref}.json'
        review_result.parent.mkdir(parents=True, exist_ok=True)
        review_result.write_text(
            json.dumps(
                {
                    'schemaVersion': 'quwoquan_data.normalization.source_review_result',
                    'sourceRef': source_ref,
                    'batchLabel': 'normalize_batch_003',
                    'sourceUrl': page_url,
                    'sourceTitle': '海螺沟景区与二号观景台',
                    'reviewedAt': '2026-05-12T02:00:00Z',
                    'acceptedMainEntities': [
                        {
                            'candidateRef': 'main_001',
                            'canonicalZhHans': '海螺沟景区',
                            'entityType': 'natural_scenery',
                            'summary': '景区主实体。',
                            'evidenceRefs': ['block_0001'],
                        }
                    ],
                    'acceptedMembers': [
                        {
                            'candidateRef': 'member_001',
                            'nameCanonicalZhHans': '二号观景台',
                            'belongsToMainCandidate': '海螺沟景区',
                            'memberRole': '观景台',
                            'ordinal': '2',
                            'evidenceRefs': ['block_0001'],
                        }
                    ],
                    'acceptedAliases': [
                        {
                            'alias': '螺沟景区',
                            'targetMainCandidate': '海螺沟景区',
                            'aliasType': '曾用别称',
                            'evidenceRefs': ['block_0001'],
                        }
                    ],
                    'selectedContentAssets': [
                        {'assetId': asset_row['assetId'], 'selectionReason': '无水印内容图'}
                    ],
                    'rejectedAssets': [],
                    'rejectedItems': [],
                    'conflictFlags': {
                        'parallelNotSubordinate': False,
                        'genericNameWithoutProof': False,
                        'articleOnlyListsStops': False,
                        'cannotInferParentFromText': False,
                    },
                    'needsAuthorityBackcheck': False,
                    'reviewSummary': '主实体和成员关系明确。',
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        self.assert_ok(
            self.run_cli('data', 'normalize-validate-output', '--stage', 'review', '--result', str(review_result))
        )

        authority_result = self.runtime_root / 'runs' / 'normalize_batch_003' / 'normalization' / 'results' / 'authority' / f'{source_ref}.json'
        authority_result.parent.mkdir(parents=True, exist_ok=True)
        authority_result.write_text(
            json.dumps(
                {
                    'schemaVersion': 'quwoquan_data.normalization.authority_backcheck_result',
                    'sourceRef': source_ref,
                    'batchLabel': 'normalize_batch_003',
                    'sourceUrl': page_url,
                    'sourceTitle': '海螺沟景区与二号观景台',
                    'checkedEntities': [
                        {
                            'candidateRef': 'main_001',
                            'authorityMatched': True,
                            'authoritySourceType': 'wikipedia_zh',
                            'authorityUrl': 'https://zh.wikipedia.org/wiki/%E6%B5%B7%E8%9E%BA%E6%B2%9F',
                            'confirmedCanonicalZhHans': '海螺沟景区',
                            'confirmedAliases': ['海螺沟'],
                            'membershipConfirmed': [
                                {'candidateRef': 'member_001', 'nameCanonicalZhHans': '二号观景台'}
                            ],
                            'membershipRejected': [],
                            'authoritySummary': '权威页确认景区名称。',
                        }
                    ],
                    'downgradedItems': [],
                    'authorityBackcheckStatus': 'verified',
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        self.assert_ok(
            self.run_cli('data', 'normalize-validate-output', '--stage', 'authority', '--result', str(authority_result))
        )

        compile_result = self.run_cli(
            'data', 'normalize-compile-entities', '--batch-label', 'normalize_batch_003'
        )
        self.assert_ok(compile_result)
        compiled = self.read_ndjson(
            self.runtime_root / 'runs' / 'normalize_batch_003' / 'normalization' / 'compiled' / 'entity_resolution.ndjson'
        )
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]['mainEntity']['canonicalZhHans'], '海螺沟景区')
        self.assertEqual(compiled[0]['members'][0]['nameCanonicalZhHans'], '二号观景台')
        self.assertEqual(len(compiled[0]['selectedContentAssets']), 1)

        catalog_path = self.runtime_root / 'seed' / 'normalization_catalog.ndjson'
        self.write_ndjson(
            catalog_path,
            [
                {
                    'topic_id': 'poi_test_003',
                    'name': '海螺沟景区',
                    'entity_type': 'natural_scenery',
                    'entity_type_label_zh': '自然景观',
                    'tagRefs': ['trees/tags/主题/旅行攻略.yaml'],
                    'province': '四川省',
                    'prefecture': '甘孜藏族自治州',
                    'district': '泸定县',
                    'raw_name': '海螺沟景区',
                }
            ],
        )
        materialize_result = self.run_cli(
            'data',
            'entity-catalog-materialize',
            '--batch-label',
            'normalize_batch_003',
            '--catalog',
            str(catalog_path),
            '--output-name',
            'normalized_entities.ndjson',
        )
        self.assert_ok(materialize_result)
        entities = self.read_ndjson(self.runtime_root / 'seed' / 'entity_catalog' / 'normalized_entities.ndjson')
        self.assertEqual(entities[0]['canonicalName'], '海螺沟景区')
        self.assertEqual(entities[0]['extensions']['members'][0]['nameCanonicalZhHans'], '二号观景台')
        self.assertEqual(len(entities[0]['extensions']['selectedContentAssets']), 1)

    def test_normalize_compile_supports_panda_villa_member_example(self) -> None:
        batch = 'normalize_batch_panda'
        source_ref = 'local__panda__001'
        extract_dir = self.runtime_root / 'runs' / batch / 'normalization' / 'results' / 'extract'
        review_dir = self.runtime_root / 'runs' / batch / 'normalization' / 'results' / 'review'
        authority_dir = self.runtime_root / 'runs' / batch / 'normalization' / 'results' / 'authority'
        extract_dir.mkdir(parents=True, exist_ok=True)
        review_dir.mkdir(parents=True, exist_ok=True)
        authority_dir.mkdir(parents=True, exist_ok=True)
        (extract_dir / f'{source_ref}.json').write_text(
            json.dumps(
                {
                    'schemaVersion': 'quwoquan_data.normalization.source_extraction_result',
                    'sourceRef': source_ref,
                    'batchLabel': batch,
                    'catalogTopicId': 'poi_panda_villa_002',
                    'sourceUrl': 'https://example.com/panda-villa',
                    'sourceTitle': '基地里的大熊猫2号别墅',
                    'sourceMarkdownPath': '/tmp/panda.md',
                    'language': 'zh',
                    'mainEntityCandidates': [{'nameOriginal': '成都大熊猫繁育研究基地', 'nameCanonicalZhHansCandidate': '成都大熊猫繁育研究基地', 'entityTypeCandidate': 'leisure_attraction', 'confidence': 0.95}],
                    'memberCandidates': [{'nameOriginal': '大熊猫2号别墅', 'nameCanonicalZhHansCandidate': '大熊猫2号别墅', 'belongsToMainCandidate': '成都大熊猫繁育研究基地', 'memberRole': '别墅', 'ordinal': '2', 'confidence': 0.91}],
                    'aliasCandidates': [],
                    'imageDecisions': [],
                    'uncertainItems': [],
                    'extractionStatus': 'ready_for_review',
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        (review_dir / f'{source_ref}.json').write_text(
            json.dumps(
                {
                    'schemaVersion': 'quwoquan_data.normalization.source_review_result',
                    'sourceRef': source_ref,
                    'batchLabel': batch,
                    'sourceUrl': 'https://example.com/panda-villa',
                    'sourceTitle': '基地里的大熊猫2号别墅',
                    'reviewedAt': '2026-05-12T02:20:00Z',
                    'acceptedMainEntities': [{'candidateRef': 'main_panda', 'canonicalZhHans': '成都大熊猫繁育研究基地', 'entityType': 'leisure_attraction'}],
                    'acceptedMembers': [{'candidateRef': 'member_panda_002', 'nameCanonicalZhHans': '大熊猫2号别墅', 'belongsToMainCandidate': '成都大熊猫繁育研究基地', 'memberRole': '别墅', 'ordinal': '2', 'evidenceRefs': ['body']}],
                    'acceptedAliases': [],
                    'selectedContentAssets': [],
                    'rejectedAssets': [],
                    'rejectedItems': [],
                    'conflictFlags': {'parallelNotSubordinate': False, 'genericNameWithoutProof': False, 'articleOnlyListsStops': False, 'cannotInferParentFromText': False},
                    'needsAuthorityBackcheck': False,
                    'reviewSummary': '明确为基地主实体下成员。',
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        (authority_dir / f'{source_ref}.json').write_text(
            json.dumps(
                {
                    'schemaVersion': 'quwoquan_data.normalization.authority_backcheck_result',
                    'sourceRef': source_ref,
                    'batchLabel': batch,
                    'sourceUrl': 'https://example.com/panda-villa',
                    'sourceTitle': '基地里的大熊猫2号别墅',
                    'checkedEntities': [{'candidateRef': 'main_panda', 'authorityMatched': True, 'authoritySourceType': 'baidu_baike', 'authorityUrl': 'https://baike.baidu.com/item/%E6%88%90%E9%83%BD%E5%A4%A7%E7%86%8A%E7%8C%AB%E7%B9%81%E8%82%B2%E7%A0%94%E7%A9%B6%E5%9F%BA%E5%9C%B0', 'confirmedCanonicalZhHans': '成都大熊猫繁育研究基地', 'confirmedAliases': [], 'membershipConfirmed': [{'candidateRef': 'member_panda_002', 'nameCanonicalZhHans': '大熊猫2号别墅'}], 'membershipRejected': [], 'authoritySummary': '基地权威页确认其内部设施。'}],
                    'downgradedItems': [],
                    'authorityBackcheckStatus': 'verified',
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        self.assert_ok(self.run_cli('data', 'normalize-compile-entities', '--batch-label', batch))
        rows = self.read_ndjson(self.runtime_root / 'runs' / batch / 'normalization' / 'compiled' / 'entity_resolution.ndjson')
        self.assertEqual(rows[0]['mainEntity']['canonicalZhHans'], '成都大熊猫繁育研究基地')
        self.assertEqual(rows[0]['members'][0]['nameCanonicalZhHans'], '大熊猫2号别墅')

    def test_normalize_compile_keeps_red_army_site_as_standalone_when_no_parent_evidence(self) -> None:
        batch = 'normalize_batch_red_army'
        source_ref = 'local__red_army__001'
        extract_dir = self.runtime_root / 'runs' / batch / 'normalization' / 'results' / 'extract'
        review_dir = self.runtime_root / 'runs' / batch / 'normalization' / 'results' / 'review'
        authority_dir = self.runtime_root / 'runs' / batch / 'normalization' / 'results' / 'authority'
        extract_dir.mkdir(parents=True, exist_ok=True)
        review_dir.mkdir(parents=True, exist_ok=True)
        authority_dir.mkdir(parents=True, exist_ok=True)
        (extract_dir / f'{source_ref}.json').write_text(
            json.dumps(
                {
                    'schemaVersion': 'quwoquan_data.normalization.source_extraction_result',
                    'sourceRef': source_ref,
                    'batchLabel': batch,
                    'catalogTopicId': 'poi_red_army_003',
                    'sourceUrl': 'https://example.com/red-army-site',
                    'sourceTitle': '红三军团驻地旧址简介',
                    'sourceMarkdownPath': '/tmp/red-army.md',
                    'language': 'zh',
                    'mainEntityCandidates': [{'nameOriginal': '红三军团驻地旧址', 'nameCanonicalZhHansCandidate': '红三军团驻地旧址', 'entityTypeCandidate': 'heritage_site', 'confidence': 0.9}],
                    'memberCandidates': [],
                    'aliasCandidates': [],
                    'imageDecisions': [],
                    'uncertainItems': [],
                    'extractionStatus': 'ready_for_review',
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        (review_dir / f'{source_ref}.json').write_text(
            json.dumps(
                {
                    'schemaVersion': 'quwoquan_data.normalization.source_review_result',
                    'sourceRef': source_ref,
                    'batchLabel': batch,
                    'sourceUrl': 'https://example.com/red-army-site',
                    'sourceTitle': '红三军团驻地旧址简介',
                    'reviewedAt': '2026-05-12T02:30:00Z',
                    'acceptedMainEntities': [{'candidateRef': 'main_red', 'canonicalZhHans': '红三军团驻地旧址', 'entityType': 'heritage_site'}],
                    'acceptedMembers': [],
                    'acceptedAliases': [],
                    'selectedContentAssets': [],
                    'rejectedAssets': [],
                    'rejectedItems': [],
                    'conflictFlags': {'parallelNotSubordinate': True, 'genericNameWithoutProof': False, 'articleOnlyListsStops': False, 'cannotInferParentFromText': True},
                    'needsAuthorityBackcheck': True,
                    'reviewSummary': '未发现足够证据证明其属于更高层主实体。',
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        (authority_dir / f'{source_ref}.json').write_text(
            json.dumps(
                {
                    'schemaVersion': 'quwoquan_data.normalization.authority_backcheck_result',
                    'sourceRef': source_ref,
                    'batchLabel': batch,
                    'sourceUrl': 'https://example.com/red-army-site',
                    'sourceTitle': '红三军团驻地旧址简介',
                    'checkedEntities': [{'candidateRef': 'main_red', 'authorityMatched': True, 'authoritySourceType': 'official_site', 'authorityUrl': 'https://example.com/red-army-site', 'confirmedCanonicalZhHans': '红三军团驻地旧址', 'confirmedAliases': [], 'membershipConfirmed': [], 'membershipRejected': [], 'authoritySummary': '仅确认旧址本体，不确认更高父实体。'}],
                    'downgradedItems': [],
                    'authorityBackcheckStatus': 'verified',
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        self.assert_ok(self.run_cli('data', 'normalize-compile-entities', '--batch-label', batch))
        rows = self.read_ndjson(self.runtime_root / 'runs' / batch / 'normalization' / 'compiled' / 'entity_resolution.ndjson')
        self.assertEqual(rows[0]['mainEntity']['canonicalZhHans'], '红三军团驻地旧址')
        self.assertEqual(rows[0]['members'], [])

    def test_authority_review_rejects_generic_name_without_title_and_region_match(self) -> None:
        entity_catalog = self.runtime_root / 'seed' / 'entity_catalog' / 'entities.ndjson'
        self.write_ndjson(
            entity_catalog,
            [
                {
                    'schemaVersion': 'quwoquan_data.entity_catalog',
                    'entityId': 'entity_generic_spot',
                    'canonicalName': '景点',
                    'entityType': 'viewpoint',
                    'aliases': [],
                    'tagRefs': ['trees/tags/主题/旅行攻略.yaml'],
                    'topicId': 'poi_generic_001',
                    'source': 'catalog',
                    'extensions': {
                        'province': '四川省',
                        'prefecture': '甘孜藏族自治州',
                        'expectedRegionKeywords': ['四川省', '甘孜藏族自治州', '川西'],
                    },
                }
            ],
        )
        page_url = self.seed_local_html_page(
            name='generic-authority.html',
            title='川西旅行攻略',
            paragraphs=[
                '这是一篇普通的川西旅行攻略，没有明确的景点主标题，也没有把景点作为权威实体介绍。',
                '正文只是泛泛而谈，并没有说明某个编号观景台或景点属于什么官方主实体。',
            ],
        )
        authority_pool = self.runtime_root / 'runs' / 'generic_authority_001' / 'entities' / 'entity_generic_spot' / 'authority_pool.ndjson'
        self.write_ndjson(
            authority_pool,
            [
                {
                    'schemaVersion': 'quwoquan_data.authority_profile',
                    'entityId': 'entity_generic_spot',
                    'topicId': 'poi_generic_001',
                    'sourceId': 'wikipedia_zh',
                    'domain': 'example.com',
                    'sourceRole': 'authority_definition',
                    'fetchPolicy': 'open_html',
                    'sourceType': 'authority',
                    'sourceUrl': page_url,
                    'titleHint': '景点',
                    'status': 'discovered',
                }
            ],
        )
        result = self.run_cli('crawl', 'authority-review', '--spec-id', 'generic_authority_001')
        self.assert_ok(result)
        entities = self.read_ndjson(entity_catalog)
        self.assertEqual(entities[0]['extensions']['authorityStatus'], 'missing')


if __name__ == '__main__':
    unittest.main()
