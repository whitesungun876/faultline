# FaultLine Testnet MVP — Day-1 作战手册

代码状态：core（toolbox / harness / verify / 5 个种子案例 / 端到端演示）已在 Python 3.12 + bittensor 10.5.0 环境下**实测通过**；neurons/（miner / validator / protocol）通过语法与 Synapse 实例化检查，链上行为需在你的机器上首次实跑验证。

## 关键路径（现在就做，不要等）

1. **去 Bittensor Discord 请求 testnet TAO**（创建子网约需 100 testTAO，数额随需求浮动，官方渠道就是 Discord 人工发放）。这是全天唯一不受你控制的等待项，先排队。
2. 等待期间完成本地验证（下方 Hour 1–4）。

## 小时计划

**Hour 0–1 环境**
```bash
python3 -m venv bt_env && source bt_env/bin/activate
pip install bittensor bittensor-cli
# 三套钱包：owner / miner / validator（全新密码，绝不复用主网钱包）
btcli wallet new_coldkey --wallet.name owner
btcli wallet new_coldkey --wallet.name miner
btcli wallet new_hotkey  --wallet.name miner --wallet.hotkey default
btcli wallet new_coldkey --wallet.name validator
btcli wallet new_hotkey  --wallet.name validator --wallet.hotkey default
```

**Hour 1–2 本地验证核心管道（无链）**
```bash
python make_seed_cases.py
python run_local_demo.py        # 四个 gate 全绿才继续
```

**Hour 2–4 接入真实目标模型**
```bash
pip install torch transformers accelerate
python - <<'EOF'
import json, pathlib
from faultline.harness import HFBackend
from faultline.verify import evaluate_case
backend = HFBackend("Qwen/Qwen2.5-1.5B-Instruct")   # v0 目标注册表 = 这一个 pinned 模型
corpus = {}
for p in sorted(pathlib.Path("seed_cases").glob("*.json")):
    case = json.loads(p.read_text())
    print(case["case_id"], evaluate_case(case, backend, corpus))
EOF
```
预期：5 个种子案例中至少 2–3 个 gate=VALID（真实模型翻车）。全部 AGENT_PASSED 就把案例加难（改数字、加干扰项）；这一步同时就是你的第一次真实 fuzzing。没有 GPU 就换 `Qwen/Qwen2.5-0.5B-Instruct` 跑 CPU。

**Hour 4–6 testnet 注册（testTAO 到账后）**
```bash
btcli subnet create --wallet.name owner --network test        # 记下返回的 netuid
btcli subnet register --netuid <NETUID> --wallet.name miner     --wallet.hotkey default --network test
btcli subnet register --netuid <NETUID> --wallet.name validator --wallet.hotkey default --network test
btcli wallet overview --wallet.name miner --network test       # 确认 UID 出现
```

**Hour 6–8 双神经元上线**
```bash
# 终端 1
python neurons/miner.py     --netuid <NETUID> --subtensor.network test \
  --wallet.name miner --wallet.hotkey default --axon.port 8091 --logging.debug
# 终端 2（先用 mock 验证布线，再切真模型）
python neurons/validator.py --netuid <NETUID> --subtensor.network test \
  --wallet.name validator --wallet.hotkey default --mock_backend --logging.debug
```
成功标准：validator 日志出现 `gate=VALID` 与 `set_weights ok`。`set_weights` 偶发 rate-limit 报错属正常，等下一轮。跑通后去掉 `--mock_backend` 切换 HFBackend。

**Hour 8+ 留痕**：截图 validator 日志 + `btcli subnet list --network test` 里你的 netuid + corpus_index.json 增长。这三张图就是你接触孵化器/发帖的 day-1 证据。

## 已知债务（testnet 可接受，mainnet 前必须还）

1. **checker 沙箱是 subprocess + rlimit + 裸命名空间，不是容器**。恶意 import 已被拦截（演示 gate 4），但这不是安全边界，只是护栏。mainnet 前上 Docker/gVisor。
2. 无提交保证金 → 无垃圾提交经济惩罚（testnet 无所谓）。
3. Difficulty 恒为 1（单目标注册表）；Generality 未实现。
4. miner 只轮询种子案例，无自动生成；validator 单机、corpus 索引为本地 JSON 未共识。
5. dendrite 广播查询全部 UID，无采样与黑名单。
6. 当前“确定性”只证明单设备确定性。同一台 Mac/MPS 上贪心解码可复现；跨 CUDA/MPS/CPU 时浮点与 kernel 差异可能改变边缘轨迹。多验证者阶段需要钉死设备/运行时，或对判定分歧引入容忍投票。

## 明日以后（按序）

自动化案例生成器（模板 + 变异）→ 第二个注册表目标（启用 Difficulty）→ corpus 索引上共享存储 → Docker 化环境 → 用真实翻车率数据回填提案第三节。
