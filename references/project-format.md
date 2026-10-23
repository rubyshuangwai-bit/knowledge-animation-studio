# 项目配置与图解协议

作品目录包含`project.json`，音频可以是相对项目路径，也可以是用户明确提供的绝对路径。skill本身不含电脑专属模型路径。

```json
{
  "version": 1,
  "title": "虚构咖啡店：订单如何流转",
  "fps": 30,
  "highlights": [{"text":"订单","role":"A"}],
  "emphasis": ["制作"],
  "sources": [],
  "chapters": [{
    "id": "ordering",
    "title": "从下单到取餐",
    "shots": [{
      "id": "flow",
      "title": "一份订单的旅程",
      "narration": "这家虚构咖啡店，把订单分成下单、制作和取餐三个步骤。",
      "explain": "理解虚构流程的先后顺序",
      "change": "订单依次经过三个状态，而不是三个标题同时展示",
      "claim_type": "illustrative",
      "source_ids": [],
      "audio": "audio/ordering/flow.wav",
      "visual": {"kind":"flow","labels":["下单","制作","取餐"],"note":"虚构流程，用于演示"}
    }]
  }]
}
```

- `id`只用英文字母、数字、下划线、连字符；章节id全项目唯一，镜头id章内唯一。数量不固定。
- `claim_type`为`factual`时必须指定已核对的`source_ids`。`sources`记录`id`、`url`或材料路径、核对日期、支持哪一项主张；验证器只检查关联，不会自动验证事实。
- `title`与图中标签尽量简短。画面底座为1920×1080、30fps；正文至少48像素，字幕64像素。长标签会换行，仍放不下则报错，不能缩成小字硬塞。
- 每章会生成字幕、时间线、Canvas页面和视频。章节末尾音频补到帧边界；句内字幕估算和外部对齐的状态写在build记录。

## 内置图解

| kind | 参数 | 用于 |
|---|---|---|
| flow | labels：2–6个简短状态 | 顺序、处理流程，按顺序建立节点 |
| comparison | groups：两项`{title,items}`；每项至多3条短项 | 前后、两种方案或两种条件 |
| bars | labels、values：1–6项，值为非负有限数 | 数量与比例；说明数据来源和单位 |
| matrix | values：最多4×4的矩形数组 | 数值结构；具体计算含义另用自定义动画解释 |
| layers | labels：2–6项 | 层级或堆叠结构 |
| attention | labels：首项是匹配对象，其余为候选；可给weights | 匹配与权重关系，不能自动替代完整的技术机制 |
| custom | 自定义参数 | 需要对象形变、存取、反馈等题材专属机制 |

`note`为一行解释或示意声明。不要把同一主题所有镜头强行落进同一种图解；视觉类型应服务于`explain`和`change`。

## 自定义场景

在作品目录创建`custom.js`，配置`visual.kind="custom"`，其他字段原样传入：

```javascript
window.drawKnowledgeScene = ({ctx,t,progress,scene,shot,palette,label,box,arrow}) => {
  // ctx已经进入当前镜头的画布坐标；主内容放在x=180..1740、y=270..720。
  // progress为当前镜头0..1，t为全章时间，shot.start/end为镜头边界。
  const x = 260 + 900 * progress;
  box(scene.object || '对象', x, 400, 300, 140, palette.orange);
};
```

画面必须只依赖t、输入与固定随机种子。不使用Date.now()、不确定随机数、逐帧累加或真实播放进度。若需要指定语音卡点，从已核对的时间输入构造事件；不要假装插值就是实际发音时间。

## 可选本地配音

项目可增加`voice`：

```json
{
  "python": "/absolute/path/to/venv/bin/python",
  "model": "/absolute/path/to/local-model",
  "mode": "design",
  "language": "Chinese",
  "instruct": "普通话自然清晰，像向朋友解释知识，轻松亲切，有自然停顿和语调起伏。",
  "seed": 42,
  "temperature": 0.8
}
```

`mode="preset"`时使用模型实际支持的`speaker`，替代`instruct`。本版支持MLX设计、预设和参考克隆。固定男声用 `"voice":{"profile":"approved-male-v1"}`，不要指定设计音色模型覆盖它。没有可用模型时使用外部配音即可，不把模型下载混入动画制作。

## 外部字幕边界

每个镜头可以配置`alignment`指向JSON：

```json
{"method":"manual","cues":[{"text":"第一句话。","start":0.1,"end":1.8}]}
```

`method`可为`manual/asr/forced`，表示输入边界的来源；它不是验证器证明过的精度。文本必须与该镜头讲稿一致，时间相对该镜头原始音频，不能交叠或超出音频。当前仅接收字幕条边界，字级时间仍为插值。未提供时显式记为estimated。

## 语义单元、节奏与章节源文件

讲稿、字幕条和语义单元分开组织。`visual.units`内的`text`顺序拼接应与讲稿一致；每项必填`text/target/action`，`background`描述降权的上下文。`events`与units一一对应，时间相对**该镜头当前音频**，按顺序、不重叠、不超出音频；它们不会自动让任意自定义代码切换状态，`custom.js`必须据此绘制。内置图解仍有默认展开逻辑，需要语义精确控制时使用自定义场景。

```json
{
  "raw_audio": "original/one.wav",
  "rhythm": {
    "pauses": [{"after": 0, "min_gap": 0.7}],
    "key_phrases": ["下一步"]
  },
  "visual": {
    "kind": "custom",
    "units": [
      {"text": "先定位对象。", "target": "对象", "action": "框选当前对象", "background": "其余信息降权"},
      {"text": "下一步，观察它的变化。", "target": "同一对象", "action": "保留前态并演示变化"}
    ],
    "events": [{"start": 0.2, "end": 1.9}, {"start": 2.6, "end": 5.1}],
    "key_events": {"下一步": 2.6}
  }
}
```

示例时间仅说明协议，不是工具实测输出。`after`是从0开始的语义单元索引，不能指向末项；`min_gap`是希望达到的间隔，工具只补不足部分。关键词必须在讲稿中唯一出现；重复关键词采用核对后的人工事件。不要将样例的停顿值当所有主题默认值。

原音频时间JSON按`<chapter>/<shot>.json`保存，例如：

```json
{
  "method": "asr",
  "audio_sha256": "实际原始WAV的SHA256",
  "segments": [{"start": 0.2, "end": 1.9, "text": "先定位对象。", "words": [{"start": 0.2, "end": 1.9, "word": "先定位对象。"}]}]
}
```

也可提供`manual/forced`方法的`cues`，每条含text/start/end，hash仍对应原始WAV。只有句级记录时句内时间为插值，不宣称ASR字级准确。音频须为单声道PCM16 WAV；格式转换先另存原音频副本。

`prepare_narration.py`的预览配置将接入`audio/alignment/processing`、更新events及key_events，保留raw_audio。工具默认不覆写项目。`build`检查来源和处理后音频、字幕文件、讲稿、停顿配置与事件记录，发现过期时停止。即便技术校验通过，声音状态仍待试听。

章节可以设置`"custom_script":"scenes/ordering.js"`覆盖默认项目`custom.js`。把局部修正保存在此源文件，build会复制到章节生成目录并跟踪hash。共用脚本变化会影响所有引用它的章节；只有源文件独立时才能隔离章节修改。已交付旧作品在工具升级后可能被标为需要重新构建，保留其成片和审核记录，不为升级无故重渲。

## 末句试听记录

每镜头可设置`audio_end_review`指向当前音频的末句试听记录；派生音频的原始结尾若被标记，还需`source_end_review`。记录必须绑定实际试听的音频SHA256，`status`为`listened_complete`且notes含实际末句核对结果。仅在实际听过、确认完整时填写。通过ASR或信号检查不得自动写此值。缓冲派生音轨使用`audio_endings.py pad`保留`.end.json`来源记录。详见[audio-endings.md](audio-endings.md)。
