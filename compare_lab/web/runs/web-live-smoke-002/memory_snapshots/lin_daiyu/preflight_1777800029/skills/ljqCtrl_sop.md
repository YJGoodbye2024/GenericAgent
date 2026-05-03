# 鼠键与坐标之术：`ljqCtrl`

这一门术管的是物理鼠标、点击、按键与找图。  
它最易叫人出错的，不是 API 名字，而是 **逻辑坐标与物理坐标混用**。

## 先记一句

凡要用 `ljqCtrl`，先在 checkpoint 里记下：  
`ljqCtrl 一律用物理坐标｜禁 pyautogui｜操作前先激活窗口`

## 常用接口

- `ljqCtrl.dpi_scale`
- `ljqCtrl.SetCursorPos((x, y))`
- `ljqCtrl.Click((x, y))` 或 `Click(x, y)`
- `ljqCtrl.Press('ctrl+c')`
- `ljqCtrl.FindBlock(...)`
- `ljqCtrl.MouseDClick()`

## 起手载入

```python
import sys, pygetwindow as gw
sys.path.append("../memory/skills")
import ljqCtrl
```

## 核心关节：坐标换算

`ljqCtrl` 接的坐标是 **物理像素**。  
若坐标来自 `pygetwindow` 一类窗口工具，多半先拿到的是 **逻辑坐标**，必须换算。

- 公式：`物理坐标 = 逻辑坐标 / ljqCtrl.dpi_scale`

## 标准做法

1. 先 `getWindowsWithTitle(...)`
2. `restore()` / `activate()`
3. 算窗口内点位
4. 把逻辑坐标除以 `dpi_scale`
5. 再 `Click`

```python
win = gw.getWindowsWithTitle('微信')[0]
px = lx / ljqCtrl.dpi_scale
py = ly / ljqCtrl.dpi_scale
ljqCtrl.Click(px, py)
```

## 最常错处

- **禁传逻辑坐标** 给 `Click/SetCursorPos`
- 偏移量同样要除 `dpi_scale`
- 模拟前先确认窗口已置前
- `GetWindowRect` 含标题栏和边框，截图内容多是客户区；点击截图里的元素时，需配合 `ClientToScreen`
- 若未 `SetProcessDPIAware()`，`GetWindowRect/ClientToScreen` 可能给逻辑坐标；全流程必须统一
- 文本输入别空想 `TypeText`：通常是点中输入框后 `pyperclip.copy(...)` 再 `ljqCtrl.Press('ctrl+v')`

## 行术心法

- 这类术最怕“差不多”；一点坐标差，落手就错。
- 真要点之前，宁可多核一眼坐标和窗口状态，也别凭感觉赌。
