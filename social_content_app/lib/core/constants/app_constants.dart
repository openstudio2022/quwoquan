class AppConstants {
  // 应用信息
  static const String appName = '趣我圈';
  static const String appVersion = '1.0.0';
  static const String appDescription = '社交及内容创造综合应用';
  
  // API配置
  static const String baseUrl = 'https://api.quwoquan.com';
  static const String apiVersion = '/v1';
  static const int connectTimeout = 30000;
  static const int receiveTimeout = 30000;
  
  // 存储键名
  static const String tokenKey = 'auth_token';
  static const String userInfoKey = 'user_info';
  static const String themeKey = 'theme_mode';
  static const String languageKey = 'language';
  static const String firstLaunchKey = 'first_launch';
  
  // 分页配置
  static const int defaultPageSize = 20;
  static const int maxPageSize = 100;
  
  // 文件上传配置
  static const int maxImageSize = 10 * 1024 * 1024; // 10MB
  static const int maxVideoSize = 100 * 1024 * 1024; // 100MB
  static const List<String> allowedImageTypes = ['jpg', 'jpeg', 'png', 'gif', 'webp'];
  static const List<String> allowedVideoTypes = ['mp4', 'mov', 'avi', 'mkv'];
  
  // 社交功能配置
  static const int maxPostLength = 2000;
  static const int maxCommentLength = 500;
  static const int maxBioLength = 160;
  static const int maxUsernameLength = 20;
  
  // 缓存配置
  static const int imageCacheMaxAge = 7 * 24 * 60 * 60; // 7天
  static const int userCacheMaxAge = 24 * 60 * 60; // 1天
  
  // 动画配置
  static const Duration defaultAnimationDuration = Duration(milliseconds: 300);
  static const Duration fastAnimationDuration = Duration(milliseconds: 150);
  static const Duration slowAnimationDuration = Duration(milliseconds: 500);
  
  // 正则表达式
  static const String emailRegex = r'^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$';
  static const String phoneRegex = r'^1[3-9]\d{9}$';
  static const String usernameRegex = r'^[a-zA-Z0-9_]{3,20}$';
  
  // 平台标识
  static const String androidPlatform = 'android';
  static const String iosPlatform = 'ios';
  static const String webPlatform = 'web';
  
  // 错误代码
  static const int successCode = 200;
  static const int unauthorizedCode = 401;
  static const int forbiddenCode = 403;
  static const int notFoundCode = 404;
  static const int serverErrorCode = 500;
  
  // 内容类型
  static const String contentTypeText = 'text';
  static const String contentTypeImage = 'image';
  static const String contentTypeVideo = 'video';
  static const String contentTypeAudio = 'audio';
  static const String contentTypeLink = 'link';
  
  // 用户状态
  static const String userStatusActive = 'active';
  static const String userStatusInactive = 'inactive';
  static const String userStatusBanned = 'banned';
  
  // 隐私设置
  static const String privacyPublic = 'public';
  static const String privacyFriends = 'friends';
  static const String privacyPrivate = 'private';
}

