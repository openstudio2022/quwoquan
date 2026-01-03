# 脚本目录

本目录包含项目自动化脚本。

## 📁 文件说明

### sync_figma.js
Node.js版本的Figma设计令牌同步脚本。

**依赖**:
- Node.js >= 14.0.0
- dotenv包

**使用方法**:
```bash
npm install
npm run sync:figma
```

### sync_figma.py
Python版本的Figma设计令牌同步脚本。

**依赖**:
- Python >= 3.7
- requests包
- python-dotenv包

**使用方法**:
```bash
pip install requests python-dotenv
python3 scripts/sync_figma.py
```

## 🔧 配置

所有脚本都需要在项目根目录的 `.env` 文件中配置：

```bash
FIGMA_ACCESS_TOKEN=your_token
FIGMA_FILE_KEY=your_file_key
```

详细配置说明请参考 [FIGMA_SYNC_README.md](../FIGMA_SYNC_README.md)

