# Apple App Store Connect Reports MCP Server

将 App Store Connect 报告 API 转为 MCP 协议，支持 stdio 和 HTTP 两种传输方式。自动解析 gzipped TSV 报告为结构化 JSON，并提供收入聚合、安装统计等高级工具。

另外也支持**本地历史报表目录**：因为 App Store Connect 报表 API 只能获取约 1 年内的数据，你可以把更早的报表归档到本地目录，再通过同一组 MCP 工具读取。

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

# 可选：本地历史报表根目录（示例占位符，需自行改成真实路径）
APP_STORE_REPORT_LOCAL_DIR=/path/to/apple-reports
```

注意：这里的 `/path/to/apple-reports` 只是示例占位符，不会自动创建，也不会自动生效；如果你要启用本地历史报表读取，必须在 `.env` 或运行环境中自行配置成真实路径。

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
        "APP_STORE_CONNECT_VENDOR_NUMBER": "12345678",
        "APP_STORE_REPORT_LOCAL_DIR": "/path/to/apple-reports"
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

## 本地历史报表

### 适用场景

Apple 报表 API 有时间窗口限制。对于更早的数据，可以把历史报表放在本地目录中，然后在工具调用时传入 `source="local"` 或 `source="auto"`。

- `source="api"`：强制走 Apple API
- `source="local"`：强制走本地目录，不命中就报错
- `source="auto"`：优先查本地目录，找不到再回退到 Apple API

如果你只想读取本地历史报表，可以只配置 `APP_STORE_REPORT_LOCAL_DIR`，并在调用时报 `source="local"`。

再次说明：`APP_STORE_REPORT_LOCAL_DIR=/path/to/apple-reports` 只是文档示例，不是默认值，需要你自己替换成真实目录。

### 推荐目录结构

程序会递归扫描本地目录，并根据**报表类型 / 子类型 / 频率 / 日期 / 区域 / vendor number**做匹配。当前实现会优先适配你这类实际归档顶层目录：`financial`、`financial_extended`、`sales`、`subscriptions_event`。

推荐按下面方式组织：

```text
/path/to/apple-reports/
  financial/
    2024-03_ZZ.tsv.gz
  financial_extended/
    2024-03_ZZ_detailed.tsv.gz
  sales/
    summary/daily/2024-04-08.tsv.gz
    subscriber/daily/2024-04-08.tsv.gz
    S_D_12345678_20240408.gz
    appstore_transformed_sales_summary_20240421.csv
  subscriptions_event/
    daily/2024-04-08.tsv.gz
    2024-04-08_subscription_event.tsv.gz
```

其中：
- `financial` / `financial_extended` 会优先用于 `get_finance_report`
- `sales` 会优先用于 sales / revenue / installs，以及部分 subscription 类报表
- `subscriptions_event` 会优先用于 `SUBSCRIPTION_EVENT` 报表

支持的本地文件后缀：
- `.gz`
- `.gzip`
- `.tsv`
- `.txt`
- `.csv`

如果同一个请求匹配到多个本地文件，工具会直接报错，避免静默读错数据。

日期过滤同时兼容 `2024-04-21`、`2024_04_21`、`20240421` 这几种命名形式，便于匹配类似 `appstore_transformed_sales_summary_20240421.csv` 的归档文件。

对于本地 transformed CSV，表头同时兼容 Apple 原始格式（例如 `Provider Country`）和去空格/去分隔符格式（例如 `ProviderCountry`、`ProductTypeIdentifier`）。

原始报表工具的**输出字段**也已统一成 transformed/local 表头风格：
- `get_sales_report` 返回 `ProviderCountry`、`ProductTypeIdentifier`、`DeveloperProceeds`、`CountryCode`、`SupportedPlatforms` 这类字段
- `get_subscription_report` 返回 `AppName`、`SubscriptionAppleID`、`DeveloperProceeds`、`CustomerCurrency` 这类字段
- 这个输出约定对 `source="api"` 和 `source="local"` 都一致
- 仅原始报表工具对外使用这套表头；聚合工具（例如 `get_revenue_summary`、`get_install_stats`）内部仍使用规范化后的字段做计算

如果你想先确认本地目录里有哪些历史文件可被发现，可以调用 `list_local_reports`。这个工具只读取 `APP_STORE_REPORT_LOCAL_DIR`，不访问 Apple API，也不需要 API 凭证；但前提是你必须先把该环境变量配置成真实目录。

### 关键实现文件

- `src/apple_mcp/report_source.py`：本地目录扫描、日期匹配、local/api/auto 路由
- `src/apple_mcp/parsers.py`：Apple 原始表头 / 本地 transformed 表头兼容解析，以及原始报表输出表头格式化
- `src/apple_mcp/tools/sales.py`：sales 原始报表读取；对外返回 transformed/local 风格表头
- `src/apple_mcp/tools/subscriptions.py`：subscription 原始报表读取；对外返回 transformed/local 风格表头
- `src/apple_mcp/server.py`：MCP 工具注册与参数定义

## MCP 工具

| 工具 | 用途 |
|------|------|
| `get_revenue_summary` | 每日收入聚合，按 app/国家/设备分组，支持 `source` |
| `get_install_stats` | 安装统计，区分新装/更新/重下载，支持 `source` |
| `get_sales_report` | 原始销售报告（SUMMARY/SUBSCRIPTION 等），支持 `source`，返回 transformed/local 风格表头 |
| `get_subscription_report` | 订阅状态与事件报告，支持 `source`，返回 transformed/local 风格表头 |
| `get_finance_report` | 按地区的财务结算报告，支持 `source` |
| `list_local_reports` | 列出 `APP_STORE_REPORT_LOCAL_DIR` 下可用的本地历史报表文件 |
| `get_customer_reviews` | 用户评论，支持评分过滤和排序 |

### 示例

```json
{
  "tool": "get_revenue_summary",
  "arguments": {
    "date": "2024-04-08",
    "group_by": "app",
    "source": "local"
  }
}
```

```json
{
  "tool": "get_finance_report",
  "arguments": {
    "report_date": "2024-03",
    "region_code": "ZZ",
    "source": "auto"
  }
}
```

```json
{
  "tool": "get_sales_report",
  "arguments": {
    "report_date": "2024-04-21",
    "report_sub_type": "SUMMARY",
    "date_type": "DAILY",
    "source": "local"
  }
}
```

`get_sales_report` 返回的字段名会统一成 transformed/local 风格，例如 `ProviderCountry`、`ProductTypeIdentifier`、`DeveloperProceeds`、`CountryCode`。

```json
{
  "tool": "get_subscription_report",
  "arguments": {
    "report_date": "2024-04-21",
    "report_type": "SUBSCRIPTION",
    "report_sub_type": "SUMMARY",
    "date_type": "DAILY",
    "source": "api"
  }
}
```

`get_subscription_report` 返回的字段名也会统一成 transformed/local 风格，例如 `AppName`、`SubscriptionAppleID`、`CustomerPrice`、`DeveloperProceeds`。

```json
{
  "tool": "list_local_reports",
  "arguments": {
    "report_type": "FINANCIAL",
    "report_date_prefix": "2024-03",
    "max_results": 20
  }
}
```

## 注意事项

- 每日报告通常在次日 **太平洋时间上午 8 点**后可用
- API 速率限制：3600 次/小时
- 销售和财务报告不可变，已自动缓存避免重复请求
- 本地报表缓存会绑定文件路径、修改时间和大小，文件更新后会自动失效
- 私钥 `.p8` 文件已在 `.gitignore` 中排除，不会被提交
