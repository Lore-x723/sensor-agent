# Sensor Agent｜设备异常处置智能体（原型）

一个面向校园实验室和小型设备的**学习型原型**：读取传感器 CSV，找出异常读数，再用工具生成可追溯的处置清单。默认使用模拟数据，无需账号或付费接口即可运行。配置兼容 OpenAI Chat Completions 的模型后，模型可自主选择查询数据、检测异常和生成清单等工具。

> 当前没有接入真实传感器，也没有在真实场景验证；输出仅用于演示，不能替代设备管理人员的判断。

## 解决的问题

设备数据通常散落在表格里，值班人员需要快速知道“哪台设备、何时、哪项指标异常、接下来核查什么”。这个原型把数据检测和后续行动放在同一个流程里，保留每条判断对应的原始读数。

## 运行

需要 Python 3.10+，只用标准库。

```bash
python agent.py --demo
python agent.py --csv sample_data.csv
```

Windows PowerShell 如果中文显示乱码，可先执行 `$env:PYTHONIOENCODING = "utf-8"`，再运行上述命令。

可选：启用大模型工具调用。请在本机设置环境变量，不要把密钥写入仓库。

```powershell
$env:AGENT_API_KEY = "你的密钥"
$env:AGENT_BASE_URL = "https://你的服务地址/v1"
$env:AGENT_MODEL = "支持工具调用的模型名"
python agent.py --csv sample_data.csv --llm
```

`--llm` 使用兼容 OpenAI Chat Completions 的 `/chat/completions` 接口。不同服务的工具调用支持可能不同；这里没有提供或测试任何特定服务的账号。

## 数据格式

CSV 表头：`timestamp,device,temperature_c,vibration_mm_s`。时间使用 ISO 8601，例如 `2026-10-19T10:00:00`。每行是一次设备读数。程序会拒绝缺列、非数字和非有限值。

默认规则：温度 `> 60 °C` 或振动 `> 4.5 mm/s` 标记为异常。阈值只是演示参数，不适用于所有设备，可以用 `--max-temp` 与 `--max-vibration` 修改。

公开液压设备数据的初步测试显示，这组默认阈值在 2,205 个周期中没有产生任何报警。因此“未报警”不能解释为“无故障”；真实部署必须先按设备类型校准阈值，并用有标注的历史数据验证误报和漏报。详见项目测试报告。

## 项目结构

- `agent.py`：读数校验、工具函数、离线演示和可选的大模型工具调用
- `sample_data.csv`：人工编造的示例数据
- `test_agent.py`：输入校验与异常检测的基础测试
- `PROJECT_BRIEF.md`：可用于申请展示的项目现状与验证计划
- `evaluate_uci.py`：对公开液压设备数据进行可复现的离线评估
- `TEST_REPORT.md`：公开数据测试摘要

## 一分钟演示

1. 运行 `python agent.py --demo`。
2. 指出 `motor-02` 的异常读数，以及输出中对应的时间和数值。
3. 解释清单如何从异常类型生成，并指出“停止设备”必须由负责人现场判断。
4. 说明下一步会连接真实传感器、收集误报反馈、验证阈值和提醒方式。

## 当前局限

- 离线模式是确定性工具流程；只有开启 `--llm` 且连接支持工具调用的模型，才有模型自主选工具的智能体流程。
- 阈值检测是规则方法，并非训练好的机器学习模型。
- 示例数据是模拟的；没有硬件接入、真实用户验证或商业收入。
- 大模型的建议可能不准确；最终处置必须有人审核。

## 公开数据复测

测试使用 [UCI 液压系统状态监测数据集](https://archive.ics.uci.edu/dataset/447/condition+monitoring+of+hydraulic+systems) 中的 `TS1.txt`、`VS1.txt` 和 `profile.txt`，本仓库不包含原始数据。将这三个文件放进同一个目录后运行：

```bash
python evaluate_uci.py path/to/data-directory
```

脚本会输出混淆矩阵，并在数据目录生成 `uci_cycle_means.csv` 供主程序复测。该 CSV 中的时间是为了适配输入格式而生成的占位时间，并非真实采集时间。测试方法和结果见 `TEST_REPORT.md`。

## 后续验证

找 3 位实验室或设备管理相关同学访谈，确认最常见的异常、现有记录方式和误报成本；再用获授权的真实历史数据测试召回率与误报率。获得明确需求后再接入 ESP32 或现成传感器网关。

## 许可

MIT License，见 `LICENSE`。
