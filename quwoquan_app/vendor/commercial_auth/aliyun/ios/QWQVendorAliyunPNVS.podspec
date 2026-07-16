Pod::Spec.new do |spec|
  spec.name = 'QWQVendorAliyunPNVS'
  spec.version = '0.0.0-controlled'
  spec.summary = '受控构建注入的阿里云号码认证官方 iOS SDK'
  spec.homepage = 'https://help.aliyun.com/zh/pnvs/developer-reference/the-ios-client-access'
  spec.license = { :type => 'Proprietary', :text => 'Alibaba Cloud PNVS official binary distribution.' }
  spec.author = { 'Alibaba Cloud' => 'https://www.aliyun.com/' }
  spec.source = { :path => '.' }
  spec.platform = :ios, '16.0'
  spec.vendored_frameworks = '*.{framework,xcframework}'
  spec.resources = '*.bundle'
end
