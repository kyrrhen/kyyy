# kyyy — AR Visual 9-Key Chinese Virtual Keyboard

AR视觉九键中文虚拟键盘 — 基于计算机视觉的Windows虚拟键盘外设。

## 工作原理

程序调用摄像头采集实时画面，将半透明九键键盘图层叠加于画面内。通过MediaPipe视觉算法识别指尖位置，当判定指尖稳定悬停在某按键上时，直接向Windows系统发送标准键盘按键信号。

**程序 = 虚拟键盘外设**：不提供输入框、不显示文字，完全模拟实体USB键盘的工作方式。光标在哪里，文字就出现在哪里。

## 系统要求

- Windows 11
- USB摄像头或内置摄像头
- Python 3.10+
- 系统中文输入法（微软拼音、搜狗等）

## 安装

```bash
pip install -r requirements.txt
```

依赖包：
- `opencv-python` — 摄像头采集与画面渲染
- `mediapipe` — 手部关键点检测
- `numpy` — 数值计算

## 运行

```bash
python main.py
```

可选参数：
```bash
python main.py --debug          # 启用调试叠加层
python main.py --config my.json # 使用自定义配置文件
```

## 使用方法

1. 启动程序 → 摄像头初始化，弹出预览窗口
2. **点击任意文本输入框**（记事本、微信、浏览器地址栏等）
3. 在预览窗口画面中，将食指指尖停留在目标按键上
4. 保持稳定约0.5秒 → 按键触发（绿色闪烁）
5. 字符直接出现在光标所在位置

## 按键布局

```
[1]  [2]  [3]
[4]  [5]  [6]
[7]  [8]  [9]
[DEL] [空格] [回车]
```

程序发送数字键给系统输入法，由输入法完成拼音→汉字的转换。

## 快捷键（预览窗口中操作）

| 按键 | 功能 |
|------|------|
| Q / ESC | 退出程序 |
| P | 暂停 / 恢复检测 |
| +/- | 调整键盘透明度 |
| [ / ] | 调整点击灵敏度（悬停帧数） |
| D | 切换手部骨骼调试显示 |
| F | 切换FPS显示 |
| B | 切换按键边界调试显示 |
| R | 重新加载配置文件 |

## 配置文件

编辑 `config.json` 可调整以下参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `camera_id` | 0 | 摄像头设备ID |
| `keyboard_alpha` | 0.45 | 键盘透明度 (0.0-1.0) |
| `dwell_frames` | 15 | 触发所需悬停帧数（越小越灵敏） |
| `debounce_frames` | 25 | 按键冷却帧数 |
| `keyboard_height_ratio` | 0.50 | 键盘占画面高度比例 |
| `smoothing_alpha` | 0.40 | 指尖平滑系数 |
| `flip_horizontal` | true | 水平镜像（自拍模式） |

## 项目结构

```
kyyy/
├── main.py              # 入口
├── config.json          # 配置文件
├── requirements.txt     # Python依赖
├── README.md
└── src/
    ├── app.py           # 主循环编排器
    ├── camera.py        # 摄像头管理
    ├── hand_detector.py # MediaPipe手部检测
    ├── overlay.py       # 键盘图层渲染
    ├── click_detector.py# 点击检测状态机
    ├── keyboard_sender.py # Windows按键模拟(SendInput)
    └── config_manager.py  # 配置管理
```

## 技术栈

- **摄像头**: OpenCV VideoCapture (DirectShow)
- **手势检测**: MediaPipe Hands (21点手部关键点)
- **按键模拟**: Windows SendInput API (ctypes)
- **渲染**: OpenCV 多层Alpha混合叠加
- **防抖**: EMA平滑 + 驻留时间状态机 + 全局冷却
