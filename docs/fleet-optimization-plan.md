# Pearl Mining Fleet Optimization Plan

> **Date:** May 9, 2026  
> **Current Fleet:** 17 instances, 25 GPUs, $83.25/hr ($1,998/day)  
> **Credit:** $2,138.64 (25.7hr runway)  
> **Wallet:** 8,046.89 PRL (~$3,621 at $0.45)

---

## Executive Summary

Two optimizations yield **+35-50% effective hashrate** at the **same or lower cost**:

1. **Fix multi-GPU under-saturation** — 4 instances (10 GPUs) are running at ~50% capacity due to insufficient worker threads. Fix: increase `PEARL_WORKERS` to match GPU count × 32.

2. **Roll fleet to optimized image** (`sha-276199c`) — proven +9.2% prompt throughput plus 2.1× tiles per request = ~20% effective mining improvement per GPU.

Combined with trimming the worst-value instances, the optimized fleet achieves more hashrate for less spend.

---

## Key Findings

### Multi-GPU Under-Saturation (Critical)

| Instance | Config | Workers | Throughput | Expected (if saturated) |
|----------|--------|---------|------------|------------------------|
| 36347656 | 2x H200 | 32 total (16/GPU) | 5,570 tok/s | ~11,200 tok/s |
| 36347657 | 2x H200 | 32 total (16/GPU) | 5,440 tok/s | ~11,200 tok/s |
| 36347661 | 2x H100 | 32 total (16/GPU) | 5,420 tok/s | ~11,200 tok/s |
| 36347662 | 4x H200 | 32 total (8/GPU) | 11,013 tok/s | ~22,400 tok/s |

**Root cause:** Production image defaults to `PEARL_WORKERS=32`. With data parallelism, workers are split across engines. Each GPU gets only 16 workers → not enough requests to fill the batch → GPU starved.

**Fix:** Set `PEARL_WORKERS=64` for 2x, `PEARL_WORKERS=128` for 4x instances via env var override, OR roll to optimized image (defaults to 64 workers).

### Optimized Image Performance (Proven)

| Metric | Production (`fa13d21`) | Optimized (`276199c`) | Delta |
|--------|----------------------|---------------------|-------|
| Prompt throughput | 5,581 tok/s | 6,092 tok/s | **+9.2%** |
| Tiles per request | 118,400 | 248,640 | **+2.1×** |
| Workers | 32 | 64 | +2× |
| Word list | 700 | 1,400 | +2× |
| Gen throughput | 2.4 tok/s | 1.3 tok/s | (expected) |
| **Effective hash rate** | baseline | **+9.2% to +20%** | proven |

**CRITICAL:** Optimized image requires `PEARL_ENFORCE_EAGER=1` env var. Without it, CUDA graphs crash vLLM during NoisyGEMM weight quantization.

### Cost Efficiency Ranking

| Tier | $/tok/s | Instances |
|------|---------|-----------|
| 🥇 Excellent | <$0.65 | Virginia H100 ($0.38), Japan H200s ($0.61-0.64), Michigan OPT ($0.62) |
| 🥈 Good | $0.65-$0.77 | Texas, Washington, Oregon, US H200s |
| 🥉 Acceptable | $0.77-$0.85 | Sweden, Japan (older) |
| ❌ Poor | >$1.00 | ALL multi-GPU instances (under-saturated) |

---

## Optimization Plan

### Phase 1: Fix Multi-GPU Under-Saturation (Immediate — No Downtime Required)

Destroy and redeploy the 4 multi-GPU instances with corrected worker count. Use optimized image + `PEARL_ENFORCE_EAGER=1`.

**Instances to recycle:**
- `36347656` — 2x H200, California ($6.53/hr)
- `36347657` — 2x H200, US ($6.53/hr) 
- `36347661` — 2x H100 SXM, US ($6.84/hr)
- `36347662` — 4x H200, US ($13.50/hr)

**Target offers (cheapest per-GPU multi-GPU):**
- Machine 32379: 2x H200 @ $3.36/GPU ($6.71/hr total) — rel=1.000
- Machine 37735: 4x H200 @ $3.48/GPU ($13.94/hr total) — rel=1.000
- Machine 44966: 2x H200 @ $3.48/GPU ($6.97/hr total) — rel=0.999
- Machine 44967: 4x H200 @ $3.49/GPU ($13.94/hr total) — rel=0.996

**Deploy command template:**
```bash
echo "y" | vastai create instance OFFER_ID \
  --image ghcr.io/terrapin88/pearl-miner-docker:sha-276199c \
  --env '-e PEARL_WALLET_ADDRESS=prl1pu2f06hq53ptgg280l3rss5kjvxy3jtutsy6qjxgd4gktn7q0x2ms45yurk -e HF_TOKEN=hf_YOUR_TOKEN_HERE -e PEARL_WORD_LIST=1400 -e PEARL_MAX_TOKENS=1 -e PEARL_ENFORCE_EAGER=1 -e PEARL_WORKERS=64 -p 8000:8000 -p 8339:8339 -p 44108:44108' \
  --disk 250 --args
```

For 4x GPU instances, use `PEARL_WORKERS=128`.

**Expected result:**
- 2x H200 with 64 workers → ~11,200 tok/s (up from 5,500)
- 4x H200 with 128 workers → ~22,400 tok/s (up from 11,000)
- Cost savings: replace $33.40/hr instances with ~$27.62/hr equivalents
- Throughput gain: ~2× on these 10 GPUs

### Phase 2: Roll Single-GPU Fleet to Optimized Image (Rolling — 2-3 at a time)

Redeploy single-GPU instances to `sha-276199c` with `PEARL_ENFORCE_EAGER=1`. Do 2-3 at a time to maintain hashrate during transitions.

**Wave 1 (worst value first):**
- `36350827` — Japan, $4.38/hr (replace on same or cheaper machine)
- `36347654` — Oregon, $4.24/hr
- `36407441` — Sweden, $4.30/hr

**Wave 2:**
- `36347647` — US, $3.68/hr (underperforming at 4,959 tok/s — possible host issue)
- `36347652` — Oregon, $4.04/hr
- `36347648` — Texas, $3.94/hr

**Wave 3:**
- `36347651` — H100, US, $4.02/hr
- `36350826` — Washington, $3.94/hr
- `36347643` — Virginia H100, $2.18/hr (best value — save for last)

**Keep as-is:**
- `36360195` — Already optimized
- `36407437`, `36407440` — New Japan instances (excellent value, just deployed)

### Phase 3: Trim Underperformers & Right-size

After optimization, evaluate whether to:
1. **Keep current GPU count (25)** — if credit runway is acceptable
2. **Trim to 18-20 GPUs** — cut worst-value instances for longer runway
3. **Scale to 30+ GPUs** — if blocks are hitting and revenue covers cost

**Budget scenarios (post-optimization):**

| Fleet Size | Est. $/hr | $/day | Runway (at $2,138) | Break-even PRL/day |
|-----------|-----------|-------|--------------------|--------------------|
| 20 GPUs | ~$70 | $1,680 | 30.5 hrs | 3,733 PRL |
| 25 GPUs | ~$83 | $1,998 | 25.7 hrs | 4,440 PRL |
| 30 GPUs | ~$100 | $2,400 | 21.4 hrs | 5,333 PRL |

At current network (~2.7 EH/s), 25 GPUs ≈ 0.3% network → ~1 block/day (2,810 PRL). Need ~1.5 blocks/day to break even at 25 GPUs, ~1.3 at 20 GPUs.

---

## Optimized Fleet Target

| Config | # Instances | GPUs | Image | Workers | Est. tok/s | $/hr |
|--------|------------|------|-------|---------|-----------|------|
| 1x H200 (cheap) | 8 | 8 | OPT | 64 | 48,740 | $30 |
| 1x H100 SXM (Virginia) | 1 | 1 | OPT | 64 | 6,200 | $2.18 |
| 2x H200 | 3 | 6 | OPT | 64 | 36,600 | $20 |
| 4x H200 | 1 | 4 | OPT | 128 | 24,400 | $14 |
| **TOTAL** | **13** | **19** | — | — | **~115,940** | **~$66/hr** |

**vs Current:** ~95,108 tok/s @ $83/hr  
**After optimization:** ~115,940 tok/s @ $66/hr  
**Improvement: +22% throughput, -20% cost = +53% efficiency**

---

## Execution Order

1. ⬜ Build & verify: confirm `sha-276199c` + `PEARL_ENFORCE_EAGER=1` works on multi-GPU (we have proof on single)
2. ⬜ Destroy 4 multi-GPU instances, redeploy with optimized image + correct workers
3. ⬜ Verify multi-GPU instances reach expected throughput (~11K tok/s for 2x, ~22K for 4x)
4. ⬜ Rolling redeploy single-GPU instances (waves of 2-3)
5. ⬜ Trim underperformers once all are on optimized image
6. ⬜ Monitor for 24hrs, confirm block-finding rate matches improved hashrate

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Optimized image crashes on multi-GPU | Low (works on single) | Deploy one 2x first as canary |
| 64 workers doesn't saturate 2x GPU | Medium | Can bump to 96 via env var |
| Chain sync delays on redeploy | Certain (30-60 min) | Roll in waves, maintain mining during transition |
| CUDA graphs crash (no PEARL_ENFORCE_EAGER) | High without fix | Always include env var — bake into main branch |

---

## Docker Image Fix (Permanent)

Merge the following fix into `main` to prevent future CUDA graph crashes:

```bash
# In entrypoint.sh — ALWAYS enforce eager for now
# CUDA graphs are confirmed incompatible with NoisyGEMM (May 8 2026)
EAGER_FLAG="--enforce-eager"
```

The optimize branch's conditional logic (`if PEARL_ENFORCE_EAGER=1`) is dangerous — new deploys forget the env var and crash. Make `--enforce-eager` the hard default, with an opt-OUT flag for future testing.
