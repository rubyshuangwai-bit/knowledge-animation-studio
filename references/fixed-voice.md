# 固定自然男声

默认档案 `approved-male-v1` 是本用户选择的个人默认值，不是所有用户都必须使用的声音。参考样本为用户先前认可的合成男声，不是真人声优录音。

`assets/voices/approved-male.wav` 保存原始样本，JSON 保存准确参考稿、SHA256、参数和模型仓库。每段均传入同一 ref_audio 与 ref_text，使用 Qwen3-TTS 1.7B Base 8bit，禁止回退为 VoiceDesign 或任意预设声。档案 ID 是本 skill 的内部标识，不是模型内置 speaker ID。

项目设置：`"voice":{"profile":"approved-male-v1"}`；新项目未设置 voice 时也使用它。安装机的 `运行环境/tts.json` 位于 skill 同级，存储 python 和 model 两个绝对路径，不把模型权重打进 skill。迁移到新机器时，配置这两个路径；缺失时明确停止，不悄悄换声。

每次加载核验样本内容 hash，缓存键包含档案、参考稿和参考 hash。参考样本替换必须显式更新档案并重新试听，不能沿用旧审核。参考条件可显著约束音色，但不承诺不同台词完全无漂移；生成后听开头、中间、结尾及段落交界。未试听的新内容仍标记 pending。

模型来源：https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit
