# 观图之术：Vision API

这门术不是一见图就上。  
能靠窗口标题、本地 OCR、局部截图弄清的，就别惊动 vision。

## 先守三条

1. 调 vision 前，先枚举窗口，确认目标确实在
2. **禁全屏截图**
3. 能不用 vision 就不用，最后才请它看图

## 快速用法

```python
from vision_api import ask_vision
result = ask_vision(image, prompt="描述图片内容", backend="claude", timeout=60, max_pixels=1_440_000)
```

- `image` 可是路径，也可是 `PIL Image`
- `backend` 可为 `claude / openai / modelscope`

## 若 `vision_api.py` 尚未成形

1. 复制 `memory/skills/vision_api.template.py` → `memory/skills/vision_api.py`
2. 只改头部配置区
3. 去 `mykey.py` 看可用配置名，但 **不输出 key 正文**
4. 若本地都无，就再考虑 ModelScope token

## 行术次序

- 先用 `pygetwindow` 找窗
- 再用 `ljqCtrl` 截局部
- OCR 能读出来，就不要调用 vision
- 真调用时，尽量给它足够小而明确的图

## 心法

- 这门术贵，不该拿来替代观察
- 图给得越大、问题越虚，它越容易花里胡哨
