"""一次性写入 Kimi K3 前 4 页预览译文。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "data" / "papers" / "c03e3fd0-c3b5-4f65-8af7-eb720a5f3893"
ZH = {
    "s_94bb18e473": "KIMI K3：开放的前沿智能",
    "s_d42804011c": "Kimi K3 技术报告",
    "s_c5f8c088ae": "Kimi 团队",
    "s_206b35552a": "摘要",
    "s_f4ca4f073f": "我们推出 Kimi K3：总参数 2.8T 的混合专家模型，激活参数 1040 亿，具备原生视觉能力，上下文窗口达 100 万 token。",
    "s_59620645c9": "Kimi K3 建立在 Kimi Delta Attention [63] 与 Attention Residuals [57] 之上，以改善沿序列长度与模型深度的信息流动。",
    "s_4a2eb832fa": "再配合 Stable LatentMoE（每个 token 实际激活 896 个路由专家中的 16 个）以及改进的训练与数据配方，相对 Kimi K2 [58] 整体缩放效率约提升 2.5 倍。",
    "s_07eb2ce4f6": "后训练重点覆盖通用、智能体与编程领域的强化学习，并支持多种推理投入档位，从而实现组合泛化与稳健的长程执行。",
    "s_02a60b548e": "在 2.8T 规模下，Kimi K3 还依赖多方面的基础设施进展：面向 KDA 的算法–系统协同设计、完全均衡的专家并行训练与高效显存管理、带持久 rollout 与沙箱状态的百万 token 智能体强化学习，以及部署侧创新。",
    "s_b41fbde818": "大量评测表明，Kimi K3 在长程编程、智能体、知识、推理与视觉任务上达到前沿水平。",
    "s_1486dc4ab8": "尽管整体仍落后于最强闭源模型 Claude Fable 5 与 GPT-5.6 Sol，Kimi K3 在我们评测套件中稳定优于其余开源与闭源模型。",
    "s_a4fedc5004": "我们发布完整的 Kimi K3 权重，以促进后续研究，并加速前沿智能的部署与采用。",
    "s_f118ffd9ae": "通用与视觉智能体：思考投入拉满（max 或 xhigh）。",
    "s_2ebd8c9b5d": "图 1：Kimi K3 主要结果。",
    "s_2cbfa53c83": "1 引言",
    "s_bdd1cf83c2": "在大语言模型发展的很长一段时间里，所谓缩放意味着在部署前投入更多计算：用更多数据训练更大的模型 [54, 45]。",
    "s_11ea9a6bc2": "推理模型的兴起把测试时计算确立为第二条缩放轴：OpenAI 的 o 系列放大强化学习与测试时推理 [84, 83]；Anthropic 的 extended-thinking 模型分配自适应思考预算，并在推理中穿插工具使用 [6, 7]；DeepSeek-R1 [40] 与 Kimi K1.5 [118] 表明大规模强化学习可以从强预训练模型中引出复杂推理行为；Kimi K2.5 Agent Swarm [59] 则把测试时缩放从串行推理进一步扩展到并行智能体协同。",
    "s_1ce6dc004a": "这些进展使测试时缩放成为前沿研究的核心议题。",
    "s_cb64e7be89": "然而，开源生态在第二条轴上进展迅速，在第一条轴上却相对缓慢：许多近期模型仍停留在 1T 级参数规模附近 [145, 29, 135, 120]。",
    "s_2c88f0aacd": "当越来越复杂的推理与智能体强化学习被施加在规模相近的预训练底座上时，开源进展有趋同风险，与最强闭源系统的差距反而拉大。",
    "s_5e134336dd": "Kimi K3 同时把两条缩放轴推向前沿：把预训练底座扩到前所未有的 3T 级参数，并在 1M 上下文长度上放大强化学习、推理投入与长程交互。",
    "s_f39c438f74": "我们推出 Kimi K3：原生多模态混合专家模型，总参数 2.8 万亿，激活参数 1040 亿，上下文窗口最长一百万 token。",
    "s_40c649e627": "其架构沿序列长度、网络深度与模型宽度三个方向扩展信息流动。",
    "s_8c93c55906": "Kimi Delta Attention（KDA）[63] 提供高效的长序列混合，并周期性地插入 Gated MLA 层以保留全局交互。",
    "s_2c9e7eacf0": "Attention Residuals（AttnRes）[57] 使每一层都能选择性地关注此前所有层的表示。",
    "s_0bd0ec7d76": "Stable LatentMoE 将路由专家空间扩展到 896 个、每 token 激活 16 个，同时用归一化、SiTU-GLU 与分位数均衡在极高稀疏度下稳定优化。",
    "s_4491cb6dac": "这些架构进展加上改进的数据与训练配方，相对 Kimi K2 [58] 整体缩放效率约提升 2.5 倍。",
    "s_6fc7e94634": "我们把这一预训练底座与专为 1M 上下文测试时缩放设计的后训练结合在一起。",
    "s_92c5bfa812": "Kimi K3 在长程编程、通用智能体、通用推理与知识任务上做强化学习，并覆盖多种推理投入档位。",
    "s_d1d69707aa": "训练环境包括可验证搜索与专业知识工作、软件工程与内核优化、带视觉闭环工具使用的多模态推理、持久助手工作流、Web 开发以及自主执行任务。",
    "s_42c8c6dee8": "这些环境训练的是推理—行动—观察—验证—适应的通用循环，常常跨越数百乃至数千次工具调用和累计数百万上下文 token。",
    "s_776e715ff9": "领域与投入档位上的专用策略，再通过多教师 on-policy 蒸馏合并为统一模型 [75, 134, 29]。",
    "s_1b39e3a857": "实现这一机制需要能随架构复杂度、模型规模与轨迹长度一起扩展的基础设施。",
    "s_56dfd32e14": "在 KDA 的系统协同设计上，我们开发了融合内核、KDA 上下文并行以及状态感知的前缀缓存，使 KDA 在设备内、设备间与请求间都足够高效。",
    "s_857ea8bab7": "对于 2.8T 参数 MoE 预训练，MoonEP 以静态计算形状与零拷贝通信实现完全均衡的专家执行，同时显存高效训练与多模态编码器优化在有界显存内维持利用率。",
    "s_d6c1db3544": "对于百万 token 智能体强化学习，我们的共置系统结合部分 rollout、外部 KV cache 保留、自适应节流以及可恢复的 microVM 沙箱，以保持长寿命的模型与环境状态。",
    "s_5753c16766": "最后，专用内核以及感知缓存与预算的集群调度，把这些创新转化为可预期的生产级服务。",
    "s_4987aaa6ae": "由此得到的模型树立了新的开源前沿。",
    "s_e038fe4e02": "在覆盖长程编程、智能体、知识、推理与视觉的基准上，Kimi K3 整体仍落后于最强闭源系统 Claude Fable 5 与 GPT-5.6 Sol，但稳定领先于我们套件中其余开源与闭源模型，见图 1。",
    "s_916e553985": "本文贡献概括如下：",
    "s_bbc35afd52": "• 开源前沿规模的预训练。",
    "s_e7cfe497e6": "我们训练了总参数 2.8T、激活 104B、上下文 1M token 的原生多模态 MoE 模型。",
    "s_9c828f2fa1": "KDA、AttnRes、Stable LatentMoE 以及改进的数据与训练配方，使整体缩放效率相对 Kimi K2 约提升 2.5 倍。",
    "s_45067c5b04": "• 面向多档测试时缩放的强化学习。",
    "s_a9da0f4932": "我们在通用、智能体与编程领域及多种推理投入档位上开展 RL，再将所得能力合并为统一模型。",
    "s_7bbffc91e9": "• 支撑千万亿参数、百万 token 智能的基础设施。",
    "s_a06bea9fc0": "我们提出 KDA 系统协同设计；面向 2.8T MoE 预训练的 MoonEP 与显存高效基础设施；带可恢复沙箱、面向百万 token 智能体轨迹的共置 RL 系统；以及其他基础设施创新。",
    "s_b95d4a42fe": "• 开放的前沿模型。",
    "s_ba09c83905": "我们发布完整的 Kimi K3 权重，使前沿智能可用于研究、部署与进一步创新。",
    "s_cc224cfc88": "图 2：Kimi K3 架构，围绕 token、通道与层混合组织，输入端带有原生视觉通路。",
    "s_2a5bfbe4b1": "每个 block 包含三层 Kimi Delta Attention（KDA）再接一层 Gated MLA，且每层注意力都配有 Stable LatentMoE 前馈网络。",
    "s_de6e1deab9": "Attention Residuals（AttnRes）用学到的伪查询 (w) 对嵌入与此前 block 输出计算注意力权重 (α)，从而在深度上选择性地传递信息。",
    "s_db270c698a": "左上：含共享专家与路由专家的 Stable LatentMoE 模块。",
    "s_32924dde9a": "左下：KDA 模块。",
    "s_63163cd81d": "右下：原生视觉通路。",
    "s_9dbcc3eb13": "2 模型架构",
    "s_882f596046": "Kimi K3 架构旨在沿三个互补维度扩展信息流动：序列长度、网络深度与模型宽度。",
    "s_706643edaa": "在序列维上，Hybrid Attention 在每个 block 中把三层 Kimi Delta Attention（KDA）[63] 与一层 Gated MLA 结合，在保留选择性高容量注意力的同时高效做长上下文 token 混合（§2.1）。",
    "s_2e428fa3b0": "在深度维上，Attention Residuals（AttnRes）[57] 使每个模块都能选择性地取回嵌入、当前 block 以及此前 block 的表示，把信息访问扩展到常规串行残差累积之外（§2.2）。",
    "s_a452705825": "在宽度维上，每层注意力后接 Stable LatentMoE，做稀疏通道混合，每个 token 实际激活 896 个路由专家中的 16 个（§2.3）。",
    "s_7005fb4278": "原生视觉方面，MoonViT-V2 编码图像与视频，轻量投影器把视觉特征映射到共享嵌入空间后再进入主干（§2.4）。",
    "s_61337292d1": "再配合 Per-Head Muon（§2.5），这些组件构成沿 token、层与通道扩展信息流的统一架构。",
    "s_1a7ab32ed6": "结合改进的训练与数据配方，相对 Kimi K2 整体缩放效率约提升 2.5 倍。",
    "s_0c1f6e9e99": "图 2 给出架构总览。",
    "s_1c11984b16": "2.1 Hybrid Attention",
    "s_7584e4288c": "Kimi K3 采用线性注意力与全局注意力的逐层混合，将 KDA [63] 与 Gated MLA 结合。",
    "s_e4f76459fd": "每个 block 含 3 层 KDA 再接 1 层 Gated MLA，混合比为 3:1。",
    "s_c7037d6e42": "该模式在整个主干中重复。",
    "s_206b5a8a12": "两种注意力机制分别在下文描述。",
    "s_0936749963": "主干末尾再放一层 Gated MLA，确保最后一层始终做全局注意力。",
    "s_25d3ae1a30": "2.1.1 Kimi Delta Attention",
    "s_e9703137b5": "KDA 在 delta-rule 递推 [105, 138] 上增加了通道级遗忘门 [63]。",
    "s_3e022bd61b": "考虑隐状态序列 $\\pmb{x}_t \\in \\mathbb{R}^{d}$，其中 t 为 token 位置、d 为模型隐空间维度。",
    "s_deb82d270e": "为清晰起见，先描述单头：查询与键 $\\boldsymbol{q}_t,\\boldsymbol{k}_t\\in\\mathbb{R}^{d_k}$，值 $\\pmb{v}_t\\in\\mathbb{R}^{d_v}$，递推状态 $\\mathbf{S}_t\\in\\mathbb{R}^{d_k\\times d_v}$。KDA 在 delta-rule 更新之前施加通道级衰减：",
    "s_c729e5c125": "其中 $\\pmb{\\alpha}_t\\in(0,1)^{d_k}$ 是通道级单步保持因子，$\\beta_t\\in(0,1)$ 控制 delta-rule 写入强度。",
    "s_b1d3346a18": "沿用 Kimi Linear [63]，KDA 将各头量参数化为",
    "s_b806c2a703": "查询、键、值投影先经 ShortConv 再接 Swish [138]，查询与键还进一步做 $L_2$ 归一化。",
    "s_9d2acbac8d": "低秩投影与头相关偏置为每个 key 通道产生细粒度衰减 logit。",
    "s_5b02b2b49e": "从该 logit 到保持因子 $\\alpha$ 的带下界映射在下文分块形式之后引入。",
    "s_e23b4a9b19": "分块并行形式。沿用 Kimi Linear [63]，KDA 在块间递推、在块内并行。",
    "s_8f5b61488a": "对块大小 $C$，$\\mathbf{X}_{[t]}$ 堆叠第 t 块中属于 $\\{Q,K,V,O,\\tilde U,W\\}$ 的 token 向量。",
    "s_f8ca7473c2": "矩阵 $\\mathbf{S}_{[t]}\\in\\mathbb{R}^{d_k\\times d_v}$ 表示进入第 t 块的递推状态。",
    "s_aa0dae1f48": "对位置 $1\\le i\\le j\\le C$，定义通道级累积衰减",
    "s_06714227ed": "与 Kimi Linear 一样，$\\mathbf{\\Gamma}_{[t]}^{1C}\\in\\mathbb{R}^{C\\times d_k}$ 按行堆叠 $\\gamma_{[t]}^{1},\\ldots,\\gamma_{[t]}^{C}$。",
    "s_7fdc9279c7": "UT 变换产生 $\\mathbf{U}_{[t]}$ 与 $\\mathbf{W}_{[t]}$，由此定义伪值项 $\\widetilde{\\mathbf{V}}_{[t]}:=\\mathbf{U}_{[t]}-\\mathbf{W}_{[t]}\\mathbf{S}_{[t]}$。",
    "s_5954d4a781": "给定进入状态 $\\mathbf{S}_{[t]}$，第 t 块内全部输出可并行计算为",
    "s_04438da518": "对矩阵 $M$，Tril$(M)$ 将严格上三角置零，保留含对角的下三角。",
    "s_cf8f0795af": "该掩码在块内强制因果交互；保留对角是因为每个输出读取的是当前 token 更新之后的状态。",
    "s_107d10e4d6": "$\\mathbf{O}_{[t]}$ 的第一项携带此前各块的信息，第二项刻画当前块内交互。",
    "s_56ddf42430": "UT 变换以及分块形式的完整推导见 Kimi Linear [63]。",
    "s_0df51c7c28": "有下界的衰减。式 (4) 用累积衰减的倒数 $1/\\Gamma_{[t]}^{1C}$ 对块内 key 重新缩放。",
    "s_2f921f4281": "由于 $\\Gamma_{[t]}^{1C}$ 是 $(0,1)$ 上保持因子的连乘，该倒数可能无界增长并在有限精度下溢出 [140, 63]。",
    "s_f45a9346b4": "Kimi Linear 通过在对数域计算相对衰减，并把每块再切成 16-token 的二级 tile 来控制数值范围 [140, 63]。",
    "s_c8db4566b6": "于是非对角 tile 可直接在 Tensor Core 上用稠密矩阵乘计算。",
    "s_e83468a16e": "对角 tile 则仍需显式的位置对计算，这仍是块内主要瓶颈。",
}

PAGE_IDS = {
    "1": [
        "s_94bb18e473", "s_d42804011c", "s_c5f8c088ae", "s_206b35552a", "s_f4ca4f073f",
        "s_59620645c9", "s_4a2eb832fa", "s_07eb2ce4f6", "s_02a60b548e", "s_b41fbde818",
        "s_1486dc4ab8", "s_a4fedc5004", "s_f118ffd9ae", "s_2ebd8c9b5d",
    ],
    "2": [
        "s_2cbfa53c83", "s_bdd1cf83c2", "s_11ea9a6bc2", "s_1ce6dc004a", "s_cb64e7be89",
        "s_2c88f0aacd", "s_5e134336dd", "s_f39c438f74", "s_40c649e627", "s_8c93c55906",
        "s_2c9e7eacf0", "s_0bd0ec7d76", "s_4491cb6dac", "s_6fc7e94634", "s_92c5bfa812",
        "s_d1d69707aa", "s_42c8c6dee8", "s_776e715ff9", "s_1b39e3a857", "s_56dfd32e14",
        "s_857ea8bab7", "s_d6c1db3544", "s_5753c16766", "s_4987aaa6ae", "s_e038fe4e02",
        "s_916e553985", "s_bbc35afd52", "s_e7cfe497e6", "s_9c828f2fa1", "s_45067c5b04",
        "s_a9da0f4932", "s_7bbffc91e9", "s_a06bea9fc0", "s_b95d4a42fe", "s_ba09c83905",
    ],
    "3": [
        "s_cc224cfc88", "s_2a5bfbe4b1", "s_de6e1deab9", "s_db270c698a", "s_32924dde9a",
        "s_63163cd81d", "s_9dbcc3eb13", "s_882f596046", "s_706643edaa", "s_2e428fa3b0",
        "s_a452705825", "s_7005fb4278", "s_61337292d1", "s_1a7ab32ed6", "s_0c1f6e9e99",
    ],
    "4": [
        "s_1c11984b16", "s_7584e4288c", "s_e4f76459fd", "s_c7037d6e42", "s_206b5a8a12",
        "s_0936749963", "s_25d3ae1a30", "s_e9703137b5", "s_3e022bd61b", "s_deb82d270e",
        "s_c729e5c125", "s_b1d3346a18", "s_b806c2a703", "s_9d2acbac8d", "s_5b02b2b49e",
        "s_e23b4a9b19", "s_8f5b61488a", "s_f8ca7473c2", "s_aa0dae1f48", "s_06714227ed",
        "s_7fdc9279c7", "s_5954d4a781", "s_04438da518", "s_cf8f0795af", "s_107d10e4d6",
        "s_56ddf42430", "s_0df51c7c28", "s_2f921f4281", "s_f45a9346b4", "s_c8db4566b6",
        "s_e83468a16e",
    ],
}


def main() -> None:
    if not (PAPER / "document.json").exists():
        raise SystemExit("找不到 K3 document.json")
    pages = {}
    for page, ids in PAGE_IDS.items():
        missing = [i for i in ids if i not in ZH]
        if missing:
            raise SystemExit(f"page {page} missing zh: {missing}")
        pages[page] = {
            "status": "ready",
            "error": None,
            "sentences": {i: ZH[i] for i in ids},
        }
    payload = {
        "paper_id": "c03e3fd0-c3b5-4f65-8af7-eb720a5f3893",
        "target_lang": "zh-CN",
        "prompt_version": 1,
        "provider": "preview",
        "model": "preview",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "pages": pages,
    }
    dest = PAPER / "translations" / "zh-CN.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {dest} pages={list(pages)}")


if __name__ == "__main__":
    main()
