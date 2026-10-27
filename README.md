# 蔬果保卫战

Windows 微信《保卫向日葵》蔬果保卫战自动化工具。

## 下载运行

在本仓库 Releases 页面下载 Windows ZIP，完整解压后运行 `蔬果保卫战.exe`。请保留旁边的 `_internal` 文件夹。

## 使用

1. 在电脑微信打开游戏，停在蔬果保卫战入口。
2. 点击左侧“豪华保卫”或右侧“普通保卫”。程序检查对应锤子数量，不足时提示并取消开局。
3. 保持游戏在前台、无遮挡，程序自动处理一局，并在结束后展示得分和水果币。

Esc 停止。程序点击水果、闹钟，避开炸弹；狂热奖励持续按住至结束。识别受画面和性能影响，不能保证每局零失误。不会自动连续开局或购买道具。

运行时会在 `runs/` 目录保存本机画面与事件记录，分享日志前请自行检查内容。

## 源码运行

Windows、Python 3.11：

```powershell
python -m pip install -r requirements.txt
python app.py
```

## 打包

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --windowed --onedir --name "蔬果保卫战" --add-data "assets;assets" app.py
```

构建结果位于 `dist/蔬果保卫战/`。发布时压缩整个目录。

## 测试

```powershell
python -m unittest test_entry test_tracker test_results offline_test
```

仓库包含程序运行和离线验证所需的游戏画面模板，不包含个人对局日志。游戏名称及画面素材属于各自权利人。
