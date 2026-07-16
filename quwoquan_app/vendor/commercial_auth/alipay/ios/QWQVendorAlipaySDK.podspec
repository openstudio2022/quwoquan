Pod::Spec.new do |spec|
  spec.name = 'QWQVendorAlipaySDK'
  spec.version = '15.8.40.1'
  spec.summary = '趣我圈固定的支付宝官方 iOS XCFramework'
  spec.homepage = 'https://opendocs.alipay.com/common/02km9l'
  spec.license = { :type => 'Proprietary', :text => 'Alipay official SDK binary distribution.' }
  spec.author = { 'Alipay' => 'https://open.alipay.com/' }
  spec.source = { :http => 'https://mdn.alipayobjects.com/portal_mdssth/afts/file/A*XwdvTYbfKEYAAAAAgGAAAAgAAQAAAQ/AlipaySDK-XCFramework-15.8.40.1.zip' }
  spec.platform = :ios, '16.0'
  spec.vendored_frameworks = 'AlipaySDK.xcframework'
  spec.resources = 'AlipaySDK.bundle'
end
