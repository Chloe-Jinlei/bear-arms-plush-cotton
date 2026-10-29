# GitHub 归档说明

本次上传将原本分散于工作目录、临时目录与内存盘的本任务资料保存到独立仓库。源运行实现与资产不作物理修改。

- `runs/plush-cotton-complete-01` 为已交付完整结果；`experiments/material-development/full-03` 保留同次运行原始录像。
- `reference/original-successful-run` 是原材质对照；其余开发目录的通过/失败状态按原始报告保留。
- `docs/physical-parameters-plush-cotton.pdf` 是此前六页中文参数 PDF 的原样副本，现纳入持久归档。
- `docs/pdf-source/build_parameters_pdf.py` 保留生成 PDF 时的源脚本；其输出路径与字体路径仍是原机器路径，重新生成前需改为本机路径。已生成的 PDF 可直接阅读。
- 原记录中的绝对路径作为运行来源证据保留，不代表克隆后的文件位置；主 README 提供当前相对路径。
- 未包含 `.git` 旧历史、虚拟环境、凭据、引擎编译缓存或 Python 字节码。已删除的临时实验输出不能从现有文件恢复，未进行重建或伪造。
- 新增 `scripts/run_portable.py` 只负责定位 vendored 机器人资产及当前 Python 环境，不改变动作、材料或几何。根目录原运行文件与 `source-at-run` 仍可逐字节比对。
