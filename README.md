# Pearl Miner — One-Click Docker Image

A ready-to-use Docker image for mining [Pearl (PRL)](https://pearlresearch.ai) on NVIDIA H100/H200 GPUs. Built for zero-config deployment on GPU cloud platforms like **Vast.ai** and **RunPod**.

## What This Does

Pearl is a Proof-of-Useful-Work blockchain where mining = running LLM inference. This image packages everything needed:

- **pearld** — Pearl full node (blockchain sync)
- **pearl-gateway** — mining bridge (connects inference to chain)
- **vLLM** — GPU inference engine with Pearl's NoisyGEMM kernel
- **Model**: `pearl-ai/Llama-3.3-70B-Instruct-pearl`

## Quick Start (Vast.ai)

1. Go to [Vast.ai](https://cloud.vast.ai) → Create New Instance
2. Select template: `ghcr.io/terrapin88/pearl-miner:latest`
3. Filter for **H100 SXM** or **H200 SXM** (required — sm90 GPUs only)
4. Set environment variables:
   - `PEARL_WALLET_ADDRESS=prl1<your-address>`
   - `HF_TOKEN=<your-huggingface-token>`
5. Click **Rent** → Mining starts automatically after node sync (~2hrs first time)

## Quick Start (RunPod)

Same concept — use the image as a custom Docker template with the env vars above.

## Quick Start (Docker, if you have your own H100/H200)

```bash
docker run --rm --gpus all \
  -p 8000:8000 -p 8337:8337 -p 8339:8339 \
  -e PEARL_WALLET_ADDRESS=prl1youraddress \
  -e HF_TOKEN=hf_yourtoken \
  -v pearl-chain-data:/app/chain-data \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  --shm-size 8g \
  ghcr.io/terrapin88/pearl-miner:latest
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PEARL_WALLET_ADDRESS` | ✅ | Your Pearl wallet address (prl1...) |
| `HF_TOKEN` | ✅ | HuggingFace token for model download |
| `PEARL_MAX_MODEL_LEN` | ❌ | Max context length (default: 8192) |
| `PEARL_GPU_UTIL` | ❌ | GPU memory utilization (default: 0.9) |
| `PEARLD_CONNECT` | ❌ | Peer address to speed up initial sync |

## Hardware Requirements

- **GPU**: NVIDIA H100 or H200 (sm90 architecture ONLY)
- **VRAM**: 80 GB minimum (H100), 141 GB recommended (H200)
- **RAM**: 64 GB system memory
- **Disk**: 200 GB+ (model weights + chain data)
- **Network**: 100 Mbps

## Monitoring

- Gateway metrics: `http://localhost:8339/metrics`
- vLLM API: `http://localhost:8000/health`
- Check your mining stats: [lordofpearls.xyz](https://lordofpearls.xyz)

## Economics (as of May 2026)

- Block reward: ~2,845 PRL/block
- Block time: ~74 seconds
- Network hashrate: ~2.38 EH/s
- **No exchange listing yet** — PRL trades OTC only (pearl-otc.com)

## Notes

- First startup takes ~2 hours (blockchain sync from genesis)
- Model download is ~140 GB on first run (cached on subsequent runs if volume is mounted)
- Chain data persists in `/app/chain-data` — mount a volume to preserve between restarts

## Credits

- [Pearl Research Labs](https://github.com/pearl-research-labs/pearl) — the protocol
- [Lord of Pearls](https://lordofpearls.xyz) — community explorer
- Built by the community for the community 🐚

## License

This packaging is MIT. Pearl's upstream code is under their own license.
