import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';

/// Mock 侧共享主页种子（强类型，与 `fields.yaml` / [HomepageDetail.fromMap] 字段一致）。
/// 运行时应通过 [cloneHomepageSeeds] 深拷贝后再写入 [MockHomepageRepository]，避免与静态表共享嵌套引用。
class HomepageMockData {
  const HomepageMockData._();

  static List<HomepageDetail> cloneHomepageSeeds() {
    return homepageDetailTemplates
        .map(_deepCloneHomepageDetail)
        .toList(growable: true);
  }

  /// 只读模板（勿直接变异；用于测试取首条等场景）。
  static final List<HomepageDetail> homepageDetailTemplates = <HomepageDetail>[
    _westLakeDetail,
    _bambooInnDetail,
    _nightMarketDetail,
    _vehicleCandidateDetail,
  ];

  static final HomepageDetail _westLakeDetail = HomepageDetail(
    id: 'homepage_sight_west_lake',
    homepageType: 'sight',
    title: '西湖景区',
    subtitle: '杭州西湖核心游览区',
    coverUrl:
        'https://images.unsplash.com/photo-1506744038136-46273834b3fb',
    status: 'published',
    sourceType: 'official_seed',
    claimStatus: 'unclaimed',
    categoryTags: const <String>['景点', '城市地标', '赏景'],
    address: '浙江省杭州市西湖区',
    city: '杭州',
    location: HomepageGeoPoint(latitude: 30.2431, longitude: 120.1500),
    averageRating: 4.7,
    ratingCount: 328,
    reviewSummary: HomepageReviewSummaryData(
      averageRating: 4.7,
      ratingCount: 328,
      highlightTags: const <String>['景色开阔', '适合散步', '拍照出片'],
      dimensionScores: <HomepageReviewDimensionScore>[
        HomepageReviewDimensionScore(label: '景观', score: 4.9),
        HomepageReviewDimensionScore(label: '交通', score: 4.5),
        HomepageReviewDimensionScore(label: '拥挤度', score: 4.2),
      ],
    ),
    contentPreview: <HomepageContentPreview>[
      HomepageContentPreview(
        postId: 'west_lake_post_1',
        title: '西湖日落散步路线',
        summary: '一条适合黄昏慢走的完整打卡笔记。',
        contentType: 'article',
        coverUrl:
            'https://images.unsplash.com/photo-1506744038136-46273834b3fb',
      ),
      HomepageContentPreview(
        postId: 'west_lake_post_2',
        title: '断桥边的夜色作品',
        summary: '把作品、笔记、提问统一沉淀到同一个主页。',
        contentType: 'image',
        coverUrl:
            'https://images.unsplash.com/photo-1506744038136-46273834b3fb',
      ),
    ],
    questionPreview: <HomepageQuestionPreview>[
      HomepageQuestionPreview(
        postId: 'west_lake_question_1',
        title: '第一次去西湖建议从哪里开始逛？',
        summary: '主页可以直接聚合相关提问。',
      ),
    ],
    relatedGroups: <HomepageRelatedGroupSummary>[
      HomepageRelatedGroupSummary(
        circleId: 'west_lake_circle_1',
        name: '西湖散步同好群',
        memberCount: 146,
        linkedHomepageId: 'homepage_sight_west_lake',
        linkedHomepageTitle: '西湖景区',
      ),
    ],
    createdAt: _dt('2026-03-20T10:00:00.000Z'),
    updatedAt: _dt('2026-03-24T08:30:00.000Z'),
    publishedAt: _dt('2026-03-21T10:00:00.000Z'),
  );

  static final HomepageDetail _bambooInnDetail = HomepageDetail(
    id: 'homepage_hotel_bamboo_inn',
    homepageType: 'hotel',
    title: '竹隐民宿',
    subtitle: '近景区山景庭院房',
    coverUrl:
        'https://images.unsplash.com/photo-1505693416388-ac5ce068fe85',
    status: 'published',
    sourceType: 'owner_created',
    claimStatus: 'claimed',
    categoryTags: const <String>['民宿', '山景', '亲子'],
    address: '浙江省杭州市西湖区龙井路 18 号',
    city: '杭州',
    location: HomepageGeoPoint(latitude: 30.2250, longitude: 120.1160),
    ownerUserId: 'owner_bamboo',
    averageRating: 4.5,
    ratingCount: 96,
    reviewSummary: HomepageReviewSummaryData(
      averageRating: 4.5,
      ratingCount: 96,
      highlightTags: const <String>['安静', '早餐好评', '老板热情'],
      dimensionScores: <HomepageReviewDimensionScore>[
        HomepageReviewDimensionScore(label: '环境', score: 4.7),
        HomepageReviewDimensionScore(label: '服务', score: 4.6),
        HomepageReviewDimensionScore(label: '交通', score: 4.1),
      ],
    ),
    contentPreview: <HomepageContentPreview>[
      HomepageContentPreview(
        postId: 'bamboo_inn_post_1',
        title: '竹隐民宿入住体验',
        summary: '适合两晚慢住，安静度很高。',
        contentType: 'article',
        coverUrl:
            'https://images.unsplash.com/photo-1505693416388-ac5ce068fe85',
      ),
    ],
    questionPreview: <HomepageQuestionPreview>[
      HomepageQuestionPreview(
        postId: 'bamboo_inn_question_1',
        title: '家庭出游适合订哪种房型？',
        summary: '问答和内容在同一主页上下文里收敛。',
      ),
    ],
    relatedGroups: <HomepageRelatedGroupSummary>[
      HomepageRelatedGroupSummary(
        circleId: 'bamboo_inn_circle_1',
        name: '杭州民宿体验交流',
        memberCount: 82,
        linkedHomepageId: 'homepage_hotel_bamboo_inn',
        linkedHomepageTitle: '竹隐民宿',
      ),
    ],
    createdAt: _dt('2026-03-18T10:00:00.000Z'),
    updatedAt: _dt('2026-03-24T09:00:00.000Z'),
    publishedAt: _dt('2026-03-19T10:00:00.000Z'),
  );

  static final HomepageDetail _nightMarketDetail = HomepageDetail(
    id: 'homepage_restaurant_night_market',
    homepageType: 'restaurant',
    title: '夜巷小馆',
    subtitle: '本地人常去的深夜小馆',
    coverUrl:
        'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4',
    status: 'published',
    sourceType: 'imported',
    claimStatus: 'unclaimed',
    categoryTags: const <String>['餐厅', '夜宵', '本地推荐'],
    address: '浙江省杭州市上城区河坊街 66 号',
    city: '杭州',
    location: HomepageGeoPoint(latitude: 30.2486, longitude: 120.1709),
    averageRating: 4.8,
    ratingCount: 157,
    reviewSummary: HomepageReviewSummaryData(
      averageRating: 4.8,
      ratingCount: 157,
      highlightTags: const <String>['出餐快', '夜宵友好', '小份菜丰富'],
      dimensionScores: <HomepageReviewDimensionScore>[
        HomepageReviewDimensionScore(label: '口味', score: 4.9),
        HomepageReviewDimensionScore(label: '价格', score: 4.6),
        HomepageReviewDimensionScore(label: '环境', score: 4.2),
      ],
    ),
    contentPreview: <HomepageContentPreview>[
      HomepageContentPreview(
        postId: 'night_market_post_1',
        title: '夜巷小馆隐藏菜单',
        summary: '一份完整的深夜小馆推荐笔记。',
        contentType: 'article',
        coverUrl:
            'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4',
      ),
    ],
    questionPreview: <HomepageQuestionPreview>[
      HomepageQuestionPreview(
        postId: 'night_market_question_1',
        title: '第一次去夜巷小馆应该点什么？',
        summary: '支持围绕主页沉淀真实问答。',
      ),
    ],
    relatedGroups: <HomepageRelatedGroupSummary>[
      HomepageRelatedGroupSummary(
        circleId: 'night_market_circle_1',
        name: '杭州夜宵地图',
        memberCount: 203,
        linkedHomepageId: 'homepage_restaurant_night_market',
        linkedHomepageTitle: '夜巷小馆',
      ),
    ],
    createdAt: _dt('2026-03-16T10:00:00.000Z'),
    updatedAt: _dt('2026-03-24T09:30:00.000Z'),
    publishedAt: _dt('2026-03-17T10:00:00.000Z'),
  );

  static final HomepageDetail _vehicleCandidateDetail = HomepageDetail(
    id: 'homepage_vehicle_modelx_candidate',
    homepageType: 'vehicle',
    title: 'Model X 2026 款',
    subtitle: '纯电中大型 SUV 候选主页',
    coverUrl:
        'https://images.unsplash.com/photo-1494976388531-d1058494cdd8',
    status: 'candidate',
    sourceType: 'user_suggested',
    claimStatus: 'unclaimed',
    categoryTags: const <String>['汽车', '新能源'],
    city: '上海',
    createdAt: _dt('2026-03-24T04:00:00.000Z'),
    updatedAt: _dt('2026-03-24T04:00:00.000Z'),
  );
}

DateTime _dt(String iso) => DateTime.parse(iso).toUtc();

HomepageDetail _deepCloneHomepageDetail(HomepageDetail h) {
  final rs = h.reviewSummary;
  return h.copyWith(
    categoryTags: List<String>.from(h.categoryTags),
    reviewSummary: rs == null
        ? null
        : HomepageReviewSummaryData(
            averageRating: rs.averageRating,
            ratingCount: rs.ratingCount,
            highlightTags: List<String>.from(rs.highlightTags),
            dimensionScores:
                List<HomepageReviewDimensionScore>.from(rs.dimensionScores),
          ),
    contentPreview: List<HomepageContentPreview>.from(h.contentPreview),
    questionPreview: List<HomepageQuestionPreview>.from(h.questionPreview),
    relatedGroups:
        List<HomepageRelatedGroupSummary>.from(h.relatedGroups),
  );
}
