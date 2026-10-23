# 知识动画工作室 · Knowledge Animation Studio

把一个知识主题，变成有资料依据、中文讲解和可编辑源码的动画视频。

这是一套面向 Codex 的知识动画制作 Skill：从“讲清楚什么”开始，组织资料、讲稿、分镜、配音和代码动画，分阶段确认后再交付成片。适合知识科普、课程辅助和原理讲解；不绑定 KV Cache 或任何一个具体主题。

## 它有什么特点？

- **先找依据，再讲知识**：AI 主题优先查阅原始论文、官方文档、大学课程等资料，标明每项事实的来源；资料分析与内容方案先交给用户确认。
- **让画面跟着讲解走**：把讲稿拆成语义单元，让当前讲到的对象、变化和关系在画面中突出，减少观众一边听、一边找对象的负担。
- **配音按完整意思组织**：讲稿、字幕和动画事件分别设计，避免为了字幕短句而把口播切得过碎；支持停顿处理与时间更新。
- **检查句尾与转场**：筛查疑似硬截断，保留收尾缓冲与试听记录。自动检查不能代替实际试听。
- **场景可编辑**：通过 HTML、Canvas 和 JavaScript 绘制动画，无需文生视频模型；复杂概念可以编写专属场景。
- **支持分章制作与修改**：按章节生成、审核、复用匹配缓存和合并；修改讲稿、声音或场景后，检查记录随内容变化而失效。

## 能做什么？

例如：“给小白介绍 Transformer”“解释 KV Cache 为什么能加速生成”“讲解一个推理框架的工作流程”，也可将文章、课程笔记或流程转成动画。

内置六类图解：流程、对比、柱状数量、矩阵、层级、匹配与权重。它们是表达工具，不是必须套用的固定模板；解释不清时应设计自定义动画。

当前重点完善了 **AI 领域**的内容研究流程；教育领域已设置入口，领域专属方法仍需继续完善。

## 制作流程

1. 确认主题、领域、受众和学习目标。
2. 收集权威资料，提交有来源的内容方案，等待用户确认。
3. 设计讲稿与分镜：每镜明确“解释什么”“对象如何变化”。
4. 制作配音和样片，核对声音、字幕与画面的对应关系。
5. 确认样片后制作完整章节，完成技术检查、画面审核和声音试听。
6. 交付章节与合并视频、字幕、项目配置及自定义场景源码。

默认按阶段确认；用户明确允许跳过某个节点时，按其授权执行。

## 在 Codex 中安装

将本仓库克隆到 Codex 的技能目录。请先确认目标目录不存在，避免覆盖自己的版本：

```bash
git clone https://github.com/rubyshuangwai-bit/knowledge-animation-studio.git ~/.codex/skills/knowledge-animation-studio
```

重新打开 Codex 会话后，用 `$knowledge-animation-studio` 调用。安装 Skill 仅安装源码与说明，**不等于已安装渲染和配音环境**。

## 怎么用？

可以直接对 Codex 说：

> 用 $knowledge-animation-studio 做一个介绍 Transformer 的中文知识动画，面向没有技术背景的用户。先查权威资料，把内容方案交给我确认，再继续讲稿和分镜。

或者提供自己的材料：

> 用 $knowledge-animation-studio 把这篇文章制作成知识动画。先列出主要观点和需要核实的事实，再给我内容方案。

已有作品也可以局部修改：

> 用 $knowledge-animation-studio 检查这个项目的句尾和转场，先确认问题；不要重做整个视频。

## 运行环境

基础渲染需要 Python 3、Node.js 22 或更新版本、FFmpeg/FFprobe，以及 Chrome 或 Chromium。渲染器使用 Node 内置 WebSocket，不需要额外的 npm 包。已在 macOS 工作流中使用；跨平台尚未验证。

可选本地 TTS 适配器使用 MLX / mlx-audio，需兼容的 Apple Silicon 环境及自行配置的本地 Qwen3-TTS 模型。模型权重与 Python 虚拟环境不随仓库提供；模型的许可和运行要求应单独核对。也可以直接提供外部配音 WAV，跳过本地 TTS。

仓库保留 `approved-male-v1` 固定男声配置和配套合成参考音频。使用该音色仍须配置兼容的 Base 模型与 Python 路径；参考克隆有助于保持一致，但不保证每段听感完全一致。项目级 `voice` 可覆盖配置。不要把作者电脑的路径直接复制到自己的环境。

项目格式、声音设置与依赖入口见 [项目协议](references/project-format.md)、[固定音色](references/fixed-voice.md) 和 [制作策略](references/production.md)。

## 工具入口

Codex 按 [SKILL.md](SKILL.md) 组织完整流程；下列命令用于已有 `project.json` 的项目：

```bash
python3 scripts/studio.py validate /path/to/project
python3 scripts/studio.py doctor /path/to/project
python3 scripts/studio.py tts /path/to/project       # 可选：已有音频可跳过
python3 scripts/studio.py build /path/to/project
python3 scripts/studio.py preflight /path/to/project
python3 scripts/studio.py render /path/to/project --jobs 1
python3 scripts/studio.py verify /path/to/project
```

合并前还需按 Skill 要求完成有证据的 review。上述命令不是跳过内容确认和试听的“一键制作”承诺。

## 输出与当前边界

- 默认渲染为 **1920 × 1080、30 fps 的横屏 MP4**；此版本不是通用竖屏模板库。
- 每章包含字幕、时间线、页面和视频；审核后可合并为完整视频。
- 未提供可靠对齐记录时，部分字幕时间按文本长度估计；不能将其当作精确发音时间。
- 自动检查不证明事实正确、TTS 无漏字或动画一定讲清楚；仍需审稿、看画面与试听。
- 本仓库不包含模型权重、个人运行环境或历史项目成片。

## 源码结构

| 目录 / 文件 | 用途 |
| --- | --- |
| `SKILL.md` | Codex 工作流与阶段要求 |
| `references/` | 资料研究、阶段确认、语音视觉协同与检查规范 |
| `assets/` | 手绘页面、图解场景与固定音色参考 |
| `scripts/` | 构建、配音、节奏处理、检查与合并工具 |
| `scripts/vendor/` | 保留来源的上游渲染、字幕和动画组件 |
| `agents/openai.yaml` | Codex 展示信息 |

## 来源与许可

本项目在 [dashi-animationstyle](https://github.com/chuspeeism/dashi-animationstyle) 的部分渲染组件与手绘底座之上，增加了通用项目协议、内容研究与确认流程、分章编排、语音视觉协同、自然停顿和句尾检查等能力。

保留上游 MIT 许可及署名，详见 [LICENSE](LICENSE)、[NOTICE](NOTICE) 和 [来源记录](references/upstream.json)。**不包含上游作者的示例录音**。外部资料、模型和用户自带素材按各自许可使用。
