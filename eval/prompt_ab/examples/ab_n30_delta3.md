# W8-3 Prompt A/B

- 黄金集：w8_prompt_30.json（w8-prompt-v1）
- 种子：42，顺序已打乱，配对按题号
- A：`strategy.zero_shot@1.0.0` 准确率 70.0%（Wilson 52.1%–83.3%）
- B：`strategy.zero_shot@1.1.0` 准确率 73.3%（Wilson 55.5%–85.8%）
- Δ=3.3%，95% 区间 [-19.5%, 26.1%]
- McNemar n01=1 n10=0 p=1.0
- credible=false

**结论：** n=30 提升 3.3% 通常不可信：样本量不足，95% 区间穿过 0，不能凭这一点上线。
