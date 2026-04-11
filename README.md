# Apple App Store Connect Reports MCP Server

将 App Store Connect 报告 API 转为 MCP 协议，支持 stdio 和 HTTP 两种传输方式。自动解析 gzipped TSV 报告为结构化 JSON，并提供收入聚合、安装统计等高级工具。

## 获取 App Store Connect API 凭证

### 1. 创建 API 密钥

1. 登录 [App Store Connect](https://appstoreconnect.apple.com/)
2. 进入 **用户和访问** → **集成** → **App Store Connect API**
3. 点击 **生成 API 密钥**（需要 Admin 角色）
4. 输入名称，选择访问权限为 **Admin**（报告和财务接口需要此权限）
5. 点击 **生成**

生成后你会得到：
- **Issuer ID** — 页面顶部显示，格式为 UUID（所有密钥共享同一个）
- **Key ID** — 密钥列表中显示，如 `ABC1234DEF`

### 2. 下载私钥文件

- 点击密钥旁的 **下载 API 密钥**，保存 `.p8` 文件
- **注意：私钥只能下载一次**，妥善保管
- 文件名格式：`AuthKey_<KeyID>.p8`

### 3. 获取 Vendor Number

1. 进入 **App Store Connect** → **销售和趋势**
2. Vendor Number 显示在页面右上角，或者：
3. 进入 **协议、税务和银行业务** 页面，Vendor Number 显示在顶部

### 4. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 填入你的凭证：

```env
APP_STORE_CONNECT_ISSUER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
APP_STORE_CONNECT_KEY_ID=ABC1234DEF
APP_STORE_CONNECT_PRIVATE_KEY_PATH=/path/to/AuthKey_ABC1234DEF.p8
APP_STORE_CONNECT_VENDOR_NUMBER=12345678
```

## 安装

```bash
uv sync
```

## 使用

### stdio 模式（Claude Desktop / Claude Code 本地使用）

```bash
uv run python -m apple_mcp
```

Claude Desktop 配置 (`claude_desktop_config.json`)：

```json
{
  "mcpServers": {
    "apple-reports": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/apple-mcp", "python", "-m", "apple_mcp"],
      "env": {
        "APP_STORE_CONNECT_ISSUER_ID": "xxx",
        "APP_STORE_CONNECT_KEY_ID": "xxx",
        "APP_STORE_CONNECT_PRIVATE_KEY_PATH": "/path/to/AuthKey.p8",
        "APP_STORE_CONNECT_VENDOR_NUMBER": "12345678"
      }
    }
  }
}
```

### HTTP 模式（服务端部署，远程访问）

服务端：凭证配置在 `.env` 文件中

```bash
uv run python -m apple_mcp --http --port 3000
```

客户端：Claude Desktop 只需配置 URL

```json
{
  "mcpServers": {
    "apple-reports": {
      "url": "http://your-server:3000/mcp"
    }
  }
}
```

可选参数：
- `--port 3000` — 监听端口（默认 3000）
- `--host 127.0.0.1` — 绑定地址（HTTP 模式默认 0.0.0.0）

## MCP 工具

| 工具 | 用途 |
|------|------|
| `get_revenue_summary` | 每日收入聚合，按 app/国家/设备分组 |
| `get_install_stats` | 安装统计，区分新装/更新/重下载 |
| `get_sales_report` | 原始销售报告（SUMMARY/SUBSCRIPTION 等） |
| `get_subscription_report` | 订阅状态与事件报告 |
| `get_finance_report` | 按地区的财务结算报告 |
| `get_customer_reviews` | 用户评论，支持评分过滤和排序 |

## 注意事项

- 每日报告通常在次日 **太平洋时间上午 8 点**后可用
- API 速率限制：3600 次/小时
- 销售和财务报告不可变，已自动缓存避免重复请求
- 私钥 `.p8` 文件已在 `.gitignore` 中排除，不会被提交
