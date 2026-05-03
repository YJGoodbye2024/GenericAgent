# 进程内存探脉之术

这是拿来探进程内存中某段特征、某个字段、某种结构的术。  
若只会扫，不会比对，不会读上下文，就很容易抓到一把死字而抓不到活脉。

## 快速起手

```python
import sys
sys.path.append('../memory/skills')
from procmem_scanner import scan_memory
results = scan_memory(pid, "48 8b ?? ?? 00", mode="hex", llm_mode=True)
```

CLI 也可：

```bash
python ../memory/skills/procmem_scanner.py <PID> "pattern" --mode string
python ../memory/skills/procmem_scanner.py <PID> "pattern" --llm
```

## 这门术最适合做什么

- 找结构体附近的特征码
- 找动态标题、当前会话名、状态字段
- 比对某值在不同状态下怎样变化

## 基本路数

1. 先定一个尽量独特的前导特征
2. 扫一次，拿地址与上下文
3. 再结合上下文字节、ASCII、状态切换去筛

## 注意两件事

- 权限不够，读不出；至少要有 `PROCESS_QUERY_INFORMATION` 与 `PROCESS_VM_READ`
- 特征太泛，误报成群；先把 pattern 收窄

## 动态字段的差集法

这是常用来抓微信等自绘界面中“当前会话标题”一类字段的法子。

### 流程

1. 先取真 PID：用有窗口的那一个
2. 当前会话 = A，扫出地址集 `S`
3. 切到 B，读 `S` 中所有地址，保留内容不等于 A 的
4. 再切回 A，保留重新等于 A 的
5. 若还不止一处，再换 C 继续压缩

### 切换与读取样例

```python
import sys; sys.path.append('../memory/skills')
import ljqCtrl, pygetwindow as gw, pyperclip, time, ctypes
```

后面的 `switch_chat` 与 `read_addrs` 可沿用旧样例代码；要点不在花样，而在 **切换成功后再读**。

## 易错处

- `Weixin.exe` 不是 `WeChat.exe`
- 地址字符串先 `int(addr, 16)`
- 第 3、4 步是 **读旧地址集**，不是重新 `scan`
- 搜索结果首项可能是广告，别看错人
- 候选大于一时，最后消歧往往要配合侧栏点击与视觉确认
- `scan_memory` 默认回的是字符串列表，不是 dict

## 心法

- 这门术怕急。急则重扫，重扫则丢动态地址。
- 若一处字段要靠状态变化才显真身，就别拿静态残影当答案。
