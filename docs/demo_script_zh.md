# FaultLine Demo 讲稿（中文）

面向 Bittensor 社区 / 子网评审。全程只需一条命令，无 GPU、无链、无网络依赖，约 6–8 分钟。

```bash
python demo_showcase.py
```

演示前建议先跑一遍 `python -m pytest -q`（9 个测试，约 3 秒），评审如果质疑任何数字，当场重跑即可——所有输出都是确定性计算。

---

## 开场（30 秒）

> 所有人都在 benchmark agent 能做什么，FaultLine 系统性地挖掘 agent **不能**做什么。矿工提交可复现的边界案例——一个任务环境加一段断言 checker，钉死版本的目标 agent 在上面可证明地失败。整条评分管线里没有人工打分，也没有 LLM-as-judge：每个判决都是代码断言，每个分数都能逐位复算。
>
> 这个 demo 演六幕：一个诚实矿工，三种作弊，一个滚动注册表，一套治理机制。

按回车跑脚本，逐幕暂停讲解。

## 第 1 幕：诚实矿工（1 分钟）

预期输出：`gate=VALID score=1.0, novelty=1.0`。

> 案例要过两道门。门 1 是可解性证明：矿工必须附一份参考解，用自己的 checker 验证通过——"不可能任务"刷分在结构上就不成立。门 2 是失败复现：validator 独立重放，钉死的目标 agent 必须真的失败。两道门都过，这是该失败类别的首次发现，novelty 1.0，满分。

要点：强调"参考解通过 + 目标失败"这个组合是整个供给侧的质量底线。

## 第 2 幕：Sybil 攻击——换皮刷新颖性（1.5 分钟，重点）

预期输出：两个指纹**完全相同**（`eb0e9de018225b43`），换皮案例 `score=0.5061, novelty=0.1768`。

> 这是评审最常问的问题：两个"看起来不同但本质相同"的提交，怎么识别？攻击者把 checker 重写了——断言全部改名成 `SD_READ_totally_new_bug_v2` 这种，控制流也重排了。但签名不看矿工写的任何字符串：validator 把 checker 扔进一组固定探针状态里跑，把判决向量规范化后哈希。行为相同，指纹就相同。
>
> 已知指纹再次提交，novelty 在类别衰减之上再乘 0.25：从 1.0 直接砸到 0.1768。换皮的边际收益是负的。

要点：如果被问"探针集是公开的，能不能 Goodhart？"——承认可以，这是 Known Limitations 里明写的残留风险，缓解路径是探针版本化 + 从 corpus 派生 validator 私有探针，在 roadmap 上。主动说比被挖出来强。

## 第 3 幕：铸造新失败类别（1 分钟）

预期输出：`category=UNCLASSIFIED, novelty=0.5, score=0.7`。

> 换皮不行，那直接发明一个新类别呢？断言返回 `ZZ_AMAZING_NEW_FAILURE`。分类学是一张封闭的、带版本号的前缀表，扩表是走治理流程的变更。不认识的前缀一律记入 UNCLASSIFIED，novelty 减半。铸造是有界的，不是免费的。

## 第 4 幕：垃圾提交（30 秒）

预期输出：`UNSOLVABLE score=0.0`、`CHECKER_ERROR score=0.0`。

> 不可解案例零分——门 1 挡掉。checker 里写 `import os` 想探沙箱——子进程裸命名空间直接报错，零分。这两类攻击不需要检测，结构上就不成立。

## 第 5 幕：滚动目标注册表（1.5 分钟）

预期输出：三个 tier 权重 0.167 / 0.333 / 0.500；只挂掉弱、中两档时 `difficulty=0.5, score=0.8`。

> 目标模型太旧，题库就是对过时模型的 benchmark；更新太快，矿工的存量案例一夜作废。我们的解法是滚动窗口：注册表里每个目标钉死 (checkpoint × harness commit)，权重按**实测通过率**排序——不是参数量。我们实测过 SmolLM2-360M 比 Qwen2.5-0.5B 大三倍地能通过案例，参数量排 tier 会算出负难度。
>
> 难度 = 挂掉的目标的权重和。这个案例只挂掉弱、中两档，强档通过了，difficulty 0.5。想拿满，去挖最新最强模型的失败——激励自动指向前沿。tier 生命周期 active → deprecated（权重减半）→ retired（归零），且**从不追溯重算**已发放的 emission。

## 第 6 幕：治理（1.5 分钟）

预期输出：突袭改参数被作废（`active version = v1`）；phase-2 检查 `ready=False (0/8)`。

> 最后是对 Owner 中心化的回应。评分参数在版本化的 `scoring_params.json` 里，每个版本必须附实测依据。关键机制：生效时间距公告不足 7 天的版本，validator 直接作废——timelock 是代码常量，想缩短它得改代码、留下公开 diff。Owner 想把 novelty 权重从 0.6 突袭改到 0.99？无效。"参数不能突袭"不是承诺，是被执行的。
>
> 第二阶段（LLM judge 赛道）的准入同样是机器可判的预注册阈值：至少 8 个类别、每类至少 20 个**不同指纹**（防模板灌水）、跨至少 2 个 tier。`python -m faultline.milestones` 随时可查进度。现在是 0/8——我们如实说没到，到了也不需要谁拍板。

## 收尾（30 秒）

> 六幕里每个门、每个惩罚、每个权重都是确定性代码。仓库里每个数字背后有归档 trace，评审可以逐条复算：`python demo_showcase.py`、`python -m pytest -q`、`python -m faultline.milestones`。

---

## 评审 Q&A 预案

**Q：探针集公开，矿工特判探针状态怎么办？**
承认（README Known Limitations 明写）。缓解：探针版本化已就位（`PROBE_BATTERY_VERSION`），下一步是 validator 私有探针从 corpus 轮换派生。同时特判探针的 checker 仍要过可解性门和失败复现门，攻击面比"改字符串"贵几个数量级。

**Q：类别级计费太粗，同类别里两个真正不同的失败共享衰减？**
是有意的取舍，偏向防换皮而非精细计量。类内多样性由指纹计数体现，并直接进 phase-2 准入指标；未来可在类内按指纹给次级衰减，参数走 timelock 变更。

**Q：跨机器 float 分歧怎么办（多 validator）？**
已知限制。贪心解码单机可复现；跨硬件用判决级（而非 token 级）门控缓解，容器化在 roadmap。

**Q：闭源 API 目标？**
只支持统计口径，不支持确定性复现——如实声明，不假装能钉死。

**Q：为什么不上 DAO 投票？**
子网 Owner 特权是 Bittensor 结构性的，MVP 阶段 DAO 是装饰。timelock + 强制实测依据是当前能真正执行的最小可信承诺；治理可以后续加码，作弊没法追溯补救。

**Q：真模型呢？这 demo 全是 scripted。**
scripted 只为演示机制的确定性。真模型证据在仓库里：45 案例 × 3 模型矩阵、tier flip 矩阵、全部 trace 归档（`evidence/`），README 的 Key Results 一节逐条链接。
