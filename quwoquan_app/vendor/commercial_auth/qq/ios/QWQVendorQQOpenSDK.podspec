Pod::Spec.new do |spec|
  spec.name = 'QWQVendorQQOpenSDK'
  spec.version = '3.6.20'
  spec.summary = '趣我圈固定的 QQ 官方 iOS OpenSDK 二进制'
  spec.homepage = 'https://wiki.connect.qq.com/sdk%E4%B8%8B%E8%BD%BD'
  spec.license = { :type => 'Proprietary', :text => 'Tencent QQ OpenSDK official binary distribution.' }
  spec.author = { 'Tencent' => 'https://open.qq.com/' }
  spec.source = { :http => 'https://tangram-1251316161.file.myqcloud.com/files/20260402/725f52c913f9bdc7c41bee57d2923c05.zip' }
  spec.platform = :ios, '16.0'
  spec.vendored_frameworks = 'TencentOpenAPI.xcframework'
  spec.frameworks = 'SystemConfiguration', 'Security', 'CoreTelephony'
  spec.libraries = 'c++', 'sqlite3', 'z'
end
