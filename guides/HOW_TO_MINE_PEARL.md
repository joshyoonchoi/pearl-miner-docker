# How to Mine PEARL on Vast.ai — Zero to Mining in 5 Minutes

## What is Pearl?

Pearl (PRL) is a Proof-of-Useful-Work blockchain where mining = running LLM inference. Instead of burning electricity on SHA-256 hashes, your GPU runs Llama-3.3-70B inference and finds blocks as a byproduct of the matrix multiplications. Same security model as Bitcoin, but the compute does useful work.

**Current Network Stats (May 2026):**
- Block reward: ~2,845 PRL/block
- Block time: ~73 seconds (~1,186 blocks/day)
- Network hashrate: 2.33 EH/s
- Circulating supply: 138.5M / 2.1B max (6.6% minted — very early)
- PRL trades OTC only at ~$0.05 (pearl-otc.com)

## Economics

| Metric | Value |
|--------|-------|
| Revenue per H200/day | ~2,600 PRL (~$130 at $0.05) |
| GPU cost (Vast.ai H200) | ~$3.50-4.25/hr ($84-102/day) |
| **Net profit per GPU** | **~$28-46/day** |
| Breakeven PRL price | ~$0.039 |
| Expected time between blocks (1 GPU) | ~26 hours |

**Important:** Solo mining has high variance. You might find 3 blocks in a day or zero for 48 hours. The math works out over weeks, not hours.

## Requirements

- **GPU:** NVIDIA H100 or H200 (sm_90 architecture ONLY — no consumer cards)
- **VRAM:** 80 GB minimum (H100), 141 GB ideal (H200)
- **Disk:** 200 GB+ (model weights + chain data)
- **Account:** Vast.ai account with payment method
- **Tokens:** HuggingFace token (free, for model download)

## Prerequisites

1. **Get a Pearl wallet address**
   - Download `prlctl` from https://github.com/pearl-research-labs/pearl/releases
   - Run: `prlctl --wallet create`
   - Save your `prl1...` address securely

2. **Get a HuggingFace token**
   - Go to https://huggingface.co/settings/tokens
   - Create a read token (free)

## One-Click Deploy on Vast.ai

### Step 1: Go to Vast.ai
Visit https://cloud.vast.ai and create an account if you don't have one.

### Step 2: Create a new instance
- Click **"Create Instance"**
- In the **Docker Image** field, enter:
  ```
  ghcr.io/terrapin88/pearl-miner-docker:latest
  ```

### Step 3: Select your GPU
- Filter for **H100 SXM** or **H200 SXM**
- Sort by price (cheapest first)
- Look for machines with 200GB+ disk space
- Target: $2.50-4.25/hr

### Step 4: Set environment variables
Add these in the "Environment Variables" section:
```
PEARL_WALLET_ADDRESS=prl1youractualwalletaddress
HF_TOKEN=hf_youractualtoken
```

### Step 5: Configure resources
- **Disk:** 200 GB minimum
- **Docker Options:** `--shm-size 8g`

### Step 6: Click Rent!
That's it. The container will:
1. Start the Pearl full node (`pearld`)
2. Sync the blockchain from genesis (~2 hours first time)
3. Launch the Pearl gateway
4. Start vLLM with the mining model
5. Begin 32-thread inference flood (this IS the mining)

## What Happens Under the Hood

```
pearld (full node) → syncs chain, provides block templates
       ↓
pearl-gateway → pulls templates, connects to vLLM via Unix socket
       ↓
vLLM + NoisyGEMM plugin → runs inference, finds valid nonces during matmul
       ↓
pearl_worker.py → 32 threads sending continuous requests to keep GPU busy
```

The magic is in the **NoisyGEMM kernel** — it replaces standard matrix multiplication with a version that embeds proof-of-work nonce searching into the computation. Every inference request is also a mining attempt.

## Monitoring

### Check your instance logs on Vast.ai
Look for:
- `✅ Pearl node is running` — node started
- `✅ vLLM is ready! Starting mining worker...` — mining active
- `[Stats] total_requests=XXXXX active_workers=32/32` — healthy
- `Template refreshed successfully (height: XXXXX)` — synced to tip
- **`Block found, creating proof for submission.`** — YOU WON! 🎉

### Check the explorer
Go to https://lordofpearls.xyz and search your `prl1...` address to see:
- Blocks mined
- Balance
- Miner rank

## Troubleshooting

| Problem | Solution |
|---------|----------|
| vLLM crashes on startup | Node wasn't synced yet. The image handles this with a sync-wait, but if you see it, just restart the instance. |
| 0 blocks after 48+ hours | Something may be wrong. Check that `active_workers=32/32` and templates are refreshing. |
| "Template refreshed" stops appearing | Node fell behind. Restart the instance. |
| GPU utilization < 90% | Workers may have died. Instance restart fixes this. |

## Scaling Up

- Each H200 finds ~1 block every 26 hours on average
- 4 GPUs = 1 block every ~6.5 hours (much more consistent)
- Use different instances, same wallet address
- The `PEARL_WALLET_ADDRESS` can be shared across machines

## Links

- **Explorer:** https://lordofpearls.xyz
- **OTC Market:** https://pearl-otc.com/marketplace
- **Docker Image:** ghcr.io/terrapin88/pearl-miner-docker:latest
- **Source Code:** https://github.com/terrapin88/pearl-miner-docker
- **Pearl Protocol:** https://github.com/pearl-research-labs/pearl

---

*Built by the community. Not financial advice. Solo mining has variance — don't rent more than you can afford to lose.*
