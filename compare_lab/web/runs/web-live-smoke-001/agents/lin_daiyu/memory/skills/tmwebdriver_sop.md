# 浏览器接管之术：TMWebDriver

这门术是我在新世界里最常借的一样器物：  
不是另起一只干净浏览器，而是借现成的 Chrome 会话、登录态、Cookie、标签页去行事。

## 先明白它是什么

- 直接通过 `web_scan / web_execute_js` 去用
- 底层是 `../TMWebDriver.py` 接管用户浏览器
- 不是 Selenium，也不是 Playwright

## 通用脾气

- `web_execute_js` 里若用了 `await`，必须 **显式 `return`**
- `web_scan` 可自动穿透同源 iframe
- 跨域 iframe 往往要换 CDP 或 `postMessage`

## 最常见的拦路石

- `isTrusted=false`：某些敏感操作会被前端嫌弃
- JS 点击打不开新标签：常是弹窗被拦，改走 CDP
- 文件上传不能靠 JS 直接塞 `<input type=file>`
- 需要物理坐标时，别忘了 `screenX/screenY`、`dpr`、`chromeH`

## 导航

- `web_scan` 只看当前页，不替你跳转
- 真要换站点，常用 `web_execute_js + location.href=...`

## 几个常用场景

### 图搜

- class 名会变，别硬写
- 常靠 `[role=button]`
- 取大图时，常按 `naturalWidth` 最大者来

### 下载 PDF

可用 `fetch(...).then(r=>r.blob())` 再造 `a.download` 去点。  
若跨域不应，先看同源/CORS 是否肯放行。

### 后台标签节流

- 后台标签里的 `setTimeout` 可能被 Chrome 大幅延迟
- 某些 SPA 必须 `Page.bringToFront` 才肯继续加载

## CDP 桥：较稳的一条路

扩展在 `assets/tmwd_cdp_bridge/`。  
若普通 JS 法不肯应，优先改走：

- `cookies`
- `tabs`
- `cdp`
- `batch`

### batch 的好处

- 一次请求走多步
- 可复用同一 session
- 适合上传文件、串联多个 DOM/CDP 操作

但要记住：

- 前序命令若败，后续 `$N.path` 引用会空
- `tabId` 不写就默认当前注入页

## 点击之术

一般点击要三段：

1. `mouseMoved`
2. `mousePressed`
3. `mouseReleased`

少一段，某些组件就像没被真正碰到。

## 心法

- 这门术不怕麻烦，怕偷懒。
- 一见 WebDriver 不应，就别死拽同一路；该换 CDP，便换 CDP。
