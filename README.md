# 硅基新电商播客剪辑

把科技、商业访谈做成可试听、可追溯、可继续修改的播客。技能包含制作流程、局部修改规则和两个执行工具，供支持 `SKILL.md` 的AI助手使用。

默认结构：**本期精华 → 固定本人介绍 → 本期嘉宾介绍 → 正文**。其他节目可按当前需求调整。适合完整剪辑、补录接入、精华节奏调整、配乐修改和发布前核验。

## 安装与调用

在Codex技能目录安装：

```bash
git clone https://github.com/zhengzhentao86/silicon-ecommerce-podcast-edit.git "$HOME/.codex/skills/silicon-ecommerce-podcast-edit"
```

目标目录已存在时，先备份或更新已有安装，不要直接覆盖。也可下载仓库ZIP，解压为 `silicon-ecommerce-podcast-edit` 文件夹，放入客户端技能目录。其他支持技能的客户端使用其对应目录。

在客户端加载技能的新对话中调用：

> 使用 $silicon-ecommerce-podcast-edit 剪辑这期访谈。去掉无意义填充和卡壳，保留正常回应，先给我精华及配乐试听，再交付完整音频与章节。

> 用硅基新电商播客剪辑skill，把我的补录介绍精修后接在精华后面，沿用已剪好的正文。

用户提供音频与自然要求即可。AI负责维护编辑清单、配置、素材缺口和版本记录，不要求用户额外填制作表。

## 环境

- Python 3.10及以上。
- FFmpeg和FFprobe，可通过系统包管理器安装。
- NumPy、SoundFile用于实际无损剪切；已有可用Python环境时优先复用。
- 转录需要AI所在环境已有的ASR工具和模型。仓库不附带模型，也不自动安装大型转录依赖。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

中国大陆可在pip命令末尾加 `-i https://pypi.tuna.tsinghua.edu.cn/simple`。Windows激活环境用 `.venv\Scripts\Activate.ps1`。

## 工作方式

1. 归档原件，核对指纹、声道与已有转录。
2. 内容审读和原音时间编辑清单：删明确重复、跑题与录制插曲，保留观点、依据、条件和分歧。
3. 字词精剪，处理无意义填充、气口、卡壳和杂音；有效肯定、疑问和自然停顿保留。
4. 提取几句关键观点；新增介绍执行相同精修，固定本人介绍和本期介绍分开保存。
5. 先用短样例校准节奏和音乐，再按模块装配；开场、介绍、正文配乐分层。
6. 全解码、时长、峰值、响度与剪口核验，交付整集、试听、章节、复用素材和未决事项。

修改精华或补录时复用未变正文干声。工程保留原件/无损母版，不逐代读取MP3重新编码；音乐另轨，按新时长连续铺设。

本技能通过AI执行全流程。附带脚本负责清单保护与无损干声剪切，**不提供一条命令自动完成ASR、内容判断、降噪、混音和发布**。音乐候选电平需要实际试听，自动核验不等于人工逐字听校。

## 执行工具

AI先按 [音频执行合同](references/audio-contract.md) 生成原音时间清单并核对转录覆盖，然后使用：

```bash
python scripts/cut_plan.py --plan episode-plan.json --output validated-plan.json --merge-gap 0
python scripts/render_cut.py --source episode-source.wav --plan episode-plan.json --output body-v1.wav --merge-gap 0
```

`cut_plan.py` 显式接收合并参数，检查合并后是否扩大删除范围、是否覆盖需要保留的字词。`render_cut.py` 渲染前再次检查清单和源指纹，保留单/双声道，输出FLOAT WAV和实际时间映射，拒绝覆盖已有版本。

项目配置示例：[podcast-project.example.json](assets/podcast-project.example.json)。AI将配置保存到素材项目内，示例路径需绑定用户真实素材；仓库不提供节目原声或音乐。

## 更新和共同迭代

用git安装后更新：

```bash
git -C "$HOME/.codex/skills/silicon-ecommerce-podcast-edit" pull --ff-only
```

如自己改过安装目录，先保存变更，通过分支和PR合入，不用强制拉取覆盖。助理可以在 [Issues](https://github.com/zhengzhentao86/silicon-ecommerce-podcast-edit/issues) 记录使用反馈或最小复现；改动通过PR评审。详见 [贡献说明](CONTRIBUTING.md)。仓库的push和PR会运行自动检查。

```bash
python scripts/validate_release.py
python scripts/test_cut_plan.py
python scripts/test_render_cut.py
```

现有17项回归涵盖删除间保留正文、合并后检查、短填充、未决内容、源指纹、两个不同合成音频的实际剪切及保留波形。CI另检查技能结构、相对引用与发布文件。实际节目效果和省时效果仍需真实使用验证。

## 内容边界与许可

本仓库只包含技能指引、源代码、合成测试和配置示例。录音、完整转录、项目日志、私人配置和凭据保留在各自项目，不提交到仓库。公开内容疑问单列待确认，技能不自动上传或发布节目。

[MIT License](LICENSE)。许可覆盖本仓库代码与指引，不代表用户上传音频或第三方音乐获得再分发许可。
