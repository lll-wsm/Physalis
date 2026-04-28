# X.com 登录用户名循环问题记录（2026-04-28）

## 现象

- 在内置 `BrowserWindow` 打开 `x.com` 登录。
- 输入用户名并点击下一步后，未进入密码输入页。
- 页面回到用户名输入步骤（并非密码错误后的失败页）。

## 影响范围

- 主要影响内置 Qt WebEngine 的 X 登录多步向导（`/i/flow/`）。
- 系统浏览器（Chrome/Safari）通常不复现，说明与嵌入式 WebEngine 兼容性/脚本干预有关。

## 根因分析

本次是多个因素叠加，核心是“登录向导状态被重置”而非“账号密码错误”：

1. **注入脚本过重，干扰页面状态机**
   - 之前在 `ui/browser_window.py` 中全局包装了 `fetch` 和 `XMLHttpRequest`。
   - 对 X 这类复杂登录前端，额外包装和重复监听可能导致请求处理链行为变化，引发向导从“密码步骤”回退到“用户名步骤”。

2. **弹窗自动关闭条件过宽**
   - 原逻辑只要 popup 导航到 `x.com`/`twitter.com` 就关闭并 `reload` 主窗口。
   - 当 popup 仍在 `/i/flow/` 登录流程中时会被误关，触发主页面刷新，打断步骤状态。

3. **Profile 存储路径未显式设置**
   - 复杂登录依赖 Cookie + LocalStorage/IndexedDB。
   - 未固定持久化路径时，状态稳定性较差，易出现流程重置。

## 修复内容

位于 `ui/browser_window.py`：

1. **精简注入脚本为最小兼容集**
   - 保留：`navigator.webdriver` 兼容处理。
   - 保留：FedCM `navigator.credentials.get` 对 `identity` 请求的降级。
   - 移除：`fetch`/`XMLHttpRequest`/`window.open` 调试包装与网络监控注入。

2. **收紧 popup 关闭策略**
   - 新增 `_x_popup_landing_finishes_oauth(url)`。
   - 对 `/i/flow/` 和 `/login` 路径不自动关闭 popup，不触发主窗口 reload。
   - 仅在更像“OAuth 完成落地页”时才关闭 popup 并刷新主窗口。

3. **启用 WebEngine 持久化目录**
   - `QWebEngineProfile` 增加 `setPersistentStoragePath()` 与 `setCachePath()`。
   - 目录落在应用配置目录下的 `webengine/` 子目录。

4. **移除硬编码 UA**
   - 不再伪装固定 Chrome 版本，改用 Qt WebEngine 默认 UA，减少版本/特征不一致风险。

## 验证结果

- 场景：`x.com` 登录输入用户名后点击下一步。
- 结果：不再回到用户名输入页，可继续进入下一登录步骤。

## 后续注意事项

- 对登录站点尽量避免“重写原生网络 API（fetch/XHR）”这类强侵入注入。
- 任何 popup 自动关闭逻辑都应限定到明确完成态，避免对流程页（如 `/i/flow/`）误触发。
- 如后续仍遇到站点风控，可使用系统浏览器登录后导入/复用 Cookie 作为兜底方案。
