# Pearl Mining on Vast.ai — Quick Start Guide

## What Is This?

Pearl (PRL) is a new cryptocurrency that you mine by running AI inference (like ChatGPT) on powerful GPUs. Instead of wasting electricity on pointless math like Bitcoin, Pearl finds valid blocks as a **by-product** of running a real AI model (Llama-3.3-70B).

**TL;DR:** You rent a GPU in the cloud for ~$4/hr, it runs an AI model, and you earn PRL tokens while it does useful work.

---

## What You Need

1. **A Vast.ai account** — https://vast.ai (sign up, add ~$50 credit to start)
2. **A Pearl wallet address** — Get one at https://lordofpearls.xyz
3. **A HuggingFace token** — Free, takes 30 seconds: https://huggingface.co/settings/tokens (click "New token" → Read)

That's it. No coding required.

---

## Step-by-Step Setup (5 minutes)

### 1. Create Your Vast.ai Account
- Go to https://vast.ai
- Sign up with email
- Add credits ($50–100 to start, it's ~$4/hr to run)

### 2. Get Your Pearl Wallet
- Go to https://lordofpearls.xyz
- Create a wallet (save your seed phrase somewhere safe!)
- Copy your wallet address (starts with `prl1...`)

### 3. Get a HuggingFace Token
- Go to https://huggingface.co/settings/tokens
- Click "New token" → name it anything → set to "Read" → Create
- Copy the token (starts with `hf_...`)

### 4. Rent a GPU on Vast.ai

Go to: https://cloud.vast.ai/create/

**Search filters:**
- GPU: **H200** or **H100 SXM** (these are the profitable ones)
- Disk: at least **300 GB**
- Look for machines $3–5/hr

**Under "Template/Image":**
```
ghcr.io/terrapin88/pearl-miner-docker:latest
```

**Under "Environment Variables" add these three:**
```
PEARL_WALLET_ADDRESS=prl1xxxYOUR_WALLET_ADDRESS_HERExxx
HF_TOKEN=hf_xxxYOUR_HUGGINGFACE_TOKEN_HERExxx
PEARL_DP_SIZE=1
```

**Docker options:**
- Run mode: **Args** (not SSH)
- Ports: `8000, 8339, 44108`
- Disk: `300 GB`

Click **RENT** and you're done!

---

## What Happens Next (Automatic)

1. ⏳ **Image pulls** (~1 min) — Downloads the mining software
2. ⏳ **Chain syncs** (~10-15 min) — Downloads the Pearl blockchain
3. ⏳ **Model downloads** (~5-15 min) — Downloads the 140GB AI model
4. ⛏️ **Mining starts!** — 32 workers flood the GPU with AI requests

**Total time from "Rent" to "Mining": ~20-30 minutes**

---

## How to Check If It's Working

### On Vast.ai:
- Click your instance → "Logs"
- Look for: `[Stats] total_requests=XXXX active_workers=32/32`
- That means it's mining!

### On the Pearl Explorer:
- Go to https://lordofpearls.xyz
- Search your wallet address
- You'll see rewards appear when you find blocks

---

## Economics (Rough Numbers)

| Item | Value |
|------|-------|
| GPU Cost | ~$4/hr ($96/day) |
| Pearl Block Reward | Varies by difficulty |
| Current PRL Price | Check https://pearl-otc.com/marketplace |
| Break-even | Depends on network hashrate & PRL price |

**Rule of thumb:** At current network size, 1x H200 can find several blocks per day. Check the OTC market for current PRL price to estimate daily revenue.

---

## Troubleshooting

**Instance stuck on "loading":**
- Wait 5 minutes. The image is 15GB.
- If stuck >10 min, destroy and try a different machine.

**Logs show errors about "downloading blocks":**
- Normal! The chain is still syncing. Wait 10-15 min.

**vLLM crashes or "no block template":**  
- Usually a timing issue. The container will auto-restart and work on the second try.

**No blocks found after hours:**
- Mining is probabilistic — like a lottery. More GPUs = more chances.
- Check that `active_workers=32/32` appears in logs.

---

## Scaling Up

Want more hashrate? Just rent more GPUs! Each instance runs independently. Rent 2-3 H200s on different machines for best results.

---

## Useful Links

- **Pearl Explorer:** https://lordofpearls.xyz
- **Pearl OTC Market:** https://pearl-otc.com/marketplace  
- **Pearl Mining Info:** https://lordofpearls.xyz/mine
- **This Docker Image:** https://github.com/terrapin88/pearl-miner-docker
- **Vast.ai:** https://vast.ai

---

## Quick Reference

```
Image:    ghcr.io/terrapin88/pearl-miner-docker:latest
GPU:      H200 or H100 SXM (1+ GPU)
Disk:     300 GB minimum
Env vars: PEARL_WALLET_ADDRESS, HF_TOKEN, PEARL_DP_SIZE=1
Mode:     Args (not SSH)
Cost:     ~$4/hr per GPU
```

Happy mining! 🐚⛏️
