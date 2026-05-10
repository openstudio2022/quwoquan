from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import yaml
import zlib


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DATA_ROOT = REPO_ROOT / 'quwoquan_data'
CLI_PATH = SOURCE_DATA_ROOT / 'tools' / 'cli.py'
VERIFY_PACKAGES_PATH = REPO_ROOT / 'scripts' / 'verify_quwoquan_data_post_packages.py'
VERIFY_AUTHENTICITY_PATH = REPO_ROOT / 'scripts' / 'verify_quwoquan_data_source_authenticity.py'
SPEC_RELATIVE_PATH = 'runtime/specs/west_lake_discovery_001.yaml'
RUNTIME_SPEC_ID = 'west_lake_discovery_001'


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


if __name__ == '__main__':
    unittest.main()
