# 🐚 Pearl Mining on Vast.ai — Discord Guide

## TL;DR
Mine PRL by running LLM inference on rented H100/H200 GPUs. One Docker image, two env vars, zero SSH.

## 💰 Economics (May 2026)
```
Block reward:     ~2,845 PRL/block
Block time:       ~73 seconds
Network hashrate: 2.33 EH/s
PRL OTC price:    ~$0.05

Per H200:
  Revenue: ~2,600 PRL/day (~$130)
  Cost:    $84-102/day (Vast.ai)
  Profit:  ~$28-46/day net
  
Breakeven: $0.039/PRL
```
⚠️ Solo mining = high variance. Expect ~1 block per 26 hours per GPU. Could be 0 for 48h, could be 3 in a day.

## ✅ Requirements
- Vast.ai account (funded)
- NVIDIA **H100 or H200** (sm90 only — no consumer cards)
- HuggingFace token (free): https://huggingface.co/settings/tokens
- Pearl wallet address (`prl1...`) — get `prlctl` from Pearl releases

## 🚀 Setup (5 minutes)

**1.** Go to https://cloud.vast.ai → Create Instance

**2.** Docker Image:
```
ghcr.io/terrapin88/pearl-miner-docker:latest
```

**3.** Filter GPUs: **H100 SXM** or **H200 SXM**, 200GB+ disk

**4.** Environment Variables:
```
PEARL_WALLET_ADDRESS=prl1yourwallethere
HF_TOKEN=hf_yourtokenhere
```

**5.** Set disk to 200GB, add `--shm-size 8g` to Docker options

**6.** Click **Rent** → Done. Mining starts automatically after chain sync (~2hrs first time).

## 📊 What "Working" Looks Like
In your Vast.ai instance logs:
```
✅ Pearl node is running
✅ vLLM is ready! Starting mining worker...
[Stats] total_requests=442687 active_workers=32/32
Template refreshed successfully (height: 45898)
```

When you find a block:
```
Block found, creating proof for submission.
Submitted plain proof to gateway
```

## 🔍 Monitoring
- **Logs:** Vast.ai dashboard → your instance → Logs
- **Explorer:** https://lordofpearls.xyz → search your `prl1...` address
- **Key metrics:** `active_workers=32/32` + templates refreshing = healthy

## ⚡ Scaling
Same wallet across multiple instances. Each GPU is independent.
- 1 GPU → ~1 block/26hrs (high variance)
- 4 GPUs → ~1 block/6.5hrs (much smoother)
- 8 GPUs → ~1 block/3.25hrs (approaching consistency)

## 🔗 Links
- Image: `ghcr.io/terrapin88/pearl-miner-docker:latest`
- Source: https://github.com/terrapin88/pearl-miner-docker
- Explorer: https://lordofpearls.xyz
- OTC: https://pearl-otc.com/marketplace
- Stats: https://lordofpearls.xyz/stats

## ❓ FAQ

**Q: Can I use RTX 4090?**
No. Pearl's NoisyGEMM kernel requires Hopper (sm90). H100/H200 only.

**Q: Do I need SSH access?**
No. Everything runs automatically from the Docker image.

**Q: How long until first block?**
Average ~26 hours per GPU. Could be 2 hours, could be 50. Solo mining variance.

**Q: What model does it run?**
`pearl-ai/Llama-3.3-70B-Instruct-pearl` — a modified Llama with Pearl's mining kernel baked in.

**Q: Is this the same as Pearl Compute?**
Same end result, DIY approach. Pearl Compute (managed hosting) is currently sold out.

---
*Not financial advice. DYOR. Solo mining has variance.*
