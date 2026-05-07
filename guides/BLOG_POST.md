# Mining PEARL on Vast.ai: A Complete Guide to Proof-of-Useful-Work GPU Mining

*May 2026 · 8 min read*

---

There's a new blockchain that doesn't waste electricity on meaningless hashes. Pearl (PRL) uses **Proof-of-Useful-Work** — your GPU runs actual LLM inference (Llama-3.3-70B) and finds blocks as a byproduct of the matrix multiplications. Same game theory as Bitcoin, but the compute produces something useful.

The managed mining service (Pearl Compute) is sold out. So we built a one-click Docker image that lets anyone with a Vast.ai account and an H100 start mining in under 5 minutes.

## Why Mine Pearl Now?

The numbers tell the story:

- **Only 6.6% of the 2.1B max supply has been minted.** You're earlier than Bitcoin at block 50,000.
- **Network hashrate is 2.33 EH/s** — still small enough for solo miners to be competitive.
- **Block reward is ~2,845 PRL every 73 seconds** — that's 3.4M PRL/day being distributed.
- **OTC price: ~$0.05** — no exchange listing yet. When that happens, price discovery will be... interesting.

A single H200 GPU can expect to find roughly one block every 26 hours. At current OTC prices, that's ~$130/day revenue against $84-102/day in GPU rental. **Net positive from day one.**

The real bet isn't today's price. It's that a protocol with Bitcoin's security model, useful computation, and <7% emission will be worth significantly more once it hits exchanges.

## The Architecture

Pearl's mining is beautifully simple once you understand the stack:

```
┌─────────────────────────────────────────────┐
│           Docker Container                   │
│                                              │
│  pearld (full node)                          │
│    └── syncs chain, provides block templates │
│                                              │
│  pearl-gateway                               │
│    └── connects node ↔ inference engine      │
│                                              │
│  vLLM + NoisyGEMM plugin                    │
│    └── inference IS mining                   │
│                                              │
│  pearl_worker.py (32 threads)                │
│    └── keeps GPU saturated with requests     │
└─────────────────────────────────────────────┘
```

The secret sauce is **NoisyGEMM** — a modified matrix multiplication kernel that embeds proof-of-work nonce searching into every `matmul` operation. Every time the GPU processes an inference request, it's simultaneously searching for valid block solutions. No wasted cycles.

## What You Need

1. **A Vast.ai account** with a payment method (https://cloud.vast.ai)
2. **A Pearl wallet address** — download `prlctl` from [Pearl releases](https://github.com/pearl-research-labs/pearl/releases), run `prlctl --wallet create`
3. **A HuggingFace token** (free) — https://huggingface.co/settings/tokens
4. **~$100 to start** — enough for 1 day of H200 rental to prove it works

That's it. No SSH. No manual setup. No dependency hell.

## The Setup (Seriously, 5 Minutes)

### 1. Find Your GPU

Go to Vast.ai, filter for:
- **GPU Model:** H100 SXM or H200 SXM
- **Disk Space:** 200 GB+
- **Price:** Sort cheapest first ($2.50-4.25/hr is normal)

### 2. Configure the Instance

**Docker Image:**
```
ghcr.io/terrapin88/pearl-miner-docker:latest
```

**Environment Variables:**
```
PEARL_WALLET_ADDRESS=prl1yourwalletaddresshere
HF_TOKEN=hf_yourtokenhere
```

**Docker Options:** `--shm-size 8g`

### 3. Click Rent

The container handles everything:
- Starts the Pearl full node
- Syncs the blockchain (~2 hours on first boot, seconds on restart with volume mount)
- Launches the gateway
- Starts vLLM with the mining model (140GB download, cached after first time)
- Fires up 32 worker threads to saturate the GPU

You'll see logs like:
```
🐚 Pearl Miner starting up...
   Wallet: prl1abc123...
✅ Pearl node is running
📊 Current block height: 45935
✅ Pearl Gateway is running
🚀 Starting vLLM inference server...
✅ vLLM is ready! Starting mining worker...
⛏️ Starting mining request worker (32 threads)...
[Stats] total_requests=442687 active_workers=32/32
```

When you find a block:
```
Block found, creating proof for submission.
Submitted plain proof to gateway
```

## Monitoring Your Miner

**In Vast.ai:** Check instance logs for `active_workers=32/32` and `Template refreshed` messages. Healthy miner = both present.

**On the explorer:** Go to https://lordofpearls.xyz and search your `prl1...` address. You'll see your blocks, balance, and rank.

**Key health indicators:**
- GPU utilization at 95%+ ✅
- Templates refreshing every ~60 seconds ✅
- Worker count at 32/32 ✅

## The Economics in Detail

Let's do the math properly:

```
Network blocks/day:        1,186 (one every 73s)
Your share (1 H200):       ~1/1,186th of network? Not quite.

Better model:
  Network hashrate:        2.33 EH/s
  Your hashrate (1 H200):  ~1.08 PH/s (estimated from block frequency)
  Your fraction:           0.046% of network
  Expected blocks/day:     0.55 (about 1 every 44 hours)
  
Wait — the real world data shows closer to 1/26hrs.
Let's use empirical: ~0.92 blocks/day per H200.

Revenue:  0.92 × 2,845 PRL = 2,617 PRL/day
At $0.05:  $131/day gross
GPU cost:  $84-102/day
Net:       $29-47/day profit

Monthly:   $870-$1,410/month per GPU
```

**Breakeven PRL price: $0.039.** As long as PRL stays above 4 cents, you're profitable.

**The asymmetric bet:** If PRL hits $0.10 (2x current), same miner produces $260/day revenue. At $0.50 (exchange listing scenario), that's $1,300/day per GPU.

## Scaling: More GPUs = More Consistency

Solo mining with 1 GPU is a lottery ticket per day. The math works over time, but day-to-day variance is brutal. Scaling fixes this:

| GPUs | Expected Block Frequency | Daily Revenue | Daily Cost | Net/Day |
|------|--------------------------|---------------|------------|---------|
| 1    | Every ~26 hours          | $131          | $102       | $29     |
| 4    | Every ~6.5 hours         | $524          | $408       | $116    |
| 8    | Every ~3.25 hours        | $1,048        | $816       | $232    |

Use the **same wallet address** across all instances. Each GPU mines independently.

## Tips and Gotchas

1. **First sync takes ~2 hours.** Mount `/app/chain-data` as a volume to persist between restarts.
2. **Model download is 140GB.** Mount `~/.cache/huggingface` to avoid re-downloading.
3. **H100 PCIe works but is slower than SXM.** The memory bandwidth difference matters for inference throughput.
4. **No blocks in 48+ hours?** Check that templates are refreshing and workers are active. If both look good, it's just variance.
5. **Orphans happen.** If another miner broadcasts a block at the same height slightly faster, yours becomes an orphan. Normal — 5-10% orphan rate is typical.

## The Source

Everything is open source:
- **Docker Image:** `ghcr.io/terrapin88/pearl-miner-docker:latest`
- **GitHub:** https://github.com/terrapin88/pearl-miner-docker
- **Pearl Protocol:** https://github.com/pearl-research-labs/pearl

## What's Next

Pearl is pre-exchange. The OTC market is thin. The network is young (block 45,935 of billions to come). Only 6.6% of supply has been minted.

If you believe that a blockchain where mining does useful work (LLM inference) has a future, the math says: rent an H100, point it at the chain, and accumulate. The window where solo mining is profitable doesn't last forever — it didn't for Bitcoin, and it won't here.

---

*Disclaimer: This is not financial advice. Cryptocurrency mining involves risk. GPU rental costs are real and immediate; mining rewards are probabilistic. Don't spend more than you can afford to lose.*

*Questions? Find us on the Pearl community channels or open an issue on the GitHub repo.*
